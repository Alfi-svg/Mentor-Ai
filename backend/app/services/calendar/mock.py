"""In-memory mock calendar provider for deterministic tests and offline development."""

import uuid
from datetime import UTC, datetime, timedelta

from app.services.calendar.base import (
    CalendarAuthExpiredException,
    CalendarAuthRevokedException,
    CalendarProvider,
    CalendarProviderException,
    CalendarRateLimitException,
)
from app.services.calendar.models import (
    CalendarEventCreate,
    CalendarEventUpdate,
    NormalizedCalendarEvent,
    OAuthTokenData,
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class MockCalendarAdapter(CalendarProvider):
    """In-memory test double for CalendarProvider interface."""

    def __init__(self) -> None:
        # In-memory event storage keyed by access_token or external_id
        self._events: dict[str, NormalizedCalendarEvent] = {}
        # Fault injection toggles
        self.simulate_rate_limit: bool = False
        self.simulate_token_expired: bool = False
        self.simulate_token_revoked: bool = False
        self.simulate_read_verification_failure: bool = False

    @property
    def provider_name(self) -> str:
        return "mock_google_calendar"

    def get_authorization_url(self, state: str) -> str:
        return f"https://mock.google.com/oauth/authorize?state={state}&scope=calendar.events"

    async def exchange_code(self, code: str) -> OAuthTokenData:
        if self.simulate_token_revoked:
            raise CalendarAuthRevokedException("Mock: Revoked code exchange.")

        return OAuthTokenData(
            access_token=f"mock_access_token_{code}",
            refresh_token=f"mock_refresh_token_{code}",
            token_type="Bearer",  # noqa: S106
            expires_in=3600,
            expires_at=datetime.now(UTC) + timedelta(seconds=3600),
            scopes=["https://www.googleapis.com/auth/calendar.events"],
            account_email="student.test@university.edu",
        )

    async def refresh_token(self, refresh_token: str) -> OAuthTokenData:
        if self.simulate_token_revoked:
            raise CalendarAuthRevokedException("Mock: Revoked refresh token.")

        return OAuthTokenData(
            access_token=f"mock_refreshed_access_{uuid.uuid4().hex[:8]}",
            refresh_token=refresh_token,
            token_type="Bearer",  # noqa: S106
            expires_in=3600,
            expires_at=datetime.now(UTC) + timedelta(seconds=3600),
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )

    async def revoke_token(self, token: str) -> bool:
        return True

    async def list_events(
        self, access_token: str, start_time: datetime, end_time: datetime
    ) -> list[NormalizedCalendarEvent]:
        if self.simulate_rate_limit:
            raise CalendarRateLimitException("Mock: Rate limit reached.")
        if self.simulate_token_expired:
            raise CalendarAuthExpiredException("Mock: Access token expired.")
        if self.simulate_token_revoked:
            raise CalendarAuthRevokedException("Mock: Access token revoked.")

        matching: list[NormalizedCalendarEvent] = []
        for ev in self._events.values():
            # Check overlap: ev.start < end and ev.end > start
            if ev.start_time < end_time and ev.end_time > start_time:
                matching.append(ev)

        matching.sort(key=lambda x: x.start_time)
        return matching

    async def get_event(
        self, access_token: str, external_id: str
    ) -> NormalizedCalendarEvent | None:
        if self.simulate_read_verification_failure:
            return None
        return self._events.get(external_id)

    async def create_event(
        self, access_token: str, event_data: CalendarEventCreate
    ) -> NormalizedCalendarEvent:
        if self.simulate_rate_limit:
            raise CalendarRateLimitException()
        if self.simulate_token_expired:
            raise CalendarAuthExpiredException()

        ext_id = f"mock_evt_{uuid.uuid4().hex[:12]}"
        created = NormalizedCalendarEvent(
            external_id=ext_id,
            title=event_data.title,
            description=event_data.description,
            start_time=_ensure_utc(event_data.start_time),
            end_time=_ensure_utc(event_data.end_time),
            is_all_day=event_data.is_all_day,
            location=event_data.location,
            status="confirmed",
            html_link=f"https://mock.google.com/calendar/event?id={ext_id}",
        )
        self._events[ext_id] = created

        # Read verification probe
        verified = await self.get_event(access_token, ext_id)
        if not verified:
            raise CalendarProviderException(
                f"Post-condition verification failed: event {ext_id} could not be read back."
            )

        return verified

    async def update_event(
        self, access_token: str, external_id: str, event_data: CalendarEventUpdate
    ) -> NormalizedCalendarEvent:
        if self.simulate_rate_limit:
            raise CalendarRateLimitException()
        if self.simulate_token_expired:
            raise CalendarAuthExpiredException()

        existing = self._events.get(external_id)
        if not existing:
            raise CalendarProviderException(
                f"Event {external_id} not found in mock calendar store", status_code=404
            )

        title = event_data.title if event_data.title is not None else existing.title
        description = (
            event_data.description if event_data.description is not None else existing.description
        )
        location = event_data.location if event_data.location is not None else existing.location
        status = event_data.status if event_data.status is not None else existing.status
        is_all_day = (
            event_data.is_all_day if event_data.is_all_day is not None else existing.is_all_day
        )
        start_time = (
            _ensure_utc(event_data.start_time)
            if event_data.start_time is not None
            else existing.start_time
        )
        end_time = (
            _ensure_utc(event_data.end_time)
            if event_data.end_time is not None
            else existing.end_time
        )

        updated = NormalizedCalendarEvent(
            external_id=external_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            is_all_day=is_all_day,
            location=location,
            status=status,
            html_link=existing.html_link,
        )
        self._events[external_id] = updated

        if self.simulate_read_verification_failure:
            raise CalendarProviderException(
                f"Post-condition verification failed: event {external_id} could not be read back."
            )

        return updated

    async def delete_event(self, access_token: str, external_id: str) -> bool:
        if external_id in self._events:
            del self._events[external_id]
            return True
        return False

    def seed_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        location: str | None = None,
        is_all_day: bool = False,
    ) -> NormalizedCalendarEvent:
        """Helper for test fixtures to pre-populate simulated events."""
        ext_id = f"mock_seed_{uuid.uuid4().hex[:8]}"
        ev = NormalizedCalendarEvent(
            external_id=ext_id,
            title=title,
            start_time=start_time.astimezone(UTC),
            end_time=end_time.astimezone(UTC),
            location=location,
            is_all_day=is_all_day,
            status="confirmed",
        )
        self._events[ext_id] = ev
        return ev
