"""User profile and preferences models."""

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Profile(Base):
    """User profile extending Supabase auth.users identity."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
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

    # Relationships
    preferences: Mapped[Optional["UserPreferences"]] = relationship(
        "UserPreferences", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(  # type: ignore # noqa: F821
        "Task", back_populates="profile", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(  # type: ignore # noqa: F821
        "CalendarEvent", back_populates="profile", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(  # type: ignore # noqa: F821
        "Schedule", back_populates="profile", cascade="all, delete-orphan"
    )
    action_history: Mapped[list["ActionHistory"]] = relationship(  # type: ignore # noqa: F821
        "ActionHistory", back_populates="profile", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore # noqa: F821
        "AuditLog", back_populates="profile", cascade="all, delete-orphan"
    )
    external_connections: Mapped[list["ExternalConnection"]] = relationship(  # type: ignore # noqa: F821
        "ExternalConnection", back_populates="profile", cascade="all, delete-orphan"
    )


class UserPreferences(Base):
    """Configurable scheduling preferences for a user."""

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("buffer_minutes >= 0 AND buffer_minutes <= 60", name="chk_buffer_minutes"),
        CheckConstraint(
            "default_task_duration > 0 AND default_task_duration <= 480",
            name="chk_default_task_duration",
        ),
        CheckConstraint(
            "max_focus_hours_per_day > 0 AND max_focus_hours_per_day <= 16",
            name="chk_max_focus_hours",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    work_start_time: Mapped[str] = mapped_column(String(8), nullable=False, default="09:00:00")
    work_end_time: Mapped[str] = mapped_column(String(8), nullable=False, default="18:00:00")
    buffer_minutes: Mapped[int] = mapped_column(nullable=False, default=15)
    default_task_duration: Mapped[int] = mapped_column(nullable=False, default=45)
    max_focus_hours_per_day: Mapped[int] = mapped_column(nullable=False, default=8)
    available_days: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=lambda: [1, 2, 3, 4, 5]
    )
    auto_schedule_breaks: Mapped[bool] = mapped_column(nullable=False, default=True)
    notification_settings: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=lambda: {
            "notify_upcoming_tasks": True,
            "notify_deadlines": True,
            "notify_overdue": True,
            "notify_schedule_conflicts": True,
            "notify_action_requests": True,
            "notify_task_completed": False,
            "reminder_lead_time_minutes": 30,
            "quiet_hours_enabled": False,
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "08:00:00",
        },
    )

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

    profile: Mapped["Profile"] = relationship("Profile", back_populates="preferences")
