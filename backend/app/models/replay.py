import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    ExecutionKind,
    ExecutionOutcome,
    ExecutionStatus,
    TargetEnvironment,
    enum_check,
)


class ReplayTarget(UUIDPrimaryKey, Timestamps, Base):
    """An explicitly registered destination. Replays may only go to these."""

    __tablename__ = "replay_targets"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        enum_check("environment", TargetEnvironment),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(2048))
    environment: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class RegressionCase(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "regression_cases"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Method, path, query, headers, body — sanitized, never containing credentials.
    request_definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Expected status plus selected response assertions.
    assertion_definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ReplayExecution(UUIDPrimaryKey, Base):
    """One outbound request: an ad-hoc replay of an event, or a regression-case run."""

    __tablename__ = "replay_executions"
    __table_args__ = (
        enum_check("kind", ExecutionKind),
        enum_check("status", ExecutionStatus),
        enum_check("outcome", ExecutionOutcome),
        CheckConstraint(
            "kind <> 'regression_run' OR regression_case_id IS NOT NULL",
            name="regression_run_has_case",
        ),
        Index("ix_replay_executions_case_started", "regression_case_id", "started_at"),
        Index("ix_replay_executions_project_started", "project_id", "started_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    regression_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regression_cases.id", ondelete="CASCADE")
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL")
    )
    # SET NULL keeps history when a target is removed; request_summary records the URL used.
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("replay_targets.id", ondelete="SET NULL")
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), server_default=ExecutionStatus.PENDING.value)
    # Only set for regression runs, once assertions are evaluated.
    outcome: Mapped[str | None] = mapped_column(String(16))
    request_summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    assertion_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
