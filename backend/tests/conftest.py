import os
from collections.abc import Callable, Iterator

# Point the app at the test database before any app module reads settings.
os.environ.setdefault(
    "TRACEBACK_DATABASE_URL",
    "postgresql+psycopg://traceback:traceback@localhost:5432/traceback_test",
)
os.environ.setdefault("TRACEBACK_ENV", "test")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import ALL_LIMITERS
from app.db.session import engine, get_db
from app.main import app
from tests.target_server import TargetServer


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """Build the schema through the real migrations, not metadata.create_all."""
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    for limiter in ALL_LIMITERS:
        limiter.reset()
    settings = get_settings()
    saved = settings.model_dump()
    yield
    for key, value in saved.items():  # tests may tweak settings
        setattr(settings, key, value)


@pytest.fixture
def db() -> Iterator[Session]:
    """Session bound to an outer transaction that is rolled back after each test."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def make_client(db: Session) -> Iterator[Callable[[], TestClient]]:
    """Factory for independent clients (separate cookie jars) sharing the test transaction."""
    app.dependency_overrides[get_db] = lambda: db
    clients: list[TestClient] = []

    def factory() -> TestClient:
        c = TestClient(app)
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    return make_client()


def sign_up(
    client: TestClient, email: str = "dev@example.com", password: str = "correct-horse-battery"
) -> dict:
    """Register and wire the CSRF header the way the browser app does."""
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = client.cookies["tb_csrf"]
    return response.json()


@pytest.fixture
def user_client(client: TestClient) -> TestClient:
    sign_up(client)
    return client


@pytest.fixture
def project(user_client: TestClient) -> dict:
    response = user_client.post("/api/v1/projects", json={"name": "Checkout API"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def api_key(user_client: TestClient, project: dict) -> str:
    response = user_client.post(f"/api/v1/projects/{project['id']}/api-keys")
    assert response.status_code == 201, response.text
    return response.json()["key"]


@pytest.fixture(scope="session")
def target_server() -> Iterator[TargetServer]:
    server = TargetServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def private_networks() -> None:
    """Local-development mode: 'local' targets may use loopback addresses."""
    get_settings().replay_allow_private_networks = True
