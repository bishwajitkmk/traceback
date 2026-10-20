"""Replays, regression-case runs and CLI-reported runs, recorded as ReplayExecutions."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.redaction import Redactor
from app.models import Project, RegressionCase, ReplayExecution, ReplayTarget, User
from app.schemas.cases import CiRunReport
from app.schemas.replay import RequestDefinition
from app.services import assertions, outbound
from app.services.netguard import allow_private_for

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def get_target(db: Session, project: Project, target_id: uuid.UUID) -> ReplayTarget:
    target = db.scalar(
        select(ReplayTarget).where(
            ReplayTarget.id == target_id, ReplayTarget.project_id == project.id
        )
    )
    if target is None:
        raise NotFound("replay target")
    if not target.enabled:
        raise AppError(409, "target_disabled", f'Target "{target.name}" is disabled.')
    return target


def _redactor(project: Project) -> Redactor:
    return Redactor(rule["field"] for rule in project.redaction_rules)


def _response_summary(
    project: Project, status: int, headers: dict[str, str], body: Any, truncated: bool
) -> dict[str, Any]:
    # Replay results follow the same privacy rules as captured events (PRD §10.8).
    redactor = _redactor(project)
    return {
        "status": status,
        "headers": redactor.redact({k.lower(): v for k, v in headers.items()}),
        "body": redactor.redact(body),
        "body_truncated": truncated,
    }


def execute(
    db: Session,
    project: Project,
    user: User | None,
    target: ReplayTarget,
    request: RequestDefinition,
    *,
    confirm_mutation: bool,
    kind: str,
    event_id: uuid.UUID | None = None,
    case: RegressionCase | None = None,
) -> ReplayExecution:
    if request.method in MUTATING and not confirm_mutation:
        raise AppError(
            409,
            "confirmation_required",
            f'{request.method} may change data on "{target.name}". Confirm the replay to send it.',
        )
    started_at = datetime.now(UTC)
    result = outbound.send(
        base_url=target.base_url,
        method=request.method,
        path=request.path,
        query=request.query,
        headers=request.headers,
        body=request.body,
        allow_private=allow_private_for(
            target.environment, get_settings().replay_allow_private_networks
        ),
    )
    execution = ReplayExecution(
        project_id=project.id,
        kind=kind,
        regression_case_id=case.id if case else None,
        event_id=event_id,
        target_id=target.id,
        triggered_by=user.id if user else None,
        request_summary={
            "method": request.method,
            "url": result.url,
            "headers": _redactor(project).redact(result.sent_headers),
            "runner": "server",
        },
        duration_ms=result.duration_ms,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=result.duration_ms or 0),
    )
    if result.status is not None and result.error is None:
        execution.status = "completed"
        execution.response_summary = _response_summary(
            project,
            result.status,
            result.response_headers or {},
            result.body,
            result.body_truncated,
        )
        if case is not None:
            execution.outcome, execution.assertion_results = assertions.evaluate(
                case.assertion_definition, result.status, result.body
            )
    else:
        execution.status = "error"
        execution.error_summary = result.error
        if case is not None:
            execution.outcome = "failed"
    db.add(execution)
    db.flush()
    db.refresh(execution)
    return execution


def record_cli_run(
    db: Session, project: Project, case: RegressionCase, report: CiRunReport
) -> ReplayExecution:
    """Store a run the CLI executed itself; assertions are re-evaluated here."""
    now = datetime.now(UTC)
    execution = ReplayExecution(
        project_id=project.id,
        kind="regression_run",
        regression_case_id=case.id,
        target_id=None,
        request_summary={
            "method": case.request_definition["method"],
            "url": outbound.build_url(
                report.target_url,
                case.request_definition["path"],
                case.request_definition.get("query", {}),
            ),
            "headers": {},
            "runner": "cli",
        },
        duration_ms=report.duration_ms,
        started_at=now - timedelta(milliseconds=report.duration_ms or 0),
        completed_at=now,
    )
    if report.response is not None and report.error is None:
        r = report.response
        execution.status = "completed"
        execution.response_summary = _response_summary(
            project, r.status, r.headers, r.body, r.body_truncated
        )
        execution.outcome, execution.assertion_results = assertions.evaluate(
            case.assertion_definition, r.status, r.body
        )
    else:
        execution.status = "error"
        execution.outcome = "failed"
        execution.error_summary = report.error or "The runner reported no response."
    db.add(execution)
    db.flush()
    db.refresh(execution)
    return execution
