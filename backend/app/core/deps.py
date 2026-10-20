"""Request dependencies: who is calling, and what they may touch."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.ratelimit import RateLimiter
from app.core.security import constant_time_equals, sha256_hex
from app.db.session import get_db
from app.models import Project, ProjectApiKey, User, UserSession

SESSION_COOKIE = "tb_session"
CSRF_COOKIE = "tb_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str:
    """Client address, honoring X-Forwarded-For only for the configured proxy hops."""
    hops = get_settings().trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for")
    if hops and forwarded:
        chain = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "unknown"


def rate_limit(limiter: RateLimiter, request: Request, *parts: str) -> None:
    limiter.hit("|".join((client_ip(request), *parts)))


# ---------------------------------------------------------------- browser sessions


def _unauthenticated() -> AppError:
    return AppError(401, "unauthenticated", "Sign in to continue.")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the session cookie; enforce double-submit CSRF on unsafe methods."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated()
    now = datetime.now(UTC)
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == sha256_hex(token), UserSession.expires_at > now
        )
    )
    if session is None:
        raise _unauthenticated()

    if request.method in UNSAFE_METHODS:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not header or not constant_time_equals(cookie, header):
            raise AppError(403, "csrf_failed", "Missing or invalid CSRF token. Reload the page.")

    # Sliding expiry: extend active sessions at most once a day.
    ttl = timedelta(hours=get_settings().session_ttl_hours)
    if session.expires_at - now < ttl - timedelta(days=1):
        session.expires_at = now + ttl
        db.commit()
    return session.user


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    user: User


def get_project_access(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectAccess:
    """Every project-scoped route goes through here (PRD §12: server-side authorization)."""
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise NotFound("project")
    return ProjectAccess(project=project, user=user)


# ---------------------------------------------------------------- SDK / CLI API keys


def get_api_key_project(request: Request, db: Session = Depends(get_db)) -> Project:
    auth = request.headers.get("authorization", "")
    scheme, _, key = auth.partition(" ")
    if scheme.lower() != "bearer" or not key.strip():
        raise AppError(
            401, "invalid_api_key", "Send the project API key as 'Authorization: Bearer <key>'."
        )
    row = db.scalar(
        select(ProjectApiKey).where(
            ProjectApiKey.key_hash == sha256_hex(key.strip()), ProjectApiKey.revoked_at.is_(None)
        )
    )
    if row is None:
        raise AppError(401, "invalid_api_key", "The API key is invalid or has been rotated.")

    # Record usage, but write at most once a minute per key.
    now = datetime.now(UTC)
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=1):
        db.execute(update(ProjectApiKey).where(ProjectApiKey.id == row.id).values(last_used_at=now))
        db.commit()
    return row.project
