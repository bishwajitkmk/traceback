import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Event, Incident, Project, RegressionCase, ReplayExecution, User
from app.schemas.cases import CaseIn, CaseOut, CasePatch
from app.schemas.replay import ExecutionOut, RequestDefinition
from app.services.outbound import safe_headers
from app.services.stats import latest_runs_by_case


def _clean_request(request: RequestDefinition) -> dict[str, Any]:
    """Stored case requests never contain credential headers (PRD §6.6)."""
    data = request.model_dump()
    data["headers"] = safe_headers(data["headers"])
    return data


def _check_refs(
    db: Session, project: Project, incident_id: uuid.UUID | None, event_id: uuid.UUID | None
) -> None:
    if incident_id and not db.scalar(
        select(Incident.id).where(Incident.id == incident_id, Incident.project_id == project.id)
    ):
        raise NotFound("incident")
    if event_id and not db.scalar(
        select(Event.id).where(Event.id == event_id, Event.project_id == project.id)
    ):
        raise NotFound("event")


def to_out(case: RegressionCase, last_run: ReplayExecution | None) -> CaseOut:
    return CaseOut(
        id=case.id,
        incident_id=case.incident_id,
        source_event_id=case.source_event_id,
        name=case.name,
        description=case.description,
        request_definition=case.request_definition,
        assertion_definition=case.assertion_definition,
        last_run=ExecutionOut.model_validate(last_run) if last_run else None,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def list_cases(db: Session, project: Project) -> list[CaseOut]:
    cases = db.scalars(
        select(RegressionCase)
        .where(RegressionCase.project_id == project.id)
        .order_by(RegressionCase.created_at.desc(), RegressionCase.id)
    )
    latest = latest_runs_by_case(db, project)
    return [to_out(c, latest.get(c.id)) for c in cases]


def get_case(db: Session, project: Project, case_id: uuid.UUID) -> RegressionCase:
    case = db.scalar(
        select(RegressionCase).where(
            RegressionCase.id == case_id, RegressionCase.project_id == project.id
        )
    )
    if case is None:
        raise NotFound("regression case")
    return case


def last_run(db: Session, case: RegressionCase) -> ReplayExecution | None:
    return db.scalar(
        select(ReplayExecution)
        .where(ReplayExecution.regression_case_id == case.id)
        .order_by(ReplayExecution.started_at.desc())
        .limit(1)
    )


def create(db: Session, project: Project, user: User, data: CaseIn) -> RegressionCase:
    _check_refs(db, project, data.incident_id, data.source_event_id)
    case = RegressionCase(
        project_id=project.id,
        incident_id=data.incident_id,
        source_event_id=data.source_event_id,
        name=data.name,
        description=(data.description or "").strip() or None,
        request_definition=_clean_request(data.request_definition),
        assertion_definition=data.assertion_definition.model_dump(),
        created_by=user.id,
    )
    db.add(case)
    db.flush()
    db.refresh(case)
    return case


def update(db: Session, project: Project, case: RegressionCase, patch: CasePatch) -> RegressionCase:
    fields = patch.model_fields_set
    _check_refs(db, project, patch.incident_id, patch.source_event_id)
    if "name" in fields and patch.name is not None:
        case.name = patch.name
    if "description" in fields:
        case.description = (patch.description or "").strip() or None
    if "incident_id" in fields:
        case.incident_id = patch.incident_id
    if "source_event_id" in fields:
        case.source_event_id = patch.source_event_id
    if patch.request_definition is not None:
        case.request_definition = _clean_request(patch.request_definition)
    if patch.assertion_definition is not None:
        case.assertion_definition = patch.assertion_definition.model_dump()
    case.updated_at = datetime.now(UTC)
    db.flush()
    return case


def runs(db: Session, case: RegressionCase, limit: int = 50) -> list[ReplayExecution]:
    return list(
        db.scalars(
            select(ReplayExecution)
            .where(ReplayExecution.regression_case_id == case.id)
            .order_by(ReplayExecution.started_at.desc(), ReplayExecution.id)
            .limit(limit)
        )
    )
