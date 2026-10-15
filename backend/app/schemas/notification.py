"""Notification request and response Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationType = Literal[
    "due_soon",
    "due_now",
    "overdue",
    "upcoming_task",
    "schedule_conflict",
    "calendar_revoked",
    "calendar_stale",
    "action_required",
    "action_failed",
    "task_completed",
]

NotificationChannel = Literal["in_app", "email", "browser_push"]

NotificationStatus = Literal[
    "pending",
    "processing",
    "delivered",
    "failed",
    "cancelled",
    "permanently_failed",
]


class NotificationSettingsSchema(BaseModel):
    """Configurable notification rules and quiet hours."""

    notify_upcoming_tasks: bool = Field(default=True, description="Remind user before task start")
    notify_deadlines: bool = Field(default=True, description="Remind user approaching deadline")
    notify_overdue: bool = Field(default=True, description="Alert user when task deadline passes")
    notify_schedule_conflicts: bool = Field(default=True, description="Warn on schedule conflicts")
    notify_action_requests: bool = Field(default=True, description="Prompt when write action requires approval")
    notify_task_completed: bool = Field(default=False, description="Send confirmation when task completed")
    reminder_lead_time_minutes: int = Field(
        default=30, ge=5, le=1440, description="Lead time in minutes before deadline"
    )
    quiet_hours_enabled: bool = Field(default=False, description="Suppress non-urgent delivery during quiet hours")
    quiet_hours_start: str | None = Field(
        default="22:00:00", pattern=r"^\d{2}:\d{2}(:\d{2})?$", description="Quiet hours start (HH:MM:SS)"
    )
    quiet_hours_end: str | None = Field(
        default="08:00:00", pattern=r"^\d{2}:\d{2}(:\d{2})?$", description="Quiet hours end (HH:MM:SS)"
    )

    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseModel):
    """Notification item returned to the user or caller."""

    id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    action_id: uuid.UUID | None = None
    notification_type: NotificationType
    channel: NotificationChannel = "in_app"
    status: NotificationStatus = "pending"
    title: str
    message: str
    scheduled_for: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    is_read: bool = False
    attempt_count: int = 0
    max_attempts: int = 3
    deduplication_key: str | None = None
    last_error: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCountResponse(BaseModel):
    """Unread notifications count."""

    unread_count: int = Field(..., ge=0)


class NotificationEvaluationResult(BaseModel):
    """Result of running notification evaluation."""

    evaluated_tasks_count: int
    new_notifications_count: int
    notifications: list[NotificationResponse] = Field(default_factory=list)


class NotificationDispatchResponse(BaseModel):
    """Operational execution outcome returned by the persistent dispatcher."""

    claimed: int
    delivered: int
    failed: int
    cancelled: int
    stale_leases_recovered: int
    duration_ms: float
    timestamp: datetime
