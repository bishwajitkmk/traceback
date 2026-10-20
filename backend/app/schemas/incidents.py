import uuid
from typing import Any, Literal

from app.schemas.common import OutSchema, Schema, UtcDatetime

IncidentStatus = Literal["open", "resolved"]


class IncidentOut(OutSchema):
    id: uuid.UUID
    project_id: uuid.UUID
    fingerprint: str
    title: str
    error_type: str
    error_message: str
    normalized_route: str | None
    status: IncidentStatus
    occurrence_count: int
    first_seen_at: UtcDatetime
    last_seen_at: UtcDatetime
    resolved_at: UtcDatetime | None


class IncidentPatch(Schema):
    status: IncidentStatus


class StackFrame(OutSchema):
    filename: str
    lineno: int
    function: str
    context_line: str | None
    in_app: bool


class ExceptionData(OutSchema):
    type: str
    message: str
    frames: list[StackFrame]


class RequestData(OutSchema):
    path: str
    query: dict[str, str | list[str]]
    headers: dict[str, str]
    body_captured: bool
    body: Any = None
    body_truncated: bool
    response_headers: dict[str, str] | None = None
    response_body: Any = None


class EventOut(OutSchema):
    id: uuid.UUID
    incident_id: uuid.UUID | None
    event_type: Literal["exception", "http_error", "diagnostic"]
    correlation_id: str | None
    environment: str | None
    release: str | None
    request_method: str | None
    normalized_route: str | None
    request_data: RequestData | None
    response_status: int | None
    duration_ms: int | None
    exception_data: ExceptionData | None
    occurred_at: UtcDatetime
    received_at: UtcDatetime
