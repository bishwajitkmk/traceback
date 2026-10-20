import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Project(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug"),
        CheckConstraint("retention_days BETWEEN 1 AND 365", name="retention_days_range"),
    )

    # Covered by the (owner_id, slug) unique index, so no separate index.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140))
    retention_days: Mapped[int] = mapped_column(Integer, server_default=text("30"))
    # Extra field names/patterns to redact on top of the built-in defaults.
    redaction_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )

    api_keys: Mapped[list["ProjectApiKey"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectApiKey(UUIDPrimaryKey, Base):
    """Ingestion key. Plaintext is shown once; only a hash is persisted.

    At most one key per project is active (revoked_at IS NULL), enforced by a
    partial unique index, so rotation is revoke-old + insert-new in one transaction.
    """

    __tablename__ = "project_api_keys"
    __table_args__ = (
        Index(
            "uq_project_api_keys_one_active",
            "project_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Non-secret leading characters, shown in the UI to identify the key.
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="api_keys")
