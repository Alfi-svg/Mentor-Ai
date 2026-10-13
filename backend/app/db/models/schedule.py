"""Schedule and schedule block domain models."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Schedule(Base):
    """Daily schedule container."""

    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'accepted', 'superseded')", name="chk_schedule_status"
        ),
        Index("idx_schedules_user_date", "user_id", "schedule_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="schedules")  # type: ignore # noqa: F821
    blocks: Mapped[list["ScheduleBlock"]] = relationship(
        "ScheduleBlock", back_populates="schedule", cascade="all, delete-orphan"
    )


class ScheduleBlock(Base):
    """Individual allocated time block in a schedule."""

    __tablename__ = "schedule_blocks"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="chk_block_end_after_start"),
        CheckConstraint(
            "block_type IN ('task', 'fixed_event', 'break', 'buffer')",
            name="chk_block_type",
        ),
        Index("idx_blocks_schedule_id", "schedule_id"),
        Index("idx_blocks_user_time", "user_id", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    block_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="blocks")
