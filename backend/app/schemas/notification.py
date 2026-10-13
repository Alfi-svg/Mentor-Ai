"""Notification request and response Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationType = Literal["due_soon", "due_now", "overdue"]


class NotificationResponse(BaseModel):
    """Notification item returned to the user."""

    id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    notification_type: NotificationType
    title: str
    message: str
    scheduled_for: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    is_read: bool
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
