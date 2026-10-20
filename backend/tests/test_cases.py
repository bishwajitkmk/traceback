import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.jobs.retention import purge
from app.services import assertions
from tests.conftest import sign_up
from tests.helpers import event_payload
from tests.target_server import TargetServer, state


@pytest.fixture
def target(
    user_client: TestClient, project: dict, target_server: TargetServer, private_networks: None
) -> dict:
    response = user_client.post(
        f"/api/v1/projects/{project['id']}/targets",
        json={"name": "Local", "base_url": target_server.url, "environment": "local"},
    )
    assert response.status_code == 201
    return response.json()


def checkout_case(**overrides: object) -> dict:
    return {
        "name": "Zero quantity is rejected",
        "description": "Guards the ZeroDivisionError",
        "incident_id": None,
        "source_event_id": None,
        "request_definition": {
            "method": "POST",
            "path": "/checkout",
            "query": {},
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer leaked"},
            "body": {"quantity": 0},
        },
        "assertion_definition": {
            "expected_status": 422,
            "assertions": [
                {"type": "json_path_equals", "path": "$.error.code", "expected": "invalid_quantity"}
            ],
        },
    } | overrides


def test_case_crud_strips_credentials(user_client: TestClient, project: dict) -> None:
    base = f"/api/v1/projects/{project['id']}/regression-cases"
    created = user_client.post(base, json=checkout_case())
    assert created.status_code == 201, created.text
    case = created.json()
    assert "Authorization" not in case["request_definition"]["headers"]
    assert case["last_run"] is None

    patched = user_client.patch(
        f"{base}/{case['id']}", json={"name": "Renamed", "description": None}
    ).json()
    assert patched["name"] == "Renamed" and patched["description"] is None
    assert [c["name"] for c in user_client.get(base).json()] == ["Renamed"]
    assert user_client.delete(f"{base}/{case['id']}").status_code == 204
    assert user_client.get(f"{base}/{case['id']}").status_code == 404


def test_case_validation(user_client: TestClient, project: dict) -> None:
    base = f"/api/v1/projects/{project['id']}/regression-cases"
    bad_status = checkout_case(assertion_definition={"expected_status": 99, "assertions": []})
    assert user_client.post(base, json=bad_status).status_code == 422
    bad_assertion = checkout_case(
        assertion_definition={"expected_status": 200, "assertions": [{"type": "regex"}]}
    )
    assert user_client.post(base, json=bad_assertion).status_code == 422
    foreign_incident = checkout_case(incident_id=str(uuid.uuid4()))
    assert user_client.post(base, json=foreign_incident).status_code == 404


def test_run_fails_before_the_fix_and_passes_after(
    user_client: TestClient, project: dict, target: dict, api_key: str
) -> None:
    ingested = user_client.post(
        "/api/v1/ingest/events",
        json=event_payload(),
        headers={"Authorization": f"Bearer {api_key}"},
    ).json()
    base = f"/api/v1/projects/{project['id']}/regression-cases"
    case = user_client.post(base, json=checkout_case(incident_id=ingested["incident_id"])).json()
    run = lambda confirm=True: user_client.post(  # noqa: E731
        f"{base}/{case['id']}/runs", json={"target_id": target["id"], "confirm_mutation": confirm}
    )

    assert run(confirm=False).status_code == 409  # POST needs confirmation

    state["fixed"] = False
    failed = run().json()
    assert failed["outcome"] == "failed" and failed["kind"] == "regression_run"
    assert [r["passed"] for r in failed["assertion_results"]] == [False, False]
    assert failed["assertion_results"][0]["actual"] == 500

    state["fixed"] = True
    try:
        passed = run().json()
    finally:
        state["fixed"] = False
    assert passed["outcome"] == "passed"

    history = user_client.get(f"{base}/{case['id']}/runs").json()
    assert [h["outcome"] for h in history] == ["passed", "failed"]
    assert user_client.get(f"{base}/{case['id']}").json()["last_run"]["outcome"] == "passed"

    stats = user_client.get(f"/api/v1/projects/{project['id']}/stats").json()
    assert stats["regression"] == {"total": 1, "passing": 1, "failing": 0, "never_run": 0}
    assert stats["recent_runs"][0]["case_name"] == "Zero quantity is rejected"


def test_cli_endpoints_use_the_project_key(
    user_client: TestClient, project: dict, api_key: str, make_client
) -> None:  # type: ignore[no-untyped-def]
    case = user_client.post(
        f"/api/v1/projects/{project['id']}/regression-cases", json=checkout_case()
    ).json()
    auth = {"Authorization": f"Bearer {api_key}"}
    cli = make_client()

    listed = cli.get("/api/v1/ci/regression-cases", headers=auth).json()
    assert [c["id"] for c in listed] == [case["id"]]
    assert cli.get("/api/v1/ci/regression-cases").status_code == 401

    report = {
        "target_url": "http://localhost:8000",
        "duration_ms": 12,
        "response": {
            "status": 422,
            "headers": {"content-type": "application/json"},
            "body": {"error": {"code": "invalid_quantity"}},
        },
    }
    stored = cli.post(
        f"/api/v1/ci/regression-cases/{case['id']}/runs", json=report, headers=auth
    ).json()
    assert stored["outcome"] == "passed" and stored["target_id"] is None
    assert stored["request_summary"]["url"] == "http://localhost:8000/checkout"

    # The server re-evaluates: a runner cannot simply claim success.
    lie = report | {"response": {"status": 500, "headers": {}, "body": {}}, "outcome": "passed"}
    assert (
        cli.post(
            f"/api/v1/ci/regression-cases/{case['id']}/runs", json=lie, headers=auth
        ).status_code
        == 422
    )
    honest = report | {"response": {"status": 500, "headers": {}, "body": {}}}
    assert (
        cli.post(
            f"/api/v1/ci/regression-cases/{case['id']}/runs", json=honest, headers=auth
        ).json()["outcome"]
        == "failed"
    )

    errored = cli.post(
        f"/api/v1/ci/regression-cases/{case['id']}/runs",
        json={"target_url": "http://localhost:8000", "error": "Connection refused"},
        headers=auth,
    ).json()
    assert errored["status"] == "error" and errored["outcome"] == "failed"

    # Another project's key cannot see or report on this case.
    other = make_client()
    sign_up(other, "other@example.com")
    other_project = other.post("/api/v1/projects", json={"name": "Other"}).json()
    other_key = other.post(f"/api/v1/projects/{other_project['id']}/api-keys").json()["key"]
    other_auth = {"Authorization": f"Bearer {other_key}"}
    assert other.get("/api/v1/ci/regression-cases", headers=other_auth).json() == []
    assert (
        other.post(
            f"/api/v1/ci/regression-cases/{case['id']}/runs", json=report, headers=other_auth
        ).status_code
        == 404
    )


def test_assertion_semantics() -> None:
    body = {"order": {"total": 42, "items": [{"sku": "A"}], "note": None}}
    definition = {
        "expected_status": 200,
        "assertions": [
            {"type": "json_path_equals", "path": "$.order.total", "expected": 42},
            {"type": "json_path_equals", "path": "order.items[0]", "expected": {"sku": "A"}},
            {"type": "json_path_exists", "path": "$.order.note"},
            {"type": "body_contains", "expected": '"sku"'},
        ],
    }
    outcome, results = assertions.evaluate(definition, 200, body)
    assert outcome == "passed" and len(results) == 5
    outcome, results = assertions.evaluate(definition | {"expected_status": 201}, 200, body)
    assert outcome == "failed" and results[0]["actual"] == 200
    assert assertions.get_path(body, '$["order"].items[5]') == (False, None)
    assert assertions.parse_path("$..bad") is None


def test_retention_purges_old_events_and_runs(
    db: Session, user_client: TestClient, project: dict, api_key: str
) -> None:
    old = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    for occurred in (old, datetime.now(UTC).isoformat()):
        user_client.post(
            "/api/v1/ingest/events",
            json=event_payload(occurred_at=occurred),
            headers={"Authorization": f"Bearer {api_key}"},
        )
    totals = purge(db)
    assert totals["events"] == 1
    events = user_client.get(f"/api/v1/projects/{project['id']}/events").json()
    assert events["total"] == 1
    incident = user_client.get(f"/api/v1/projects/{project['id']}/incidents").json()["items"][0]
    assert incident["occurrence_count"] == 2  # aggregates are kept
