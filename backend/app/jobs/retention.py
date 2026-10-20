"""Delete data past each project's retention period (PRD §12).

Run daily (Render cron job, or any scheduler):
    python -m app.jobs.retention

Deletes, per project, events and replay/run records older than
`retention_days`. Incidents are kept (they hold only aggregate counts,
timestamps and the error message); regression cases are kept (they are
user-authored definitions). Expired browser sessions are removed too.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Event, Project, ReplayExecution, UserSession

log = logging.getLogger("traceback.retention")


def purge(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    totals = {"events": 0, "executions": 0, "sessions": 0}
    for project_id, days in db.execute(select(Project.id, Project.retention_days)).all():
        cutoff = now - timedelta(days=days)
        totals["executions"] += db.execute(
            delete(ReplayExecution).where(
                ReplayExecution.project_id == project_id, ReplayExecution.started_at < cutoff
            )
        ).rowcount
        totals["events"] += db.execute(
            delete(Event).where(Event.project_id == project_id, Event.occurred_at < cutoff)
        ).rowcount
    totals["sessions"] = db.execute(
        delete(UserSession).where(UserSession.expires_at <= now)
    ).rowcount
    return totals


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    with SessionLocal() as db:
        totals = purge(db)
        db.commit()
    log.info("retention purge complete: %s", totals)


if __name__ == "__main__":
    main()
