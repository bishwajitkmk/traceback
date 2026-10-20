import uuid

from pydantic import Field

from app.schemas.common import Email, OutSchema, Schema, UtcDatetime


class Credentials(Schema):
    email: Email
    password: str = Field(min_length=1, max_length=1024)


class Registration(Schema):
    email: Email
    password: str = Field(min_length=10, max_length=1024)


class UserOut(OutSchema):
    id: uuid.UUID
    email: str
    created_at: UtcDatetime


class WaitlistIn(Schema):
    email: Email
    source: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
