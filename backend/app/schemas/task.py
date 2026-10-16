"""Task request and response Pydantic validation schemas."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]
TaskPriority = Literal["P1", "P2", "P3", "P4"]
EnergyLevel = Literal["high", "medium", "low"]
TaskSortBy = Literal["created_at", "updated_at", "deadline", "priority", "duration_minutes"]
SortOrder = Literal["asc", "desc"]


class TaskConstraints(BaseModel):
    """Optional scheduling availability constraints for a task."""

    earliest_start: str | None = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$",
        description="Earliest permissible start time in HH:MM format",
    )
    latest_end: str | None = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$",
        description="Latest permissible end time in HH:MM format",
    )
    allowed_days: list[int] | None = Field(
        default=None,
        description="Permissible days of the week (1=Monday ... 7=Sunday)",
    )
    preferred_time_of_day: Literal["morning", "afternoon", "evening"] | None = Field(
        default=None,
        description="Preferred energy block alignment",
    )

    model_config = ConfigDict(extra="allow")


class TaskCreateRequest(BaseModel):
    """Task creation payload."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Task title (trimmed, 1-200 characters)",
        examples=["Complete Operating Systems Lab 2"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional detailed description or acceptance notes",
        examples=["Multi-threaded process scheduler in C"],
    )
    priority: TaskPriority = Field(
        default="P3",
        description="Task priority level (P1=Urgent/Highest to P4=Lowest)",
        examples=["P1"],
    )
    duration_minutes: int = Field(
        default=45,
        ge=1,
        le=720,
        description="Estimated duration in minutes (1 to 720 minutes = 12 hours)",
        examples=[120],
    )
    deadline: datetime | None = Field(
        default=None,
        description="Optional timezone-aware completion deadline (converted and stored in UTC)",
        examples=["2026-10-15T23:59:59Z"],
    )
    energy_level: EnergyLevel = Field(
        default="medium",
        description="Required cognitive energy level",
        examples=["high"],
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Categorization tags (max 20 tags, each up to 50 characters)",
        examples=[["cs301", "lab"]],
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom or availability constraints (e.g. earliest_start, latest_end)",
    )
    scheduled_start: datetime | None = Field(
        default=None,
        description="Designated calendar execution start time",
    )
    scheduled_end: datetime | None = Field(
        default=None,
        description="Designated calendar execution end time",
    )
    status: TaskStatus = Field(
        default="pending",
        description="Initial status",
    )
    scheduling_preference: Literal["auto", "manual", "unscheduled"] | None = Field(
        default=None,
        description="Explicit scheduling preference: auto (solve slot), manual (use timestamps), or unscheduled (backlog only)",
    )

    @model_validator(mode="before")
    @classmethod
    def pre_validate_and_normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Map duration aliases
            if data.get("duration_minutes") is None:
                est = data.get("estimated_duration_minutes")
                if est is not None:
                    data["duration_minutes"] = est
                else:
                    data["duration_minutes"] = 45

            # 2. Handle empty or null deadline
            dl = data.get("deadline")
            if dl == "" or dl is None:
                data["deadline"] = None

            # 3. Handle energy_level null or default
            el = data.get("energy_level")
            if not el:
                data["energy_level"] = "medium"
            elif isinstance(el, str):
                el_lower = el.lower().strip()
                if el_lower in ("high", "medium", "low"):
                    data["energy_level"] = el_lower
                else:
                    data["energy_level"] = el

            # 4. Handle priority normalization
            p = data.get("priority")
            if not p:
                data["priority"] = "P3"
            elif isinstance(p, str):
                p_upper = p.upper().strip()
                if p_upper in ("P1", "P2", "P3", "P4"):
                    data["priority"] = p_upper
                elif p_upper in ("HIGH", "URGENT"):
                    data["priority"] = "P1"
                elif p_upper in ("MEDIUM", "NORMAL"):
                    data["priority"] = "P2"
                elif p_upper in ("LOW",):
                    data["priority"] = "P3"
                else:
                    # Keep original value so Pydantic raises validation error for invalid priorities like 'P5'
                    data["priority"] = p
        return data

    @field_validator("title", mode="after")
    @classmethod
    def clean_title(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Task title cannot be empty or whitespace only")
        return trimmed

    @field_validator("deadline", "scheduled_start", "scheduled_end", mode="after")
    @classmethod
    def normalize_deadline(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            # Naive datetime treated as UTC
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    @field_validator("tags", mode="after")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in v:
            t = tag.strip().lower()
            if t and len(t) <= 50 and t not in cleaned:
                cleaned.append(t)
        return cleaned


class TaskUpdateRequest(BaseModel):
    """Task update payload for partial updates."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated task title",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Updated description (pass empty string or null to clear)",
    )
    priority: TaskPriority | None = Field(
        default=None,
        description="Updated priority",
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=720,
        description="Updated estimated duration in minutes",
    )
    deadline: datetime | None = Field(
        default=None,
        description="Updated timezone-aware completion deadline",
    )
    energy_level: EnergyLevel | None = Field(
        default=None,
        description="Updated cognitive energy level",
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Updated tags",
    )
    constraints: dict[str, Any] | None = Field(
        default=None,
        description="Updated scheduling availability constraints",
    )
    scheduled_start: datetime | None = Field(
        default=None,
        description="Updated designated calendar start time",
    )
    scheduled_end: datetime | None = Field(
        default=None,
        description="Updated designated calendar end time",
    )
    google_calendar_event_id: str | None = Field(
        default=None,
        description="Linked Google Calendar event ID",
    )
    calendar_sync_status: str | None = Field(
        default=None,
        description="Calendar sync status (unsynced, synced, pending, failed)",
    )
    calendar_sync_error: str | None = Field(
        default=None,
        description="Last calendar sync error message if any",
    )
    last_synced_at: datetime | None = Field(
        default=None,
        description="Timestamp of last successful calendar sync",
    )
    status: TaskStatus | None = Field(
        default=None,
        description="Updated task lifecycle status",
    )
    is_archived: bool | None = Field(
        default=None,
        description="Archive or unarchive the task",
    )

    @field_validator("title", mode="after")
    @classmethod
    def clean_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Task title cannot be empty or whitespace only")
        return trimmed

    @field_validator("deadline", "scheduled_start", "scheduled_end", "last_synced_at", mode="after")
    @classmethod
    def normalize_deadline(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    @field_validator("tags", mode="after")
    @classmethod
    def clean_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for tag in v:
            t = tag.strip().lower()
            if t and len(t) <= 50 and t not in cleaned:
                cleaned.append(t)
        return cleaned


class TaskResponse(BaseModel):
    """Full task response representation."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None = None
    status: str
    priority: str
    duration_minutes: int
    deadline: datetime | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    google_calendar_event_id: str | None = None
    calendar_sync_status: str = "unsynced"
    calendar_sync_error: str | None = None
    last_synced_at: datetime | None = None
    energy_level: str
    tags: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "deadline",
        "scheduled_start",
        "scheduled_end",
        "last_synced_at",
        "created_at",
        "updated_at",
        mode="after",
    )
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class TaskListResponse(BaseModel):
    """Paginated task collection response."""

    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskAutoScheduleResponse(BaseModel):
    """Result of attempting auto-scheduling for a task."""

    task: TaskResponse
    scheduled: bool
    message: str
