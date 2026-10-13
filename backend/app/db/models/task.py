"""Task domain model."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Task(Base):
    """Task entity managed by user."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("length(title) > 0", name="chk_task_title_not_empty"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')", name="chk_task_status"
        ),
        CheckConstraint("priority IN ('P1', 'P2', 'P3', 'P4')", name="chk_task_priority"),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 720", name="chk_task_duration"
        ),
        CheckConstraint("energy_level IN ('high', 'medium', 'low')", name="chk_task_energy"),
        Index("idx_tasks_user_status", "user_id", "status"),
        Index("idx_tasks_user_deadline", "user_id", "deadline"),
        Index("idx_tasks_user_archived", "user_id", "is_archived"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(5), nullable=False, default="P3")
    duration_minutes: Mapped[int] = mapped_column(nullable=False, default=45)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    energy_level: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="tasks")  # type: ignore # noqa: F821
