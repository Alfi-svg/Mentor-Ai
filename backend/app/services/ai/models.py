"""Data structures and context definitions for AI adapters."""

from datetime import date, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.planner import DraftPlan, ParserType


class ExistingItemSummary(BaseModel):
    """Brief summary of an existing task or calendar event provided for context."""

    id: str
    title: str
    start_time: str | None = None
    end_time: str | None = None
    duration_minutes: int | None = None
    priority: str | None = None


class UserPlanContext(BaseModel):
    """Contextual user information provided to the AI planning prompt."""

    current_date: date = Field(..., description="Today's date in user's timezone")
    timezone: str = Field(default="UTC", description="IANA timezone name")
    work_start_time: time = Field(default=time(9, 0), description="Configured work day start")
    work_end_time: time = Field(default=time(18, 0), description="Configured work day end")
    buffer_minutes: int = Field(default=15, description="Meeting buffer requirement")
    existing_events: list[ExistingItemSummary] = Field(
        default_factory=list, description="Already committed calendar events for target day"
    )
    existing_tasks: list[ExistingItemSummary] = Field(
        default_factory=list, description="Existing pending tasks in user's backlog"
    )

    model_config = ConfigDict(extra="ignore")


class LLMParseResult(BaseModel):
    """Result of an AI adapter parsing operation."""

    draft_plan: DraftPlan
    parser_used: ParserType
    fallback_applied: bool = False
    raw_response: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
