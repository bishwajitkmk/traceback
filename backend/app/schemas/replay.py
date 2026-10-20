import uuid
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator

from app.schemas.common import OutSchema, Schema, UtcDatetime

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
TargetEnvironment = Literal["local", "development", "staging", "test"]
TargetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
BaseUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]


class TargetIn(Schema):
    name: TargetName
    base_url: BaseUrl
    environment: TargetEnvironment
    enabled: bool = True


class TargetPatch(Schema):
    name: TargetName | None = None
    base_url: BaseUrl | None = None
    environment: TargetEnvironment | None = None
    enabled: bool | None = None


class TargetOut(OutSchema):
    id: uuid.UUID
    name: str
    base_url: str
    environment: TargetEnvironment
    enabled: bool
    created_at: UtcDatetime
    updated_at: UtcDatetime


def _has_control_chars(value: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)


class RequestDefinition(Schema):
    method: HttpMethod
    path: str = Field(min_length=1, max_length=2048)
    query: dict[str, str | list[str]] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None

    @field_validator("path")
    @classmethod
    def _relative_path(cls, path: str) -> str:
        # The path is joined to a registered target; it must not be able to change the host.
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "://" in path
            or "\\" in path
            or _has_control_chars(path)
            or " " in path
        ):
            raise ValueError("The path must be relative to the target, starting with a single '/'.")
        return path

    @field_validator("headers")
    @classmethod
    def _bounded_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        if len(headers) > 50:
            raise ValueError("At most 50 headers.")
        for name, value in headers.items():
            if not name or len(name) > 256 or len(value) > 8192:
                raise ValueError(f"Header {name[:40]!r} is too long.")
            if _has_control_chars(name) or _has_control_chars(value) or ":" in name:
                raise ValueError(f"Header {name[:40]!r} contains invalid characters.")
        return headers


class CreateReplay(Schema):
    target_id: uuid.UUID
    event_id: uuid.UUID | None = None
    request: RequestDefinition
    confirm_mutation: bool = False


class ResponseSummary(OutSchema):
    status: int
    headers: dict[str, str]
    body: Any = None
    body_truncated: bool = False


class AssertionResult(OutSchema):
    description: str
    passed: bool
    expected: Any = None
    actual: Any = None


class RequestSummary(OutSchema):
    method: HttpMethod
    url: str
    headers: dict[str, str]


class ExecutionOut(OutSchema):
    id: uuid.UUID
    kind: Literal["replay", "regression_run"]
    regression_case_id: uuid.UUID | None
    event_id: uuid.UUID | None
    target_id: uuid.UUID | None
    status: Literal["pending", "running", "completed", "error"]
    outcome: Literal["passed", "failed"] | None
    request_summary: RequestSummary
    response_summary: ResponseSummary | None
    assertion_results: list[AssertionResult] | None
    duration_ms: int | None
    error_summary: str | None
    started_at: UtcDatetime
    completed_at: UtcDatetime | None
