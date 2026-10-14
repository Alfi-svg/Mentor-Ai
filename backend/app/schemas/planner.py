"""Pydantic schemas for the Natural Language Planner and Chat pipeline."""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.task import (
    EnergyLevel,
    TaskConstraints,
    TaskCreateRequest,
    TaskPriority,
    TaskResponse,
)
from app.services.scheduler.models import ScheduleProposal

PlanIntent = Literal[
    "plan_day",
    "add_task",
    "add_event",
    "reschedule",
    "clarification_needed",
    "unsupported",
]
ParserType = Literal["gemini", "groq", "deterministic_offline"]


class DetectedFixedEvent(BaseModel):
    """A fixed calendar event extracted from user natural language instructions."""

    title: str = Field(..., min_length=1, max_length=200, description="Event title")
    start_time: datetime = Field(..., description="Timezone-aware start time")
    end_time: datetime = Field(..., description="Timezone-aware end time")
    location: str | None = Field(
        default=None, max_length=200, description="Meeting location or URL"
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("start_time", "end_time", mode="after")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Normalize naive datetimes to UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    @field_validator("end_time", mode="after")
    @classmethod
    def validate_duration(cls, end_time: datetime, info: Any) -> datetime:
        """Ensure end_time is strictly after start_time."""
        start_time = info.data.get("start_time")
        if start_time and end_time <= start_time:
            raise ValueError("end_time must be strictly after start_time")
        return end_time


class DetectedTask(BaseModel):
    """A task extracted from user natural language instructions."""

    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=720,
        description="Estimated duration in minutes (1-720). Null if missing from prompt.",
    )
    priority: TaskPriority = Field(
        default="P3",
        description="Task priority level (P1 highest, P4 lowest)",
    )
    deadline: datetime | None = Field(
        default=None,
        description="Optional deadline timestamp (UTC)",
    )
    energy_level: EnergyLevel | None = Field(
        default=None,
        description="Optional cognitive energy level required",
    )
    constraints: TaskConstraints | None = Field(
        default=None,
        description="Optional scheduling constraints",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Optional prerequisite task titles or references",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("deadline", mode="after")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        """Normalize naive deadlines to UTC."""
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class DraftPlan(BaseModel):
    """Structured NLU output matching docs/AI_AND_SCHEDULER.md DraftPlan schema."""

    intent: PlanIntent = Field(..., description="Classified user intent")
    target_date: date = Field(..., description="Target schedule date (YYYY-MM-DD)")
    explanation: str = Field(..., description="Brief, user-facing summary of understanding")
    fixed_events: list[DetectedFixedEvent] = Field(
        default_factory=list, description="Extracted fixed commitments"
    )
    tasks: list[DetectedTask] = Field(
        default_factory=list, description="Extracted actionable tasks"
    )
    clarification_question: str | None = Field(
        default=None,
        description="Question asked if critical information is missing or ambiguous",
    )

    model_config = ConfigDict(extra="ignore")


class PlanGenerateRequest(BaseModel):
    """User request to generate a structured plan proposal from natural language."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User natural-language instruction (e.g., 'Plan my day tomorrow...')",
        examples=[
            "Plan my day tomorrow: 2 classes from 10am to 11:30am and 2pm to 3:30pm, team sync at 4pm, and 2 hours for my compiler lab."
        ],
    )
    client_timezone: str = Field(
        default="UTC",
        description="User's IANA timezone string (e.g. 'America/New_York', 'UTC')",
        examples=["America/New_York"],
    )
    target_date: date | None = Field(
        default=None,
        description="Optional explicit override for target date. If omitted, extracted from message or defaults to today/tomorrow.",
    )


class PlanProposalResponse(BaseModel):
    """Proposal returned to the user for review before any persistence or action execution."""

    proposal_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique proposal UUID"
    )
    original_prompt: str = Field(..., description="The user's original unadulterated instruction")
    target_date: date = Field(..., description="Target date for the plan")
    intent: PlanIntent = Field(..., description="Detected intent")
    explanation: str = Field(..., description="Explanation of what was understood")
    fixed_events: list[DetectedFixedEvent] = Field(
        default_factory=list, description="Extracted fixed events"
    )
    tasks: list[DetectedTask] = Field(default_factory=list, description="Extracted tasks")
    missing_information: list[str] = Field(
        default_factory=list, description="List of missing critical fields preventing scheduling"
    )
    clarification_question: str | None = Field(
        default=None, description="Concise question asking for missing information"
    )
    requires_confirmation: bool = Field(
        ...,
        description="True if proposal is complete and ready for confirmation; False if clarification needed",
    )
    parser_used: ParserType = Field(
        ...,
        description="Accurate disclosure of parser used ('gemini', 'groq', 'deterministic_offline')",
    )
    fallback_applied: bool = Field(
        default=False,
        description="True if primary AI failed and fallback parser was engaged",
    )
    preview_schedule: ScheduleProposal | None = Field(
        default=None,
        description="Dry-run schedule calculated by Day 5 deterministic solver (not yet persisted)",
    )


class PlanConfirmRequest(BaseModel):
    """Explicit confirmation payload from the user accepting the proposed plan."""

    proposal_id: str | None = Field(default=None, description="Proposal UUID if available")
    target_date: date = Field(..., description="Target schedule date")
    tasks: list[TaskCreateRequest] = Field(
        ...,
        min_length=0,
        description="Tasks to persist (may include user edits made during proposal review)",
    )
    fixed_events: list[DetectedFixedEvent] = Field(
        default_factory=list,
        description="Fixed events to persist as CalendarEvent records",
    )
    persist_tasks: bool = Field(
        default=True, description="Whether to persist the confirmed tasks to database"
    )
    generate_schedule: bool = Field(
        default=True,
        description="Whether to run Day 5 deterministic scheduler and persist schedule blocks",
    )


class PlanConfirmResponse(BaseModel):
    """Response returned after user confirms a proposed plan."""

    target_date: date
    created_tasks: list[TaskResponse] = Field(default_factory=list)
    created_events: list[dict[str, Any]] = Field(default_factory=list)
    schedule: ScheduleProposal | None = Field(default=None)
    persisted_schedule_id: str | None = Field(default=None)
    status: str = Field(default="confirmed")
