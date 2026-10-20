import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Event, Incident, Project

MAX_PAGE_SIZE = 100


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _page[T](
    db: Session, query: Select[tuple[T]], page: int, page_size: int, *order: Any
) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = list(db.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def list_incidents(
    db: Session,
    project: Project,
    *,
    status: str | None,
    error_type: str | None,
    q: str | None,
    since_days: int | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    query = select(Incident).where(Incident.project_id == project.id)
    if status:
        query = query.where(Incident.status == status)
    if error_type:
        query = query.where(Incident.error_type == error_type)
    if since_days:
        query = query.where(Incident.last_seen_at >= datetime.now(UTC) - timedelta(days=since_days))
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        query = query.where(
            or_(
                Incident.title.ilike(pattern, escape="\\"),
                Incident.error_message.ilike(pattern, escape="\\"),
                Incident.normalized_route.ilike(pattern, escape="\\"),
            )
        )
    # Deterministic ordering: most recent first, id as tiebreaker.
    return _page(db, query, page, page_size, Incident.last_seen_at.desc(), Incident.id)


def get_incident(db: Session, project: Project, incident_id: uuid.UUID) -> Incident:
    incident = db.scalar(
        select(Incident).where(Incident.id == incident_id, Incident.project_id == project.id)
    )
    if incident is None:
        raise NotFound("incident")
    return incident


def set_status(db: Session, incident: Incident, status: str) -> Incident:
    if incident.status != status:
        incident.status = status
        incident.resolved_at = datetime.now(UTC) if status == "resolved" else None
        incident.updated_at = datetime.now(UTC)
        db.flush()
    return incident


def list_events(
    db: Session,
    project: Project,
    *,
    incident_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    query = select(Event).where(Event.project_id == project.id)
    if incident_id is not None:
        query = query.where(Event.incident_id == incident_id)
    return _page(db, query, page, page_size, Event.occurred_at.desc(), Event.id)


def get_event(db: Session, project: Project, event_id: uuid.UUID) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id, Event.project_id == project.id))
    if event is None:
        raise NotFound("event")
    return event
