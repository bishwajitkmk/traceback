"""Replay targets and the outbound client — an SSRF boundary (PRD §6.6, §12, §14)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.netguard import blocked_reason
from tests.helpers import event_payload
from tests.target_server import TargetServer, state


def add_target(
    client: TestClient,
    project: dict,
    base_url: str,
    environment: str = "local",
    name: str = "Local",
):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/projects/{project['id']}/targets",
        json={"name": name, "base_url": base_url, "environment": environment},
    )


def replay(client: TestClient, project: dict, target_id: str, **request: object):  # type: ignore[no-untyped-def]
    body = {"method": "GET", "path": "/echo", "query": {}, "headers": {}, "body": None} | request
    confirm = body.pop("confirm", False)
    event_id = body.pop("event_id", None)
    return client.post(
        f"/api/v1/projects/{project['id']}/replays",
        json={
            "target_id": target_id,
            "event_id": event_id,
            "request": body,
            "confirm_mutation": confirm,
        },
    )


@pytest.fixture
def local_target(
    user_client: TestClient, project: dict, target_server: TargetServer, private_networks: None
) -> dict:
    response = add_target(user_client, project, target_server.url + "/")
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- address rules


@pytest.mark.parametrize(
    ("ip", "allow_private", "blocked"),
    [
        ("93.184.215.14", False, False),
        ("169.254.169.254", True, True),  # metadata: always blocked
        ("::ffff:169.254.169.254", True, True),  # IPv4-mapped bypass attempt
        ("fd00:ec2::254", True, True),
        ("100.100.100.200", True, True),
        ("127.0.0.1", False, True),
        ("127.0.0.1", True, False),
        ("10.1.2.3", False, True),
        ("192.168.1.10", False, True),
        ("172.20.0.5", False, True),
        ("100.64.0.1", False, True),  # carrier-grade NAT
        ("::1", False, True),
        ("0.0.0.0", True, True),
        ("224.0.0.1", True, True),
        ("fe80::1", True, True),
    ],
)
def test_blocked_reason(ip: str, allow_private: bool, blocked: bool) -> None:
    assert (blocked_reason(ip, allow_private) is not None) is blocked


@pytest.mark.parametrize(
    ("url", "environment", "private_enabled", "ok"),
    [
        ("https://staging.example.com", "staging", False, True),
        ("http://169.254.169.254", "local", True, False),
        ("http://metadata.google.internal", "staging", False, False),
        ("http://10.0.0.5:8080", "staging", True, False),  # private only for *local* targets
        ("http://localhost:9000", "local", False, False),  # dev mode off
        ("http://localhost:9000", "local", True, True),
        ("http://127.0.0.1:9000", "local", True, True),
        ("http://user:pw@staging.example.com", "staging", False, False),
        ("https://staging.example.com/?a=1", "staging", False, False),
        ("ftp://staging.example.com", "staging", False, False),
        ("staging.example.com", "staging", False, False),
    ],
)
def test_target_registration_rules(
    user_client: TestClient,
    project: dict,
    url: str,
    environment: str,
    private_enabled: bool,
    ok: bool,
) -> None:
    get_settings().replay_allow_private_networks = private_enabled
    response = add_target(user_client, project, url, environment)
    assert (response.status_code == 201) is ok, response.text


def test_production_targets_are_rejected(user_client: TestClient, project: dict) -> None:
    response = add_target(user_client, project, "https://api.example.com", "production")
    assert response.status_code == 422


def test_target_crud(user_client: TestClient, project: dict, local_target: dict) -> None:
    base = f"/api/v1/projects/{project['id']}/targets"
    assert not local_target["base_url"].endswith("/")  # normalized at registration
    assert (
        add_target(user_client, project, local_target["base_url"]).status_code == 422
    )  # name taken
    patched = user_client.patch(
        f"{base}/{local_target['id']}", json={"enabled": False, "name": "Dev"}
    ).json()
    assert patched["enabled"] is False and patched["name"] == "Dev"
    moved = user_client.patch(f"{base}/{local_target['id']}", json={"environment": "staging"})
    assert moved.status_code == 422  # loopback is not allowed once it is no longer "local"
    assert user_client.delete(f"{base}/{local_target['id']}").status_code == 204
    assert user_client.get(base).json() == []


# ---------------------------------------------------------------- executing replays


def test_replay_records_response_and_never_forwards_credentials(
    user_client: TestClient, project: dict, local_target: dict, api_key: str
) -> None:
    user_client.post(
        "/api/v1/ingest/events",
        json=event_payload(),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    event = user_client.get(f"/api/v1/projects/{project['id']}/events").json()["items"][0]

    response = replay(
        user_client,
        project,
        local_target["id"],
        event_id=event["id"],
        query={"tag": ["a", "b"]},
        headers={
            "Authorization": "Bearer stolen",
            "Cookie": "sid=1",
            "X-Api-Key": "k",
            "X-Custom": "yes",
        },
    )
    assert response.status_code == 201, response.text
    execution = response.json()
    assert execution["status"] == "completed" and execution["kind"] == "replay"
    echoed = execution["response_summary"]["body"]
    assert echoed["method"] == "GET" and echoed["path"] == "/echo"
    sent = echoed["headers"]
    assert "authorization" not in sent and "cookie" not in sent and "x-api-key" not in sent
    assert sent["x-custom"] == "yes" and sent["x-traceback-replay"] == "1"
    assert execution["request_summary"]["url"].endswith("/echo?tag=a&tag=b")

    history = user_client.get(
        f"/api/v1/projects/{project['id']}/replays", params={"event_id": event["id"]}
    ).json()
    assert [h["id"] for h in history] == [execution["id"]]
    assert (
        user_client.get(f"/api/v1/projects/{project['id']}/replays/{execution['id']}").status_code
        == 200
    )


def test_mutating_replays_require_explicit_confirmation(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    unconfirmed = replay(
        user_client,
        project,
        local_target["id"],
        method="POST",
        path="/checkout",
        body={"quantity": 0},
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["error"]["code"] == "confirmation_required"

    state["fixed"] = False
    confirmed = replay(
        user_client,
        project,
        local_target["id"],
        method="POST",
        path="/checkout",
        body={"quantity": 0},
        confirm=True,
    )
    assert confirmed.json()["response_summary"]["status"] == 500


@pytest.mark.parametrize(
    "path", ["//evil.example.com/x", "http://evil.example.com/", "/a\\b", "relative", "/a b"]
)
def test_path_cannot_change_the_host(
    user_client: TestClient, project: dict, local_target: dict, path: str
) -> None:
    response = replay(user_client, project, local_target["id"], path=path)
    assert response.status_code == 422


def test_unknown_disabled_and_foreign_targets(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    import uuid

    assert replay(user_client, project, str(uuid.uuid4())).status_code == 404
    user_client.patch(
        f"/api/v1/projects/{project['id']}/targets/{local_target['id']}", json={"enabled": False}
    )
    disabled = replay(user_client, project, local_target["id"])
    assert disabled.status_code == 409 and disabled.json()["error"]["code"] == "target_disabled"


def test_redirects_outside_the_target_are_not_followed(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    out = replay(user_client, project, local_target["id"], path="/redirect-out").json()
    assert out["status"] == "error"
    assert "not followed" in out["error_summary"]
    inside = replay(user_client, project, local_target["id"], path="/redirect-in").json()
    assert inside["status"] == "completed"
    assert inside["response_summary"]["body"]["query"] == {"from": "redirect"}


def test_connect_time_check_blocks_private_addresses(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    """A target that passed registration is re-checked on every connection
    (covers DNS answers changing after registration)."""
    get_settings().replay_allow_private_networks = False
    blocked = replay(user_client, project, local_target["id"]).json()
    assert blocked["status"] == "error"
    assert "Destination blocked" in blocked["error_summary"]


def test_response_size_and_time_are_bounded(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    big = replay(user_client, project, local_target["id"], path="/big").json()
    assert big["response_summary"]["body_truncated"] is True
    assert len(big["response_summary"]["body"]) == get_settings().replay_max_response_bytes

    get_settings().replay_timeout_seconds = 0.5
    slow = replay(user_client, project, local_target["id"], path="/slow").json()
    assert slow["status"] == "error" and "Timed out" in slow["error_summary"]


def test_oversized_replay_body_is_rejected(
    user_client: TestClient, project: dict, local_target: dict
) -> None:
    response = replay(
        user_client,
        project,
        local_target["id"],
        method="PUT",
        body={"x": "y" * 70_000},
        confirm=True,
    )
    assert response.status_code == 413
