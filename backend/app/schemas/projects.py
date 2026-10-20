import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import OutSchema, Schema, UtcDatetime

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RedactionRule(Schema):
    field: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProjectCreate(Schema):
    name: Name


class ProjectUpdate(Schema):
    name: Name | None = None
    retention_days: int | None = Field(default=None, ge=1, le=365)
    redaction_rules: list[RedactionRule] | None = Field(default=None, max_length=50)


class ApiKeySummary(OutSchema):
    id: uuid.UUID
    key_prefix: str
    created_at: UtcDatetime
    last_used_at: UtcDatetime | None


class ApiKeyCreated(OutSchema):
    key: str
    api_key: ApiKeySummary


class ProjectOut(OutSchema):
    id: uuid.UUID
    name: str
    slug: str
    retention_days: int
    redaction_rules: list[RedactionRule]
    api_key: ApiKeySummary | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
