"""Integrity rules the database itself must enforce, independent of service code."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Event,
    Incident,
    Project,
    ProjectApiKey,
    ReplayExecution,
    ReplayTarget,
    User,
)


@pytest.fixture
def project(db: Session) -> Project:
    user = User(email="dev@example.com", password_hash="x")
    db.add(user)
    db.flush()
    project = Project(owner_id=user.id, name="Checkout", slug="checkout")
    db.add(project)
    db.flush()
    return project


def _incident(project: Project, fingerprint: str = "fp-1") -> Incident:
    now = datetime.now(UTC)
    return Incident(
        project_id=project.id,
        fingerprint=fingerprint,
        title="ZeroDivisionError in /checkout",
        error_type="ZeroDivisionError",
        error_message="division by zero",
        first_seen_at=now,
        last_seen_at=now,
    )


def _assert_rejected(db: Session, obj: object) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(obj)
        db.flush()


def test_server_defaults_applied(db: Session, project: Project) -> None:
    incident = _incident(project)
    db.add(incident)
    db.flush()
    db.refresh(incident)
    db.refresh(project)
    assert incident.status == "open"
    assert incident.occurrence_count == 0
    assert project.retention_days == 30
    assert project.redaction_rules == []


def test_incident_fingerprint_unique_per_project(db: Session, project: Project) -> None:
    db.add(_incident(project))
    db.flush()
    _assert_rejected(db, _incident(project))


def test_incident_status_must_be_known(db: Session, project: Project) -> None:
    incident = _incident(project)
    incident.status = "ignored"
    _assert_rejected(db, incident)


def test_duplicate_idempotency_key_rejected(db: Session, project: Project) -> None:
    def event(key: str | None) -> Event:
        return Event(
            project_id=project.id,
            event_type="exception",
            idempotency_key=key,
            occurred_at=datetime.now(UTC),
        )

    db.add_all([event("evt-1"), event(None), event(None)])
    db.flush()  # NULL keys never collide
    _assert_rejected(db, event("evt-1"))


def test_only_one_active_api_key_per_project(db: Session, project: Project) -> None:
    first = ProjectApiKey(project_id=project.id, key_prefix="tb_aaaa", key_hash="a" * 64)
    db.add(first)
    db.flush()
    _assert_rejected(
        db, ProjectApiKey(project_id=project.id, key_prefix="tb_bbbb", key_hash="b" * 64)
    )

    # Rotation: revoke the old key, then a new active key is allowed.
    first.revoked_at = datetime.now(UTC)
    db.add(ProjectApiKey(project_id=project.id, key_prefix="tb_cccc", key_hash="c" * 64))
    db.flush()
    active = db.scalar(
        select(func.count())
        .select_from(ProjectApiKey)
        .where(ProjectApiKey.project_id == project.id, ProjectApiKey.revoked_at.is_(None))
    )
    assert active == 1


def test_production_replay_target_rejected(db: Session, project: Project) -> None:
    _assert_rejected(
        db,
        ReplayTarget(
            project_id=project.id,
            name="prod",
            base_url="https://api.example.com",
            environment="production",
        ),
    )


def test_regression_run_requires_case(db: Session, project: Project) -> None:
    _assert_rejected(
        db,
        ReplayExecution(project_id=project.id, kind="regression_run", request_summary={}),
    )
