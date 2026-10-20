"""SDK -> API event schema. See docs/contracts.md."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import OutSchema, Schema

Short = Annotated[str, StringConstraints(max_length=128)]


class IngestFrame(Schema):
    filename: str = Field(max_length=1024)
    lineno: int = Field(ge=0)
    function: str = Field(max_length=512)
    context_line: str | None = Field(default=None, max_length=2000)
    in_app: bool = True


class IngestException(Schema):
    type: str = Field(min_length=1, max_length=255)
    message: str = Field(default="", max_length=8000)
    frames: list[IngestFrame] = Field(default_factory=list, max_length=100)


class IngestRequest(Schema):
    method: str = Field(min_length=1, max_length=16)
    route: str | None = Field(default=None, max_length=512)
    path: str = Field(min_length=1, max_length=2048)
    query: dict[str, str | list[str]] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body_captured: bool = False
    body: Any = None
    body_truncated: bool = False


class IngestResponse(Schema):
    status: int = Field(ge=100, le=599)
    headers: dict[str, str] | None = None
    body: Any = None


class IngestSdk(Schema):
    name: str = Field(max_length=64)
    version: str = Field(max_length=32)


class IngestEvent(Schema):
    # Newer SDKs may send fields this server does not know yet.
    model_config = ConfigDict(extra="ignore")

    event_id: uuid.UUID
    event_type: Literal["exception", "http_error"]
    occurred_at: AwareDatetime
    environment: Annotated[str, StringConstraints(max_length=64)] | None = None
    release: Short | None = None
    correlation_id: Short | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    request: IngestRequest | None = None
    response: IngestResponse | None = None
    exception: IngestException | None = None
    sdk: IngestSdk | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "IngestEvent":
        if self.event_type == "exception" and self.exception is None:
            raise ValueError("exception events need an 'exception' object.")
        if self.event_type == "http_error" and self.response is None:
            raise ValueError("http_error events need a 'response' object.")
        return self


class IngestResult(OutSchema):
    event_id: uuid.UUID
    incident_id: uuid.UUID | None
    duplicate: bool
