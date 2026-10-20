from fastapi.testclient import TestClient

from tests.conftest import sign_up
from tests.helpers import event_payload


def test_create_list_rename(user_client: TestClient) -> None:
    created = user_client.post("/api/v1/projects", json={"name": "  Checkout API  "}).json()
    assert created["name"] == "Checkout API" and created["slug"] == "checkout-api"
    assert created["api_key"] is None and created["retention_days"] == 30
    second = user_client.post("/api/v1/projects", json={"name": "Checkout API"}).json()
    assert second["slug"] == "checkout-api-2"

    renamed = user_client.patch(f"/api/v1/projects/{created['id']}", json={"name": "Payments"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Payments"
    assert [p["name"] for p in user_client.get("/api/v1/projects").json()] == [
        "Payments",
        "Checkout API",
    ]


def test_settings_validation(user_client: TestClient, project: dict) -> None:
    url = f"/api/v1/projects/{project['id']}"
    assert user_client.patch(url, json={"retention_days": 0}).status_code == 422
    assert user_client.patch(url, json={"name": ""}).status_code == 422
    rules = user_client.patch(
        url, json={"redaction_rules": [{"field": "ssn"}, {"field": "SSN"}, {"field": "iban"}]}
    )
    assert [r["field"] for r in rules.json()["redaction_rules"]] == ["ssn", "iban"]  # de-duplicated


def test_api_key_is_shown_once_and_stored_hashed(user_client: TestClient, project: dict) -> None:
    created = user_client.post(f"/api/v1/projects/{project['id']}/api-keys").json()
    key = created["key"]
    assert key.startswith("tb_") and len(key) == 51
    assert created["api_key"]["key_prefix"] == key[:9]
    shown = user_client.get(f"/api/v1/projects/{project['id']}").json()
    assert shown["api_key"]["key_prefix"] == key[:9]
    assert key not in str(shown)
    again = user_client.post(f"/api/v1/projects/{project['id']}/api-keys")
    assert again.status_code == 409 and again.json()["error"]["code"] == "key_exists"


def test_rotation_invalidates_the_previous_key(
    user_client: TestClient, project: dict, api_key: str
) -> None:
    send = lambda key: user_client.post(  # noqa: E731
        "/api/v1/ingest/events", json=event_payload(), headers={"Authorization": f"Bearer {key}"}
    )
    assert send(api_key).status_code == 202
    rotated = user_client.post(f"/api/v1/projects/{project['id']}/api-keys/rotate").json()["key"]
    assert rotated != api_key
    old = send(api_key)
    assert old.status_code == 401 and old.json()["error"]["code"] == "invalid_api_key"
    assert send(rotated).status_code == 202


def test_cross_project_access_is_indistinguishable_from_missing(
    make_client, project: dict, api_key: str
) -> None:  # type: ignore[no-untyped-def]
    """PRD §12/§14: guessed or leaked UUIDs from another account must not work."""
    owner = make_client()
    owner.cookies.clear()
    intruder = make_client()
    sign_up(intruder, "mallory@example.com")

    pid = project["id"]
    for method, path in [
        ("GET", f"/api/v1/projects/{pid}"),
        ("PATCH", f"/api/v1/projects/{pid}"),
        ("POST", f"/api/v1/projects/{pid}/api-keys/rotate"),
        ("GET", f"/api/v1/projects/{pid}/stats"),
        ("GET", f"/api/v1/projects/{pid}/incidents"),
        ("GET", f"/api/v1/projects/{pid}/events"),
        ("GET", f"/api/v1/projects/{pid}/targets"),
        ("GET", f"/api/v1/projects/{pid}/regression-cases"),
        ("POST", f"/api/v1/projects/{pid}/replays"),
    ]:
        response = intruder.request(method, path, json={} if method != "GET" else None)
        assert response.status_code in (404, 422), (method, path, response.status_code)
        if response.status_code == 404:
            assert response.json()["error"]["message"] == "The requested project was not found."
    assert intruder.get("/api/v1/projects").json() == []
