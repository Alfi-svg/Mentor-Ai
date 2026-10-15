"""Calendar domain service orchestrating provider interactions, token refresh, and persistence."""

import uuid
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import (
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    verify_oauth_state,
)
from app.core.errors import AppException
from app.core.logging import get_logger
from app.db.models.action import AuditLog
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.profile import UserPreferences
from app.services.calendar.base import (
    CalendarAuthExpiredException,
    CalendarAuthRevokedException,
    CalendarProvider,
)
from app.services.calendar.google import GoogleCalendarAdapter
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.models import (
    CalendarConnectResponse,
    CalendarEventCreate,
    CalendarStatusResponse,
    CalendarSyncResponse,
    ConflictCheckResponse,
)

logger = get_logger("mentor_ai.calendar.service")


def _ensure_utc(dt: datetime) -> datetime:
    """Guarantee datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class CalendarService:
    """Manages calendar connections, synchronization, token lifecycle, and event persistence."""

    _provider_override: CalendarProvider | None = None

    @classmethod
    def get_provider(cls) -> CalendarProvider:
        """Resolve the active calendar provider adapter."""
        if cls._provider_override is not None:
            return cls._provider_override
        if settings.CALENDAR_PROVIDER == "mock":
            return MockCalendarAdapter()
        return GoogleCalendarAdapter()

    @classmethod
    def set_provider_override(cls, provider: CalendarProvider | None) -> None:
        """Inject test mock provider for unit tests."""
        cls._provider_override = provider

    @classmethod
    async def get_connect_url(cls, user_id: uuid.UUID) -> CalendarConnectResponse:
        """Generate authorization URL and state token for user."""
        provider = cls.get_provider()
        state = generate_oauth_state(user_id=user_id, provider=provider.provider_name)
        auth_url = provider.get_authorization_url(state=state)

        return CalendarConnectResponse(
            authorization_url=auth_url,
            state=state,
            provider=provider.provider_name,
        )

    @classmethod
    async def handle_callback(
        cls, code: str, state: str, db: AsyncSession
    ) -> tuple[ExternalConnection, str | None]:
        """Verify state, exchange code, encrypt tokens, and persist connection."""
        provider = cls.get_provider()
        user_id = verify_oauth_state(state=state, expected_provider=provider.provider_name)

        # Exchange authorization code for tokens
        token_data = await provider.exchange_code(code)

        # Encrypt tokens for storage at rest
        enc_access = encrypt_token(token_data.access_token)
        enc_refresh = encrypt_token(token_data.refresh_token) if token_data.refresh_token else None

        # Look for existing connection
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        now = datetime.now(UTC)
        if conn is None:
            conn = ExternalConnection(
                id=uuid.uuid4(),
                user_id=user_id,
                provider="google_calendar",
                provider_account_id=token_data.account_email,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                token_expires_at=token_data.expires_at,
                scopes=token_data.scopes,
                status="connected",
                metadata_json={"token_type": token_data.token_type},
                created_at=now,
                updated_at=now,
            )
            db.add(conn)
        else:
            conn.encrypted_access_token = enc_access
            if enc_refresh:
                conn.encrypted_refresh_token = enc_refresh
            conn.token_expires_at = token_data.expires_at
            conn.scopes = token_data.scopes
            conn.status = "connected"
            if token_data.account_email:
                conn.provider_account_id = token_data.account_email
            conn.updated_at = now

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="calendar_connected",
            resource_type="external_connection",
            resource_id=str(conn.id),
            details={"provider": "google_calendar", "email": token_data.account_email},
            created_at=now,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(conn)

        logger.info(
            "Calendar connection established",
            user_id=str(user_id),
            email=token_data.account_email,
        )
        return conn, token_data.account_email

    @classmethod
    async def disconnect(cls, user_id: uuid.UUID, db: AsyncSession) -> bool:
        """Revoke token at provider and mark connection as disconnected."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn:
            return True

        # Attempt provider token revocation if token is available
        if conn.encrypted_access_token:
            try:
                raw_token = decrypt_token(conn.encrypted_access_token)
                provider = cls.get_provider()
                await provider.revoke_token(raw_token)
            except Exception as exc:
                logger.warning("Could not revoke token with provider", error=str(exc))

        conn.status = "disconnected"
        conn.encrypted_access_token = None
        conn.encrypted_refresh_token = None
        conn.updated_at = datetime.now(UTC)

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="calendar_disconnected",
            resource_type="external_connection",
            resource_id=str(conn.id),
            details={"provider": "google_calendar"},
            created_at=datetime.now(UTC),
        )
        db.add(audit)
        await db.commit()

        logger.info("Calendar disconnected", user_id=str(user_id))
        return True

    @classmethod
    async def get_status(cls, user_id: uuid.UUID, db: AsyncSession) -> CalendarStatusResponse:
        """Return user calendar connection state truthfully."""
        configured = settings.has_google_calendar_credentials or cls._provider_override is not None

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not configured:
            return CalendarStatusResponse(
                provider="google_calendar",
                is_connected=False,
                configured=False,
                status_label="Not Connected (OAuth Credentials Not Configured)",
            )

        if not conn or conn.status != "connected":
            status_text = "Not Connected"
            if conn and conn.status == "revoked":
                status_text = "Disconnected (Access Revoked)"
            elif conn and conn.status == "expired":
                status_text = "Disconnected (Token Expired)"
            return CalendarStatusResponse(
                provider="google_calendar",
                is_connected=False,
                configured=True,
                status_label=status_text,
                account_email=conn.provider_account_id if conn else None,
                last_synced_at=conn.last_synced_at if conn else None,
            )

        return CalendarStatusResponse(
            provider="google_calendar",
            is_connected=True,
            configured=True,
            status_label="Connected",
            account_email=conn.provider_account_id,
            last_synced_at=conn.last_synced_at,
            scopes=conn.scopes,
        )

    @classmethod
    async def get_valid_access_token(cls, conn: ExternalConnection, db: AsyncSession) -> str:
        """Decrypt access token and automatically refresh if expired."""
        if not conn.encrypted_access_token:
            raise CalendarAuthRevokedException(
                "No access token available. Please reconnect calendar."
            )

        now = datetime.now(UTC)
        is_expired = False
        if conn.token_expires_at is not None:
            exp_utc = _ensure_utc(conn.token_expires_at)
            is_expired = exp_utc <= (now + timedelta(seconds=60))

        if not is_expired:
            return decrypt_token(conn.encrypted_access_token)

        # Token is expired; attempt refresh
        if not conn.encrypted_refresh_token:
            conn.status = "expired"
            await db.commit()
            raise CalendarAuthExpiredException(
                "Access token expired and no refresh token available."
            )

        refresh_tok = decrypt_token(conn.encrypted_refresh_token)
        provider = cls.get_provider()

        try:
            new_tokens = await provider.refresh_token(refresh_tok)
        except CalendarAuthRevokedException:
            conn.status = "revoked"
            conn.encrypted_access_token = None
            await db.commit()
            raise

        conn.encrypted_access_token = encrypt_token(new_tokens.access_token)
        conn.token_expires_at = new_tokens.expires_at
        conn.updated_at = now
        await db.commit()

        logger.info("OAuth access token refreshed successfully", user_id=str(conn.user_id))
        return new_tokens.access_token

    @classmethod
    async def sync_events(
        cls,
        user_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
        db: AsyncSession,
    ) -> CalendarSyncResponse:
        """Fetch provider events, normalize, and upsert into calendar_events table."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
            ExternalConnection.status == "connected",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn:
            raise AppException("Calendar is not connected for this user.", status_code=400)

        access_token = await cls.get_valid_access_token(conn, db)
        provider = cls.get_provider()

        normalized_events = await provider.list_events(access_token, start_time, end_time)

        # Upsert normalized events into database
        synced_count = 0
        events_summary: list[dict[str, Any]] = []

        for ev in normalized_events:
            ev_stmt = select(CalendarEvent).where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.external_id == ev.external_id,
            )
            ev_res = await db.execute(ev_stmt)
            existing = ev_res.scalar_one_or_none()

            if existing is None:
                new_event = CalendarEvent(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    title=ev.title,
                    description=ev.description,
                    start_time=ev.start_time,
                    end_time=ev.end_time,
                    is_all_day=ev.is_all_day,
                    is_fixed=True,
                    source="google_calendar",
                    external_id=ev.external_id,
                    location=ev.location,
                    created_at=datetime.now(UTC),
                )
                db.add(new_event)
            else:
                existing.title = ev.title
                existing.description = ev.description
                existing.start_time = ev.start_time
                existing.end_time = ev.end_time
                existing.is_all_day = ev.is_all_day
                existing.location = ev.location

            synced_count += 1
            events_summary.append(
                {
                    "external_id": ev.external_id,
                    "title": ev.title,
                    "start_time": ev.start_time.isoformat(),
                    "end_time": ev.end_time.isoformat(),
                    "is_all_day": ev.is_all_day,
                    "location": ev.location,
                }
            )

        # Delete removed/cancelled events previously synced from Google Calendar in this time window
        fetched_ext_ids = {ev.external_id for ev in normalized_events}
        del_stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.source == "google_calendar",
            CalendarEvent.start_time < end_time,
            CalendarEvent.end_time > start_time,
        )
        del_res = await db.execute(del_stmt)
        existing_in_range = list(del_res.scalars().all())
        for old_ev in existing_in_range:
            if old_ev.external_id and old_ev.external_id not in fetched_ext_ids:
                await db.delete(old_ev)

        now = datetime.now(UTC)
        conn.last_synced_at = now
        await db.commit()

        logger.info(
            "Calendar sync complete",
            user_id=str(user_id),
            synced_count=synced_count,
        )

        return CalendarSyncResponse(
            synced_count=synced_count,
            provider="google_calendar",
            last_synced_at=now,
            events=events_summary,
        )

    @classmethod
    async def create_calendar_event(
        cls,
        user_id: uuid.UUID,
        event_data: CalendarEventCreate,
        db: AsyncSession,
    ) -> tuple[CalendarEvent, bool]:
        """Create a calendar event; pushes to Google Calendar if connected and verifies with follow-up read."""
        # Check if an identical event already exists to prevent duplicate creation on action retries
        start_utc = event_data.start_time.astimezone(UTC)
        end_utc = event_data.end_time.astimezone(UTC)
        dup_stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.title == event_data.title,
            CalendarEvent.start_time == start_utc,
            CalendarEvent.end_time == end_utc,
        )
        dup_res = await db.execute(dup_stmt)
        dup_event = dup_res.scalar_one_or_none()
        if dup_event:
            logger.info("reconciled_existing_event_on_retry", event_id=str(dup_event.id))
            return dup_event, (dup_event.source == "google_calendar")

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
            ExternalConnection.status == "connected",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        external_id: str | None = None
        pushed_to_remote = False

        if conn:
            try:
                access_token = await cls.get_valid_access_token(conn, db)
                provider = cls.get_provider()
                # create_event performs follow-up read verification internally
                remote_event = await provider.create_event(access_token, event_data)
                external_id = remote_event.external_id
                pushed_to_remote = True
            except Exception as exc:
                logger.error(
                    "Failed to create event on remote calendar provider",
                    user_id=str(user_id),
                    error=str(exc),
                )
                raise

        event = CalendarEvent(
            id=uuid.uuid4(),
            user_id=user_id,
            title=event_data.title,
            description=event_data.description,
            start_time=start_utc,
            end_time=end_utc,
            is_all_day=event_data.is_all_day,
            is_fixed=True,
            source="google_calendar" if pushed_to_remote else "internal",
            external_id=external_id,
            location=event_data.location,
            created_at=datetime.now(UTC),
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)

        return event, pushed_to_remote

    @classmethod
    async def detect_conflicts(
        cls,
        user_id: uuid.UUID,
        target_date: date,
        db: AsyncSession,
    ) -> ConflictCheckResponse:
        """Detect conflicts and calculate busy/free slots for a specific target date."""
        day_start = datetime.combine(target_date, dtime.min, tzinfo=UTC)
        day_end = datetime.combine(target_date, dtime.max, tzinfo=UTC)

        # Query user preferences for working hours
        pref_res = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        pref = pref_res.scalar_one_or_none()
        work_start = pref.work_start_time if pref else "09:00:00"
        work_end = pref.work_end_time if pref else "18:00:00"

        # Query existing calendar events on that day
        stmt = (
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.start_time < day_end,
                CalendarEvent.end_time > day_start,
            )
            .order_by(CalendarEvent.start_time.asc())
        )

        res = await db.execute(stmt)
        events = list(res.scalars().all())

        conflicts: list[dict[str, Any]] = []
        total_busy_minutes = 0

        for ev in events:
            s_utc = _ensure_utc(ev.start_time)
            e_utc = _ensure_utc(ev.end_time)
            duration_mins = int((e_utc - s_utc).total_seconds() / 60)
            total_busy_minutes += duration_mins
            conflicts.append(
                {
                    "id": str(ev.id),
                    "external_id": ev.external_id,
                    "title": ev.title,
                    "start_time": s_utc.isoformat(),
                    "end_time": e_utc.isoformat(),
                    "duration_minutes": duration_mins,
                    "source": ev.source,
                    "location": ev.location,
                }
            )

        # Calculate free slots within working hours
        wh_start = datetime.combine(
            target_date,
            datetime.strptime(work_start, "%H:%M:%S").time(),
            tzinfo=UTC,
        )
        wh_end = datetime.combine(
            target_date,
            datetime.strptime(work_end, "%H:%M:%S").time(),
            tzinfo=UTC,
        )

        free_slots: list[dict[str, Any]] = []
        current_cursor = wh_start

        for ev in events:
            s_utc = _ensure_utc(ev.start_time)
            e_utc = _ensure_utc(ev.end_time)
            ev_start = max(s_utc, wh_start)
            ev_end = min(e_utc, wh_end)

            if ev_start > current_cursor:
                gap_mins = int((ev_start - current_cursor).total_seconds() / 60)
                if gap_mins >= 15:
                    free_slots.append(
                        {
                            "start_time": current_cursor.isoformat(),
                            "end_time": ev_start.isoformat(),
                            "duration_minutes": gap_mins,
                        }
                    )
            if ev_end > current_cursor:
                current_cursor = ev_end

        if current_cursor < wh_end:
            gap_mins = int((wh_end - current_cursor).total_seconds() / 60)
            if gap_mins >= 15:
                free_slots.append(
                    {
                        "start_time": current_cursor.isoformat(),
                        "end_time": wh_end.isoformat(),
                        "duration_minutes": gap_mins,
                    }
                )

        return ConflictCheckResponse(
            target_date=target_date.isoformat(),
            has_conflicts=len(conflicts) > 0,
            conflicting_events=conflicts,
            total_busy_minutes=total_busy_minutes,
            free_slots=free_slots,
        )
