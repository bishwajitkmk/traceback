import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import engine
from app.models import Incident, Project, User
from app.schemas.ingest import IngestEvent
from app.services.ingestion import ingest
from tests.helpers import event_payload


def post(client: TestClient, key: str, body: object, **kwargs: object):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/ingest/events", json=body, headers={"Authorization": f"Bearer {key}"}, **kwargs
    )


def incidents(client: TestClient, project: dict) -> list[dict]:
    return client.get(f"/api/v1/projects/{project['id']}/incidents").json()["items"]


def test_event_creates_an_incident(user_client: TestClient, project: dict, api_key: str) -> None:
    response = post(user_client, api_key, event_payload())
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["duplicate"] is False and result["incident_id"]

    [incident] = incidents(user_client, project)
    assert incident["title"] == "ZeroDivisionError in POST /checkout"
    assert incident["occurrence_count"] == 1 and incident["status"] == "open"
    assert incident["normalized_route"] == "/checkout" and len(incident["fingerprint"]) == 64


def test_duplicate_delivery_does_not_change_counts(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    event = event_payload()
    first = post(user_client, api_key, event).json()
    second = post(user_client, api_key, event).json()
    assert second == {**first, "duplicate": True}
    assert incidents(user_client, project)[0]["occurrence_count"] == 1


def test_grouping_ignores_line_numbers_but_not_location(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    moved = event_payload()
    moved["exception"]["frames"][-1]["lineno"] = 99  # same function, edited file
    other = event_payload()
    other["exception"]["frames"][-1]["function"] = "discount"
    for e in (event_payload(), moved, other):
        assert post(user_client, api_key, e).status_code == 202
    counts = sorted(i["occurrence_count"] for i in incidents(user_client, project))
    assert counts == [1, 2]


def test_last_seen_and_message_track_newest_event(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    now = datetime.now(UTC)
    post(user_client, api_key, event_payload(occurred_at=now.isoformat()))
    older = event_payload(occurred_at=(now - timedelta(hours=3)).isoformat())
    older["exception"]["message"] = "older message"
    post(user_client, api_key, older)
    [incident] = incidents(user_client, project)
    assert incident["error_message"] == "division by zero"
    assert incident["first_seen_at"].startswith((now - timedelta(hours=3)).isoformat()[:16])
    assert incident["last_seen_at"].startswith(now.isoformat()[:16])


def test_sensitive_data_is_redacted_before_persistence(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    user_client.patch(
        f"/api/v1/projects/{project['id']}", json={"redaction_rules": [{"field": "cart_id"}]}
    )
    event = event_payload()
    event["request"]["query"]["access_token"] = "q-secret"
    event["response"]["headers"]["Set-Cookie"] = "sid=server-secret"
    post(user_client, api_key, event)
    [stored] = user_client.get(f"/api/v1/projects/{project['id']}/events").json()["items"]
    data = stored["request_data"]
    assert data["headers"]["authorization"] == "[REDACTED]"
    assert data["headers"]["cookie"] == "[REDACTED]"
    assert data["headers"]["content-type"] == "application/json"
    assert data["query"]["access_token"] == "[REDACTED]" and data["query"]["tag"] == ["a", "b"]
    assert data["body"]["card_number"] == "[REDACTED]"
    assert data["body"]["nested"]["password"] == "[REDACTED]"
    assert data["body"]["cart_id"] == "[REDACTED]"  # project rule
    assert data["body"]["quantity"] == 0
    assert data["response_headers"]["set-cookie"] == "[REDACTED]"
    for secret in ("prod-secret", "session=abc", "4111111111111111", "q-secret", "server-secret"):
        assert secret not in str(stored)


def test_body_capture_disabled_is_distinct_from_empty(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    event = event_payload()
    event["request"]["body_captured"] = False
    event["request"]["body"] = {"should": "not be stored"}
    post(user_client, api_key, event)
    [stored] = user_client.get(f"/api/v1/projects/{project['id']}/events").json()["items"]
    assert stored["request_data"]["body_captured"] is False
    assert stored["request_data"]["body"] is None


def test_http_error_events_group_by_status_and_route(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    event = event_payload(event_type="http_error", exception=None)
    event["response"]["status"] = 503
    assert post(user_client, api_key, event).status_code == 202
    [incident] = incidents(user_client, project)
    assert incident["error_type"] == "HTTP 503"
    assert incident["error_message"] == "Request POST /checkout returned 503"


def test_new_occurrence_reopens_a_resolved_incident(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    post(user_client, api_key, event_payload())
    [incident] = incidents(user_client, project)
    user_client.patch(
        f"/api/v1/projects/{project['id']}/incidents/{incident['id']}", json={"status": "resolved"}
    )
    later = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    post(user_client, api_key, event_payload(occurred_at=later))
    [again] = incidents(user_client, project)
    assert (
        again["status"] == "open"
        and again["resolved_at"] is None
        and again["occurrence_count"] == 2
    )


def test_validation_errors_are_specific(user_client: TestClient, api_key: str) -> None:
    bad = event_payload(occurred_at="2026-10-20T12:00:00")  # no timezone
    bad["event_type"] = "exception"
    del bad["exception"]
    response = post(user_client, api_key, bad)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert any("occurred_at" in d["field"] for d in response.json()["error"]["details"])

    not_json = user_client.post(
        "/api/v1/ingest/events",
        content=b"{nope",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    assert not_json.status_code == 422


def test_oversized_events_are_rejected(user_client: TestClient, api_key: str) -> None:
    event = event_payload()
    event["request"]["body"] = {"blob": "x" * 300_000}
    response = post(user_client, api_key, event)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer tb_" + "0" * 48])
def test_invalid_api_keys(client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    response = client.post("/api/v1/ingest/events", json=event_payload(), headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_ingestion_updates_key_last_used(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    post(user_client, api_key, event_payload())
    shown = user_client.get(f"/api/v1/projects/{project['id']}").json()
    assert shown["api_key"]["last_used_at"] is not None


def test_concurrent_and_duplicate_delivery_keeps_counts_exact() -> None:
    """Real commits from parallel sessions: the database must serialize correctly."""
    with Session(engine) as setup:
        user = User(
            email=f"conc-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x" * 12)
        )
        setup.add(user)
        setup.flush()
        project = Project(
            owner_id=user.id, name="Concurrency", slug="concurrency", redaction_rules=[]
        )
        setup.add(project)
        setup.commit()
        project_id, user_id = project.id, user.id

    unique = [event_payload() for _ in range(12)]
    deliveries = unique + [copy.deepcopy(e) for e in unique[:6]] * 2  # retries of half of them

    def deliver(payload: dict) -> bool:
        with Session(engine) as s:
            proj = s.get(Project, project_id)
            assert proj is not None
            result = ingest(s, proj, IngestEvent.model_validate(payload))
            s.commit()
            return result.duplicate

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            duplicates = sum(pool.map(deliver, deliveries))
        with Session(engine) as check:
            [count] = check.scalars(
                select(Incident.occurrence_count).where(Incident.project_id == project_id)
            ).all()
        assert count == len(unique)
        assert duplicates == len(deliveries) - len(unique)
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))  # cascades
            cleanup.commit()
