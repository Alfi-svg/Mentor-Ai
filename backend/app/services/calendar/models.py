"""Pydantic schemas and transfer objects for Calendar integration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OAuthTokenData(BaseModel):
    """Normalized OAuth token bundle returned by providers."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int = 3600
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)
    account_email: str | None = None


class NormalizedCalendarEvent(BaseModel):
    """Normalized, timezone-aware calendar event representation."""

    model_config = ConfigDict(from_attributes=True)

    external_id: str
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    location: str | None = None
    status: str = "confirmed"  # confirmed, tentative, cancelled
    html_link: str | None = None
    etag: str | None = None


class CalendarEventCreate(BaseModel):
    """Payload to create an event on an external calendar provider."""

    title: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    is_all_day: bool = False


class CalendarStatusResponse(BaseModel):
    """Status of user's external calendar connection."""

    provider: str
    is_connected: bool
    configured: bool
    status_label: str
    account_email: str | None = None
    last_synced_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


class CalendarConnectResponse(BaseModel):
    """OAuth initiation response with signed authorization URL."""

    authorization_url: str
    state: str
    provider: str


class CalendarSyncResponse(BaseModel):
    """Result of calendar synchronization."""

    synced_count: int
    provider: str
    last_synced_at: datetime
    events: list[dict[str, Any]] = Field(default_factory=list)


class ConflictCheckResponse(BaseModel):
    """Scheduling conflict analysis against calendar events."""

    target_date: str
    has_conflicts: bool
    conflicting_events: list[dict[str, Any]] = Field(default_factory=list)
    total_busy_minutes: int
    free_slots: list[dict[str, Any]] = Field(default_factory=list)
