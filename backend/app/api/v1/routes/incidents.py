import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import ProjectAccess, get_project_access
from app.core.errors import error_responses
from app.db.session import get_db
from app.models import Event, Incident
from app.schemas.common import Page
from app.schemas.incidents import EventOut, IncidentOut, IncidentPatch
from app.services import incidents as service
from app.services.incidents import MAX_PAGE_SIZE

router = APIRouter(tags=["incidents"])


@router.get(
    "/projects/{project_id}/incidents",
    response_model=Page[IncidentOut],
    responses=error_responses(404, 422),
)
def list_incidents(
    status: Literal["open", "resolved"] | None = None,
    error_type: str | None = Query(default=None, max_length=255),
    q: str | None = Query(default=None, max_length=200),
    since_days: int | None = Query(default=None, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return service.list_incidents(
        db,
        access.project,
        status=status,
        error_type=error_type,
        q=q,
        since_days=since_days,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/projects/{project_id}/incidents/{incident_id}",
    response_model=IncidentOut,
    responses=error_responses(404),
)
def get_incident(
    incident_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> Incident:
    return service.get_incident(db, access.project, incident_id)


@router.patch(
    "/projects/{project_id}/incidents/{incident_id}",
    response_model=IncidentOut,
    responses=error_responses(404, 422),
)
def update_incident(
    incident_id: uuid.UUID,
    body: IncidentPatch,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> Incident:
    incident = service.set_status(
        db, service.get_incident(db, access.project, incident_id), body.status
    )
    db.commit()
    return incident


@router.get(
    "/projects/{project_id}/incidents/{incident_id}/events",
    response_model=Page[EventOut],
    responses=error_responses(404),
)
def incident_events(
    incident_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = service.get_incident(db, access.project, incident_id)
    return service.list_events(
        db, access.project, incident_id=incident.id, page=page, page_size=page_size
    )


@router.get(
    "/projects/{project_id}/events", response_model=Page[EventOut], responses=error_responses(404)
)
def project_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return service.list_events(db, access.project, incident_id=None, page=page, page_size=page_size)


@router.get(
    "/projects/{project_id}/events/{event_id}",
    response_model=EventOut,
    responses=error_responses(404),
)
def get_event(
    event_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> Event:
    return service.get_event(db, access.project, event_id)
