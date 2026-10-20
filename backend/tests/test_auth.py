from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import User, UserSession
from tests.conftest import sign_up


def test_register_sets_session_and_csrf_cookies(client: TestClient) -> None:
    user = sign_up(client, "Ada@Example.com")
    assert user["email"] == "ada@example.com"  # normalized
    assert "tb_session" in client.cookies and "tb_csrf" in client.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]


def test_session_cookie_is_httponly_and_lax(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "c@example.com", "password": "correct-horse-battery"},
    )
    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("tb_session="))
    csrf = next(c for c in cookies if c.startswith("tb_csrf="))
    assert "HttpOnly" in session and "samesite=lax" in session.lower()
    assert "HttpOnly" not in csrf  # the frontend must read it


def test_passwords_are_hashed_with_argon2(client: TestClient, db: Session) -> None:
    sign_up(client, "h@example.com", "correct-horse-battery")
    stored = db.scalar(select(User.password_hash).where(User.email == "h@example.com"))
    assert stored is not None and stored.startswith("$argon2id$")
    assert "correct-horse-battery" not in stored


def test_registration_validation_and_duplicates(client: TestClient) -> None:
    bad = client.post("/api/v1/auth/register", json={"email": "nope", "password": "short"})
    assert bad.status_code == 422
    fields = {d["field"] for d in bad.json()["error"]["details"]}
    assert fields == {"body.email", "body.password"}

    sign_up(client, "dup@example.com")
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@example.com", "password": "correct-horse-battery"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "email_taken"


def test_login_logout(make_client) -> None:  # type: ignore[no-untyped-def]
    sign_up(make_client(), "l@example.com", "correct-horse-battery")
    c = make_client()
    wrong = c.post("/api/v1/auth/login", json={"email": "l@example.com", "password": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_credentials"
    unknown = c.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "nope"})
    assert unknown.json()["error"] == wrong.json()["error"]  # no user enumeration

    assert (
        c.post(
            "/api/v1/auth/login",
            json={"email": "l@example.com", "password": "correct-horse-battery"},
        ).status_code
        == 200
    )
    assert c.get("/api/v1/auth/me").status_code == 200
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_logout_invalidates_the_session_server_side(client: TestClient) -> None:
    sign_up(client)
    stolen = client.cookies["tb_session"]
    client.post("/api/v1/auth/logout")
    client.cookies.set("tb_session", stolen)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, db: Session) -> None:
    sign_up(client)
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_protected_routes_require_auth(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_unsafe_requests_need_matching_csrf_token(client: TestClient) -> None:
    sign_up(client)
    token = client.headers.pop("X-CSRF-Token")
    missing = client.post("/api/v1/projects", json={"name": "P"})
    assert missing.status_code == 403 and missing.json()["error"]["code"] == "csrf_failed"
    wrong = client.post("/api/v1/projects", json={"name": "P"}, headers={"X-CSRF-Token": "forged"})
    assert wrong.status_code == 403
    ok = client.post("/api/v1/projects", json={"name": "P"}, headers={"X-CSRF-Token": token})
    assert ok.status_code == 201
    assert client.get("/api/v1/projects").status_code == 200  # safe methods need no token


def test_login_is_rate_limited(client: TestClient) -> None:
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "r@example.com", "password": "nope"})
    limited = client.post("/api/v1/auth/login", json={"email": "r@example.com", "password": "nope"})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_waitlist_accepts_and_never_reveals_existing_signups(client: TestClient) -> None:
    body = {"email": "early@example.com", "source": "landing"}
    assert client.post("/api/v1/waitlist", json=body).status_code == 202
    assert client.post("/api/v1/waitlist", json=body).status_code == 202
    assert client.post("/api/v1/waitlist", json={"email": "bad"}).status_code == 422
