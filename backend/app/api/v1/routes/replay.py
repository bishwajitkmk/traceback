import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import ProjectAccess, get_project_access
from app.core.errors import NotFound, ValidationFailed, error_responses
from app.db.session import get_db
from app.models import ReplayExecution, ReplayTarget
from app.schemas.replay import CreateReplay, ExecutionOut, TargetIn, TargetOut, TargetPatch
from app.services import executions
from app.services.incidents import get_event
from app.services.netguard import validate_target_url

router = APIRouter(tags=["replay"])


def _target(db: Session, access: ProjectAccess, target_id: uuid.UUID) -> ReplayTarget:
    target = db.scalar(
        select(ReplayTarget).where(
            ReplayTarget.id == target_id, ReplayTarget.project_id == access.project.id
        )
    )
    if target is None:
        raise NotFound("replay target")
    return target


def _commit_unique_name(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValidationFailed("name", "A target with this name already exists.") from None


@router.get("/projects/{project_id}/targets", response_model=list[TargetOut])
def list_targets(
    access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> list[ReplayTarget]:
    return list(
        db.scalars(
            select(ReplayTarget)
            .where(ReplayTarget.project_id == access.project.id)
            .order_by(ReplayTarget.created_at, ReplayTarget.id)
        )
    )


@router.post(
    "/projects/{project_id}/targets",
    response_model=TargetOut,
    status_code=201,
    responses=error_responses(404, 422),
)
def create_target(
    body: TargetIn,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ReplayTarget:
    base_url = validate_target_url(
        body.base_url, body.environment, get_settings().replay_allow_private_networks
    )
    target = ReplayTarget(
        project_id=access.project.id,
        name=body.name,
        base_url=base_url,
        environment=body.environment,
        enabled=body.enabled,
    )
    db.add(target)
    _commit_unique_name(db)
    db.refresh(target)
    return target


@router.patch(
    "/projects/{project_id}/targets/{target_id}",
    response_model=TargetOut,
    responses=error_responses(404, 422),
)
def update_target(
    target_id: uuid.UUID,
    body: TargetPatch,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ReplayTarget:
    target = _target(db, access, target_id)
    environment = body.environment or target.environment
    # Re-validate the URL whenever it or the environment changes.
    if body.base_url is not None or body.environment is not None:
        target.base_url = validate_target_url(
            body.base_url or target.base_url,
            environment,
            get_settings().replay_allow_private_networks,
        )
    target.environment = environment
    if body.name is not None:
        target.name = body.name
    if body.enabled is not None:
        target.enabled = body.enabled
    target.updated_at = datetime.now(UTC)
    _commit_unique_name(db)
    db.refresh(target)
    return target


@router.delete(
    "/projects/{project_id}/targets/{target_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(404),
)
def delete_target(
    target_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> Response:
    target = _target(db, access, target_id)
    db.execute(
        update(ReplayExecution).where(ReplayExecution.target_id == target.id).values(target_id=None)
    )
    db.delete(target)
    db.commit()
    return Response(status_code=204)


@router.post(
    "/projects/{project_id}/replays",
    response_model=ExecutionOut,
    status_code=201,
    responses=error_responses(404, 409, 413, 422, 429),
)
def create_replay(
    body: CreateReplay,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ReplayExecution:
    if body.event_id is not None:
        get_event(db, access.project, body.event_id)  # 404 unless it belongs to this project
    target = executions.get_target(db, access.project, body.target_id)
    execution = executions.execute(
        db,
        access.project,
        access.user,
        target,
        body.request,
        confirm_mutation=body.confirm_mutation,
        kind="replay",
        event_id=body.event_id,
    )
    db.commit()
    return execution


@router.get("/projects/{project_id}/replays", response_model=list[ExecutionOut])
def list_replays(
    event_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> list[ReplayExecution]:
    query = select(ReplayExecution).where(
        ReplayExecution.project_id == access.project.id, ReplayExecution.kind == "replay"
    )
    if event_id is not None:
        query = query.where(ReplayExecution.event_id == event_id)
    return list(
        db.scalars(
            query.order_by(ReplayExecution.started_at.desc(), ReplayExecution.id).limit(limit)
        )
    )


@router.get(
    "/projects/{project_id}/replays/{replay_id}",
    response_model=ExecutionOut,
    responses=error_responses(404),
)
def get_replay(
    replay_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ReplayExecution:
    execution = db.scalar(
        select(ReplayExecution).where(
            ReplayExecution.id == replay_id, ReplayExecution.project_id == access.project.id
        )
    )
    if execution is None:
        raise NotFound("replay")
    return execution
