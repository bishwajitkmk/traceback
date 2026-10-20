"""Event ingestion: redact, fingerprint, persist, aggregate (PRD §6.3).

Correctness under retries and concurrency comes from the database:
- the event insert is idempotent on (project_id, idempotency_key);
- the incident upsert is a single INSERT … ON CONFLICT DO UPDATE, so counts are
  incremented atomically and only for events that were actually inserted.
"""

import hashlib
import uuid
from typing import Any

from sqlalchemy import and_, case, func, null, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.redaction import Redactor
from app.models import Event, Incident, Project
from app.schemas.ingest import IngestEvent, IngestResult

MAX_MESSAGE = 2000


def _error_identity(event: IngestEvent) -> tuple[str, str]:
    if event.exception is not None:
        return event.exception.type, event.exception.message
    status = event.response.status if event.response else 0
    req = event.request
    where = f" {req.method.upper()} {req.route or req.path}" if req else ""
    return f"HTTP {status}", f"Request{where} returned {status}"


def _top_in_app_frame(event: IngestEvent) -> str:
    if event.exception is None:
        return ""
    frames = event.exception.frames
    in_app = [f for f in frames if f.in_app] or frames
    if not in_app:
        return ""
    top = in_app[-1]  # most recent call last
    return f"{top.filename}:{top.function}"


def fingerprint(error_type: str, method: str | None, route: str | None, frame: str) -> str:
    """Stable grouping key. Line numbers are excluded so unrelated edits don't split incidents."""
    raw = "|".join((error_type, method or "", route or "", frame))
    return hashlib.sha256(raw.encode()).hexdigest()


def _lower_keys(headers: dict[str, str] | None) -> dict[str, str] | None:
    return None if headers is None else {k.lower(): v for k, v in headers.items()}


def _request_data(event: IngestEvent, redactor: Redactor) -> dict[str, Any] | None:
    req, resp = event.request, event.response
    if req is None:
        return None
    return {
        "path": req.path,
        "query": redactor.redact(req.query),
        "headers": redactor.redact(_lower_keys(req.headers)),
        "body_captured": req.body_captured,
        "body": redactor.redact(req.body) if req.body_captured else None,
        "body_truncated": req.body_truncated,
        "response_headers": redactor.redact(_lower_keys(resp.headers)) if resp else None,
        "response_body": redactor.redact(resp.body) if resp else None,
    }


def ingest(db: Session, project: Project, event: IngestEvent) -> IngestResult:
    redactor = Redactor(rule["field"] for rule in project.redaction_rules)
    req = event.request
    method = req.method.upper() if req else None
    route = (req.route or req.path) if req else None
    error_type, message = _error_identity(event)
    message = message[:MAX_MESSAGE]
    occurred = event.occurred_at

    event_id = db.scalar(
        pg_insert(Event)
        .values(
            id=uuid.uuid4(),
            project_id=project.id,
            incident_id=None,
            idempotency_key=str(event.event_id),
            event_type=event.event_type,
            correlation_id=event.correlation_id,
            environment=event.environment,
            release=event.release,
            request_method=method,
            normalized_route=route,
            request_data=_request_data(event, redactor),
            response_status=event.response.status if event.response else None,
            duration_ms=event.duration_ms,
            exception_data=event.exception.model_dump() if event.exception else None,
            occurred_at=occurred,
        )
        .on_conflict_do_nothing(index_elements=["project_id", "idempotency_key"])
        .returning(Event.id)
    )
    if event_id is None:
        existing = db.scalar(
            select(Event.incident_id).where(
                Event.project_id == project.id, Event.idempotency_key == str(event.event_id)
            )
        )
        return IngestResult(event_id=event.event_id, incident_id=existing, duplicate=True)

    insert = pg_insert(Incident).values(
        id=uuid.uuid4(),
        project_id=project.id,
        fingerprint=fingerprint(error_type, method, route, _top_in_app_frame(event)),
        title=(f"{error_type} in {method} {route}" if req else error_type)[:500],
        error_type=error_type[:255],
        error_message=message,
        normalized_route=route,
        status="open",
        occurrence_count=1,
        first_seen_at=occurred,
        last_seen_at=occurred,
    )
    newer = insert.excluded.last_seen_at >= Incident.last_seen_at
    # A new occurrence after resolution reopens the incident (recurrence).
    recurred = and_(
        Incident.status == "resolved", insert.excluded.last_seen_at > Incident.resolved_at
    )
    incident_id = db.scalar(
        insert.on_conflict_do_update(
            index_elements=["project_id", "fingerprint"],
            set_={
                "occurrence_count": Incident.occurrence_count + 1,
                "first_seen_at": func.least(Incident.first_seen_at, insert.excluded.first_seen_at),
                "last_seen_at": func.greatest(Incident.last_seen_at, insert.excluded.last_seen_at),
                "error_message": case(
                    (newer, insert.excluded.error_message), else_=Incident.error_message
                ),
                "status": case((recurred, "open"), else_=Incident.status),
                "resolved_at": case((recurred, null()), else_=Incident.resolved_at),
                "updated_at": func.now(),
            },
        ).returning(Incident.id)
    )
    db.execute(update(Event).where(Event.id == event_id).values(incident_id=incident_id))
    return IngestResult(event_id=event.event_id, incident_id=incident_id, duplicate=False)
