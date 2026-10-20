import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import EventType, IncidentStatus, enum_check


class Incident(UUIDPrimaryKey, Timestamps, Base):
    """A group of events sharing a stable fingerprint within a project."""

    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint"),
        enum_check("status", IncidentStatus),
        CheckConstraint("occurrence_count >= 0", name="occurrence_count_non_negative"),
        Index("ix_incidents_project_status_last_seen", "project_id", "status", "last_seen_at"),
        Index("ix_incidents_project_last_seen", "project_id", "last_seen_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    error_type: Mapped[str] = mapped_column(String(255), index=True)
    error_message: Mapped[str] = mapped_column(Text)
    normalized_route: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), server_default=IncidentStatus.OPEN.value)
    occurrence_count: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(UUIDPrimaryKey, Base):
    """One captured occurrence, already redacted and size-limited before insert."""

    __tablename__ = "events"
    __table_args__ = (
        # NULLs are distinct in Postgres, so events without a key never collide.
        UniqueConstraint("project_id", "idempotency_key"),
        enum_check("event_type", EventType),
        Index("ix_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_events_incident_occurred", "incident_id", "occurred_at"),
        Index("ix_events_project_correlation", "project_id", "correlation_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # Diagnostic events may not belong to an incident.
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    environment: Mapped[str | None] = mapped_column(String(64))
    release: Mapped[str | None] = mapped_column(String(128))
    request_method: Mapped[str | None] = mapped_column(String(16))
    normalized_route: Mapped[str | None] = mapped_column(String(512))
    request_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    exception_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
