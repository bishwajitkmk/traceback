"""Dashboard statistics, computed from stored data (PRD §6.8)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models import Event, Incident, Project, RegressionCase, ReplayExecution
from app.schemas.incidents import IncidentOut
from app.schemas.replay import ExecutionOut
from app.schemas.stats import (
    DailyCount,
    ProjectStats,
    RecentRun,
    RegressionSummary,
    TopIncident,
)


def latest_runs_by_case(db: Session, project: Project) -> dict[object, ReplayExecution]:
    rows = db.scalars(
        select(ReplayExecution)
        .where(
            ReplayExecution.project_id == project.id,
            ReplayExecution.kind == "regression_run",
        )
        .distinct(ReplayExecution.regression_case_id)
        .order_by(ReplayExecution.regression_case_id, ReplayExecution.started_at.desc())
    )
    return {r.regression_case_id: r for r in rows}


def project_stats(db: Session, project: Project, days: int) -> ProjectStats:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)
    in_range = (Event.project_id == project.id, Event.occurred_at >= start)

    day = cast(func.timezone("UTC", Event.occurred_at), Date)
    counts = {
        d.isoformat(): n
        for d, n in db.execute(select(day, func.count()).where(*in_range).group_by(day))
    }
    daily = [
        DailyCount(
            date=(start + timedelta(days=i)).date().isoformat(),
            events=counts.get((start + timedelta(days=i)).date().isoformat(), 0),
        )
        for i in range(days)
    ]

    top_rows = db.execute(
        select(Event.incident_id, func.count().label("n"))
        .where(*in_range, Event.incident_id.is_not(None))
        .group_by(Event.incident_id)
        .order_by(func.count().desc(), Event.incident_id)
        .limit(5)
    ).all()
    incidents = {
        i.id: i
        for i in db.scalars(select(Incident).where(Incident.id.in_([r[0] for r in top_rows])))
    }

    recent_incidents = db.scalars(
        select(Incident)
        .where(Incident.project_id == project.id)
        .order_by(Incident.last_seen_at.desc(), Incident.id)
        .limit(5)
    )

    runs = db.execute(
        select(ReplayExecution, RegressionCase.name)
        .join(RegressionCase, RegressionCase.id == ReplayExecution.regression_case_id)
        .where(ReplayExecution.project_id == project.id, ReplayExecution.kind == "regression_run")
        .order_by(ReplayExecution.started_at.desc())
        .limit(5)
    ).all()

    case_ids = list(
        db.scalars(select(RegressionCase.id).where(RegressionCase.project_id == project.id))
    )
    latest = latest_runs_by_case(db, project)
    passing = sum(1 for cid in case_ids if cid in latest and latest[cid].outcome == "passed")
    never = sum(1 for cid in case_ids if cid not in latest)

    return ProjectStats(
        days=days,
        open_incidents=db.scalar(
            select(func.count()).where(Incident.project_id == project.id, Incident.status == "open")
        )
        or 0,
        events_in_range=sum(counts.values()),
        new_incidents_in_range=db.scalar(
            select(func.count()).where(
                Incident.project_id == project.id, Incident.first_seen_at >= start
            )
        )
        or 0,
        daily=daily,
        top_incidents=[
            TopIncident(incident=IncidentOut.model_validate(incidents[iid]), events=n)
            for iid, n in top_rows
            if iid in incidents
        ],
        recent_incidents=[IncidentOut.model_validate(i) for i in recent_incidents],
        recent_runs=[
            RecentRun(
                execution=ExecutionOut.model_validate(r),
                case_id=r.regression_case_id,
                case_name=name,
            )
            for r, name in runs
        ],
        regression=RegressionSummary(
            total=len(case_ids),
            passing=passing,
            failing=len(case_ids) - passing - never,
            never_run=never,
        ),
    )
