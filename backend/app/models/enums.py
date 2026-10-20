from enum import StrEnum

from sqlalchemy import CheckConstraint


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class EventType(StrEnum):
    EXCEPTION = "exception"
    HTTP_ERROR = "http_error"
    DIAGNOSTIC = "diagnostic"


class TargetEnvironment(StrEnum):
    """Replay is never allowed against production, so it is not a member here."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    TEST = "test"


class ExecutionKind(StrEnum):
    REPLAY = "replay"
    REGRESSION_RUN = "regression_run"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ExecutionOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


def enum_check(column: str, enum: type[StrEnum], name: str | None = None) -> CheckConstraint:
    """CHECK constraint restricting a VARCHAR column to an enum's values.

    Plain VARCHAR + CHECK is used instead of native PG enums because adding
    values to a native enum is awkward to migrate.
    """
    allowed = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or f"{column}_valid")
