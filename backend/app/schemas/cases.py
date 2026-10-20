import uuid
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import OutSchema, Schema, UtcDatetime
from app.schemas.replay import ExecutionOut, RequestDefinition

JsonPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class JsonPathEquals(Schema):
    type: Literal["json_path_equals"]
    path: JsonPath
    expected: Any = None


class JsonPathExists(Schema):
    type: Literal["json_path_exists"]
    path: JsonPath


class BodyContains(Schema):
    type: Literal["body_contains"]
    expected: str = Field(min_length=1, max_length=2000)


Assertion = Annotated[JsonPathEquals | JsonPathExists | BodyContains, Field(discriminator="type")]


class AssertionDefinition(Schema):
    expected_status: int = Field(ge=100, le=599)
    assertions: list[Assertion] = Field(default_factory=list, max_length=25)


CaseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CaseIn(Schema):
    name: CaseName
    description: str | None = Field(default=None, max_length=2000)
    incident_id: uuid.UUID | None = None
    source_event_id: uuid.UUID | None = None
    request_definition: RequestDefinition
    assertion_definition: AssertionDefinition


class CasePatch(Schema):
    name: CaseName | None = None
    description: str | None = Field(default=None, max_length=2000)
    incident_id: uuid.UUID | None = None
    source_event_id: uuid.UUID | None = None
    request_definition: RequestDefinition | None = None
    assertion_definition: AssertionDefinition | None = None


class CaseOut(OutSchema):
    id: uuid.UUID
    incident_id: uuid.UUID | None
    source_event_id: uuid.UUID | None
    name: str
    description: str | None
    request_definition: RequestDefinition
    assertion_definition: AssertionDefinition
    last_run: ExecutionOut | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RunCase(Schema):
    target_id: uuid.UUID
    confirm_mutation: bool = False


# ---------------------------------------------------------------- CLI / CI


class CiCase(OutSchema):
    id: uuid.UUID
    name: str
    request_definition: RequestDefinition
    assertion_definition: AssertionDefinition


class CiResponse(Schema):
    status: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    body_truncated: bool = False


class CiRunReport(Schema):
    target_url: str = Field(min_length=1, max_length=2048)
    duration_ms: int | None = Field(default=None, ge=0)
    response: CiResponse | None = None
    error: str | None = Field(default=None, max_length=2000)
