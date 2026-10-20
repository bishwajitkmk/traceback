import uuid

from app.schemas.common import OutSchema
from app.schemas.incidents import IncidentOut
from app.schemas.replay import ExecutionOut


class DailyCount(OutSchema):
    date: str
    events: int


class TopIncident(OutSchema):
    incident: IncidentOut
    events: int


class RecentRun(OutSchema):
    execution: ExecutionOut
    case_id: uuid.UUID
    case_name: str


class RegressionSummary(OutSchema):
    total: int
    passing: int
    failing: int
    never_run: int


class ProjectStats(OutSchema):
    days: int
    open_incidents: int
    events_in_range: int
    new_incidents_in_range: int
    daily: list[DailyCount]
    top_incidents: list[TopIncident]
    recent_incidents: list[IncidentOut]
    recent_runs: list[RecentRun]
    regression: RegressionSummary
