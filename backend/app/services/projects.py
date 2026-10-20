import re
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import API_KEY_DISPLAY_CHARS, new_api_key, sha256_hex
from app.models import Project, ProjectApiKey, User
from app.schemas.projects import ApiKeyCreated, ApiKeySummary, ProjectOut, ProjectUpdate


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "project"


def active_key(db: Session, project: Project) -> ProjectApiKey | None:
    return db.scalar(
        select(ProjectApiKey).where(
            ProjectApiKey.project_id == project.id, ProjectApiKey.revoked_at.is_(None)
        )
    )


def to_out(db: Session, project: Project) -> ProjectOut:
    key = active_key(db, project)
    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        retention_days=project.retention_days,
        redaction_rules=project.redaction_rules,
        api_key=ApiKeySummary.model_validate(key) if key else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def list_for(db: Session, user: User) -> list[Project]:
    return list(
        db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at))
    )


def create(db: Session, user: User, name: str) -> Project:
    base = _slugify(name)
    taken = set(db.scalars(select(Project.slug).where(Project.owner_id == user.id)))
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    project = Project(owner_id=user.id, name=name, slug=slug, retention_days=30, redaction_rules=[])
    db.add(project)
    db.flush()
    db.refresh(project)
    return project


def update_project(db: Session, project: Project, patch: ProjectUpdate) -> Project:
    if patch.name is not None:
        project.name = patch.name
    if patch.retention_days is not None:
        project.retention_days = patch.retention_days
    if patch.redaction_rules is not None:
        seen: set[str] = set()
        rules = []
        for rule in patch.redaction_rules:
            if rule.field.lower() not in seen:
                seen.add(rule.field.lower())
                rules.append({"field": rule.field})
        project.redaction_rules = rules
    project.updated_at = datetime.now(UTC)
    db.flush()
    return project


def _issue_key(db: Session, project: Project) -> ApiKeyCreated:
    plaintext = new_api_key()
    key = ProjectApiKey(
        project_id=project.id,
        key_prefix=plaintext[:API_KEY_DISPLAY_CHARS],
        key_hash=sha256_hex(plaintext),
    )
    db.add(key)
    db.flush()
    db.refresh(key)
    return ApiKeyCreated(key=plaintext, api_key=ApiKeySummary.model_validate(key))


def create_key(db: Session, project: Project) -> ApiKeyCreated:
    if active_key(db, project) is not None:
        raise AppError(409, "key_exists", "This project already has a key. Rotate it instead.")
    return _issue_key(db, project)


def rotate_key(db: Session, project: Project) -> ApiKeyCreated:
    """Revoke the active key and issue a new one in the same transaction.

    The partial unique index (one active key per project) makes a concurrent
    double-rotate fail instead of leaving two valid keys.
    """
    db.execute(
        update(ProjectApiKey)
        .where(ProjectApiKey.project_id == project.id, ProjectApiKey.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return _issue_key(db, project)
