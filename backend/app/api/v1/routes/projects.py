from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import ProjectAccess, get_current_user, get_project_access
from app.core.errors import error_responses
from app.db.session import get_db
from app.models import User
from app.schemas.projects import ApiKeyCreated, ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.stats import ProjectStats
from app.services import projects as service
from app.services.stats import project_stats

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ProjectOut]:
    return [service.to_out(db, p) for p in service.list_for(db, user)]


@router.post(
    "/projects", response_model=ProjectOut, status_code=201, responses=error_responses(422)
)
def create_project(
    body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProjectOut:
    project = service.create(db, user, body.name)
    db.commit()
    return service.to_out(db, project)


@router.get("/projects/{project_id}", response_model=ProjectOut, responses=error_responses(404))
def get_project(
    access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> ProjectOut:
    return service.to_out(db, access.project)


@router.patch(
    "/projects/{project_id}", response_model=ProjectOut, responses=error_responses(404, 422)
)
def update_project(
    body: ProjectUpdate,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = service.update_project(db, access.project, body)
    db.commit()
    return service.to_out(db, project)


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
    responses=error_responses(404, 409),
)
def create_api_key(
    access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> ApiKeyCreated:
    created = service.create_key(db, access.project)
    db.commit()
    return created


@router.post(
    "/projects/{project_id}/api-keys/rotate",
    response_model=ApiKeyCreated,
    responses=error_responses(404),
)
def rotate_api_key(
    access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> ApiKeyCreated:
    created = service.rotate_key(db, access.project)
    db.commit()
    return created


@router.get(
    "/projects/{project_id}/stats", response_model=ProjectStats, responses=error_responses(404)
)
def stats(
    days: int = Query(default=14, ge=1, le=90),
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ProjectStats:
    return project_stats(db, access.project, days)
