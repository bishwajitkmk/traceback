import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectAccess, get_api_key_project, get_project_access, rate_limit
from app.core.errors import error_responses
from app.core.ratelimit import ci_limiter
from app.db.session import get_db
from app.models import Project, RegressionCase, ReplayExecution
from app.schemas.cases import CaseIn, CaseOut, CasePatch, CiCase, CiRunReport, RunCase
from app.schemas.replay import ExecutionOut, RequestDefinition
from app.services import cases as service
from app.services import executions

router = APIRouter(tags=["regression cases"])


@router.get("/projects/{project_id}/regression-cases", response_model=list[CaseOut])
def list_cases(
    access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> list[CaseOut]:
    return service.list_cases(db, access.project)


@router.post(
    "/projects/{project_id}/regression-cases",
    response_model=CaseOut,
    status_code=201,
    responses=error_responses(404, 422),
)
def create_case(
    body: CaseIn, access: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)
) -> CaseOut:
    case = service.create(db, access.project, access.user, body)
    db.commit()
    return service.to_out(case, None)


@router.get(
    "/projects/{project_id}/regression-cases/{case_id}",
    response_model=CaseOut,
    responses=error_responses(404),
)
def get_case(
    case_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> CaseOut:
    case = service.get_case(db, access.project, case_id)
    return service.to_out(case, service.last_run(db, case))


@router.patch(
    "/projects/{project_id}/regression-cases/{case_id}",
    response_model=CaseOut,
    responses=error_responses(404, 422),
)
def update_case(
    case_id: uuid.UUID,
    body: CasePatch,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> CaseOut:
    case = service.update(db, access.project, service.get_case(db, access.project, case_id), body)
    db.commit()
    return service.to_out(case, service.last_run(db, case))


@router.delete(
    "/projects/{project_id}/regression-cases/{case_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(404),
)
def delete_case(
    case_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(service.get_case(db, access.project, case_id))  # runs cascade in the database
    db.commit()
    return Response(status_code=204)


@router.post(
    "/projects/{project_id}/regression-cases/{case_id}/runs",
    response_model=ExecutionOut,
    status_code=201,
    responses=error_responses(404, 409, 422, 429),
)
def run_case(
    case_id: uuid.UUID,
    body: RunCase,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> ReplayExecution:
    case = service.get_case(db, access.project, case_id)
    target = executions.get_target(db, access.project, body.target_id)
    execution = executions.execute(
        db,
        access.project,
        access.user,
        target,
        RequestDefinition.model_validate(case.request_definition),
        confirm_mutation=body.confirm_mutation,
        kind="regression_run",
        case=case,
    )
    db.commit()
    return execution


@router.get(
    "/projects/{project_id}/regression-cases/{case_id}/runs",
    response_model=list[ExecutionOut],
    responses=error_responses(404),
)
def case_runs(
    case_id: uuid.UUID,
    access: ProjectAccess = Depends(get_project_access),
    db: Session = Depends(get_db),
) -> list[ReplayExecution]:
    return service.runs(db, service.get_case(db, access.project, case_id))


# ---------------------------------------------------------------- CLI / CI (project API key)


@router.get(
    "/ci/regression-cases",
    response_model=list[CiCase],
    tags=["ci"],
    responses=error_responses(401, 429),
)
def ci_cases(
    request: Request, project: Project = Depends(get_api_key_project), db: Session = Depends(get_db)
) -> list[RegressionCase]:
    rate_limit(ci_limiter, request, str(project.id))
    return list(
        db.scalars(
            select(RegressionCase)
            .where(RegressionCase.project_id == project.id)
            .order_by(RegressionCase.created_at, RegressionCase.id)
        )
    )


@router.post(
    "/ci/regression-cases/{case_id}/runs",
    response_model=ExecutionOut,
    tags=["ci"],
    responses=error_responses(401, 404, 422, 429),
)
def ci_report_run(
    case_id: uuid.UUID,
    body: CiRunReport,
    request: Request,
    project: Project = Depends(get_api_key_project),
    db: Session = Depends(get_db),
) -> ReplayExecution:
    rate_limit(ci_limiter, request, str(project.id))
    execution = executions.record_cli_run(db, project, service.get_case(db, project, case_id), body)
    db.commit()
    return execution
