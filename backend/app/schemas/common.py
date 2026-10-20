import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or not _EMAIL.match(value):
        raise ValueError("Enter a valid email address.")
    return value


Email = Annotated[str, AfterValidator(_email)]

# ISO-8601 with a trailing Z, matching what the frontend and SDK expect.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(lambda d: d.isoformat().replace("+00:00", "Z"), return_type=str),
]


class Schema(BaseModel):
    """Request bodies: unknown fields are rejected."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OutSchema(BaseModel):
    """Response bodies, usually built from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class Page[T](OutSchema):
    items: list[T]
    total: int
    page: int
    page_size: int
