"""Notification domain model for task deadline alerts, persistent execution, and delivery tracking."""

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
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Notification(Base):
    """Notification entity representing a deadline alert, action prompt, or system reminder."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('due_soon', 'due_now', 'overdue', 'upcoming_task', 'schedule_conflict', 'calendar_revoked', 'calendar_stale', 'action_required', 'action_failed', 'task_completed', 'missed_session', 'schedule_recovery')",
            name="chk_notification_type",
        ),

        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed', 'cancelled', 'permanently_failed')",
            name="chk_notification_status",
        ),
        CheckConstraint(
            "channel IN ('in_app', 'email', 'browser_push')",
            name="chk_notification_channel",
        ),
        Index("idx_notifications_user_read", "user_id", "is_read"),
        Index("idx_notifications_user_scheduled", "user_id", "scheduled_for"),
        Index("idx_notifications_task_type", "task_id", "notification_type"),
        Index("idx_notifications_dispatch", "status", "scheduled_for", "lease_expires_at"),
        Index("idx_notifications_user_dedup", "user_id", "deduplication_key"),
        Index("idx_notifications_action_id", "action_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("action_history.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="in_app")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deduplication_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", backref="notifications")
    action = relationship("ActionHistory", backref="notifications")
