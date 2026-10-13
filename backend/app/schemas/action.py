"""Pydantic schemas for two-phase action approval and verification."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ActionStatus = Literal[
    "pending_approval",
    "executing",
    "completed",
    "failed",
    "rejected",
]


class ActionResponse(BaseModel):
    """Details of a staged, completed, or rejected action."""

    id: uuid.UUID
    user_id: uuid.UUID
    action_type: str
    status: ActionStatus
    payload: dict[str, Any]
    verification_result: dict[str, Any] | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "confirmed_at", "completed_at", mode="after")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class ActionConfirmRequest(BaseModel):
    """User confirmation or rejection decision for a staged action."""

    confirmed: bool = Field(..., description="True to approve execution, False to reject")
    rejection_reason: str | None = Field(
        default=None, max_length=500, description="Optional explanation if rejected"
    )


class ActionConfirmResponse(BaseModel):
    """Execution and verification outcome following approval decision."""

    action_id: uuid.UUID
    status: ActionStatus
    verified: bool
    verification_details: dict[str, Any] | None = None
    error_message: str | None = None


class ActionVerifyResponse(BaseModel):
    """Post-condition verification report for an executed action."""

    action_id: uuid.UUID
    status: ActionStatus
    verified: bool
    details: dict[str, Any] | None = None
    error_message: str | None = None
