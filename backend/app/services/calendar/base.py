"""Abstract calendar provider interface and calendar domain exceptions."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.core.errors import AppException
from app.services.calendar.models import (
    CalendarEventCreate,
    NormalizedCalendarEvent,
    OAuthTokenData,
)


class CalendarProviderException(AppException):
    """Base exception for calendar provider operations."""

    def __init__(self, detail: str = "Calendar operation failed", status_code: int = 502):
        super().__init__(
            detail=detail, status_code=status_code, error_code="CALENDAR_PROVIDER_ERROR"
        )


class CalendarAuthExpiredException(CalendarProviderException):
    """Access token expired and requires refresh."""

    def __init__(self, detail: str = "Calendar authorization token has expired"):
        super().__init__(detail=detail, status_code=401)
        self.error_code = "CALENDAR_TOKEN_EXPIRED"


class CalendarAuthRevokedException(CalendarProviderException):
    """User revoked access or refresh token is invalid."""

    def __init__(self, detail: str = "Calendar authorization has been revoked by user or provider"):
        super().__init__(detail=detail, status_code=401)
        self.error_code = "CALENDAR_ACCESS_REVOKED"


class CalendarRateLimitException(CalendarProviderException):
    """Calendar provider rate limit reached (HTTP 429)."""

    def __init__(self, detail: str = "Calendar provider rate limit exceeded. Please retry later."):
        super().__init__(detail=detail, status_code=429)
        self.error_code = "CALENDAR_RATE_LIMITED"


class CalendarTimeoutException(CalendarProviderException):
    """Provider network call timed out."""

    def __init__(self, detail: str = "Calendar provider request timed out"):
        super().__init__(detail=detail, status_code=504)
        self.error_code = "CALENDAR_TIMEOUT"


class CalendarProvider(ABC):
    """Abstract interface defining required capabilities for any calendar provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'google_calendar')."""
        ...

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Build the OAuth authorization URL with required scopes and CSRF state."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthTokenData:
        """Exchange authorization code for access and refresh tokens."""
        ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> OAuthTokenData:
        """Obtain a fresh access token using a refresh token."""
        ...

    @abstractmethod
    async def revoke_token(self, token: str) -> bool:
        """Revoke an active access or refresh token with the provider."""
        ...

    @abstractmethod
    async def list_events(
        self, access_token: str, start_time: datetime, end_time: datetime
    ) -> list[NormalizedCalendarEvent]:
        """Retrieve and normalize events between start_time and end_time."""
        ...

    @abstractmethod
    async def get_event(
        self, access_token: str, external_id: str
    ) -> NormalizedCalendarEvent | None:
        """Truthful post-condition check: fetch an individual event by external ID."""
        ...

    @abstractmethod
    async def create_event(
        self, access_token: str, event_data: CalendarEventCreate
    ) -> NormalizedCalendarEvent:
        """Create an event on the external calendar."""
        ...

    @abstractmethod
    async def delete_event(self, access_token: str, external_id: str) -> bool:
        """Delete an event on the external calendar."""
        ...
