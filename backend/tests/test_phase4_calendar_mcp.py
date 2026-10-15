"""Phase 4 comprehensive automated test suite for Mentor AI.

Covers all Phase 4 requirements:
1. OAuth state validation (HMAC signature, tamper detection, TTL expiration).
2. Missing credentials handling and truthful unconfigured status.
3. Token encryption and decryption at rest (Fernet key derivation, IV uniqueness).
4. Expired-token auto-refresh behavior.
5. Revoked or invalid credentials handling and connection status update.
6. User connection isolation (multi-tenant boundary).
7. Calendar pagination (nextPageToken traversal).
8. Duplicate-event prevention (stable external_id upsert).
9. Event update and deletion synchronization.
10. Timezone normalization and all-day UTC boundary handling.
11. Free-slot and conflict calculation with fixed events and buffers.
12. Calendar API failure and recovery (rate limit backoff, timeout).
13. MCP input validation and authorization scoping (user_id spoofing prevention).
14. Write-action approval policy enforcement (staged pending human approval).
15. Idempotent action execution and duplicate prevention on retry.
16. External outcome verification probe.
17. Integration with deterministic scheduler warnings.
"""

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.crypto import (
    CryptoException,
    StateValidationException,
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    verify_oauth_state,
)
from app.core.errors import AppException, EntityNotFoundException
from app.db.base import Base
from app.db.models.action import ActionHistory
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.profile import Profile, UserPreferences
from app.schemas.action import ActionConfirmRequest
from app.services.action_service import ActionService
from app.services.calendar.base import (
    CalendarAuthExpiredException,
    CalendarAuthRevokedException,
    CalendarProviderException,
    CalendarRateLimitException,
    CalendarTimeoutException,
)
from app.services.calendar.google import GoogleCalendarAdapter
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.models import CalendarEventCreate, OAuthTokenData
from app.services.calendar.service import CalendarService
from app.services.mcp.server import (
    authenticated_mcp_user,
    create_calendar_event,
    get_calendar_events,
    get_user_context,
    list_tasks,
    validate_mcp_user_authorization,
    verify_action,
)
from app.services.scheduler.service import SchedulerService


@pytest.fixture
async def test_db():
    """Create an isolated in-memory async SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_provider():
    """Ensure CalendarService provider override is reset after each test."""
    CalendarService.set_provider_override(None)
    yield
    CalendarService.set_provider_override(None)


# -----------------------------------------------------------------------------
# 1. OAuth State Validation (CSRF & Tamper Resistance)
# -----------------------------------------------------------------------------
def test_oauth_state_generation_and_verification():
    """Test HMAC state generation, tamper detection, and TTL expiration."""
    user_id = uuid.uuid4()
    state = generate_oauth_state(user_id=user_id, provider="google_calendar", expires_in_seconds=300)

    # 1. Valid state verifies and extracts user_id
    extracted_uid = verify_oauth_state(state=state, expected_provider="google_calendar")
    assert extracted_uid == user_id

    # 2. Tampered signature is rejected
    tampered_state = state[:-4] + "abcd"
    with pytest.raises(StateValidationException) as exc:
        verify_oauth_state(state=tampered_state, expected_provider="google_calendar")
    assert "signature verification failed" in str(exc.value).lower()

    # 3. Provider mismatch is rejected
    with pytest.raises(StateValidationException) as exc:
        verify_oauth_state(state=state, expected_provider="outlook_calendar")
    assert "provider mismatch" in str(exc.value).lower()

    # 4. Expired state token is rejected
    expired_state = generate_oauth_state(user_id=user_id, provider="google_calendar", expires_in_seconds=-10)
    with pytest.raises(StateValidationException) as exc:
        verify_oauth_state(state=expired_state, expected_provider="google_calendar")
    assert "expired" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# 2. Missing Credentials Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_google_credentials(test_db):
    """Test system truthfully reports unconfigured status when credentials are missing."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="nocal@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    with patch.object(settings, "GOOGLE_CLIENT_ID", None), patch.object(settings, "GOOGLE_CLIENT_SECRET", None):
        adapter = GoogleCalendarAdapter()
        with pytest.raises(CalendarProviderException) as exc:
            adapter.get_authorization_url(state="test_state")
        assert "not configured" in str(exc.value).lower()

        # Service status reports unconfigured truthfully
        status = await CalendarService.get_status(user_id=user_id, db=test_db)
        assert status.is_connected is False
        assert status.configured is False
        assert "not configured" in status.status_label.lower()


# -----------------------------------------------------------------------------
# 3. Token Encryption and Decryption at Rest
# -----------------------------------------------------------------------------
def test_token_encryption_and_decryption():
    """Verify Fernet encryption produces unique ciphertexts and decrypts accurately."""
    raw_token = "ya29.a0AfH6SMD_very_secret_google_oauth_access_token_12345"

    enc1 = encrypt_token(raw_token)
    enc2 = encrypt_token(raw_token)

    assert enc1 != raw_token
    # Due to random 128-bit IV, identical plaintexts produce different ciphertexts
    assert enc1 != enc2

    dec1 = decrypt_token(enc1)
    dec2 = decrypt_token(enc2)
    assert dec1 == raw_token
    assert dec2 == raw_token

    # Tampered ciphertext fails decryption
    with pytest.raises(CryptoException):
        decrypt_token("gAAAAABl_invalid_ciphertext_tampered_payload_xyz")


# -----------------------------------------------------------------------------
# 4. Expired-Token Auto-Refresh Behavior
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expired_token_auto_refresh(test_db):
    """Verify get_valid_access_token automatically refreshes expired access tokens."""
    mock_provider = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_provider)

    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="refresh_user@mentor.ai", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        encrypted_access_token=encrypt_token("old_expired_access_token"),
        encrypted_refresh_token=encrypt_token("valid_refresh_token_xyz"),
        token_expires_at=now - timedelta(minutes=5),  # Expired
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    token = await CalendarService.get_valid_access_token(conn, test_db)
    assert "mock_refreshed_access_" in token

    # Check connection was updated in database
    refreshed_conn = await test_db.get(ExternalConnection, conn.id)
    assert refreshed_conn.token_expires_at > now
    assert decrypt_token(refreshed_conn.encrypted_access_token) == token


# -----------------------------------------------------------------------------
# 5. Revoked or Invalid Credentials Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revoked_credentials_handling(test_db):
    """Verify that when refresh token is revoked, connection status becomes 'revoked'."""
    mock_provider = MockCalendarAdapter()
    mock_provider.simulate_token_revoked = True
    CalendarService.set_provider_override(mock_provider)

    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="revoked_user@mentor.ai", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        encrypted_access_token=encrypt_token("expired_access_token"),
        encrypted_refresh_token=encrypt_token("revoked_refresh_token"),
        token_expires_at=now - timedelta(minutes=10),
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    with pytest.raises(CalendarAuthRevokedException):
        await CalendarService.get_valid_access_token(conn, test_db)

    refreshed_conn = await test_db.get(ExternalConnection, conn.id)
    assert refreshed_conn.status == "revoked"
    assert refreshed_conn.encrypted_access_token is None


# -----------------------------------------------------------------------------
# 6. User Connection Isolation (Multi-Tenant Boundary)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_user_connection_isolation(test_db):
    """Verify User B cannot access User A's calendar connection or trigger sync."""
    mock_provider = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_provider)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    profile_a = Profile(id=user_a, email="user_a@mentor.ai", timezone="UTC")
    profile_b = Profile(id=user_b, email="user_b@mentor.ai", timezone="UTC")
    test_db.add_all([profile_a, profile_b])

    conn_a = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_a,
        provider="google_calendar",
        provider_account_id="user_a@gmail.com",
        encrypted_access_token=encrypt_token("token_a"),
        status="connected",
    )
    test_db.add(conn_a)
    await test_db.commit()

    # User A status is connected
    status_a = await CalendarService.get_status(user_id=user_a, db=test_db)
    assert status_a.is_connected is True
    assert status_a.account_email == "user_a@gmail.com"

    # User B status is not connected
    status_b = await CalendarService.get_status(user_id=user_b, db=test_db)
    assert status_b.is_connected is False
    assert status_b.account_email is None

    # User B attempting to sync raises error (no connection)
    with pytest.raises(AppException) as exc:
        await CalendarService.sync_events(
            user_id=user_b,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=7),
            db=test_db,
        )
    assert "not connected" in str(exc.value.detail).lower()


# -----------------------------------------------------------------------------
# 7. Calendar Pagination (nextPageToken traversal)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_pagination_handling():
    """Verify adapter continues requesting pages until nextPageToken is null."""
    adapter = GoogleCalendarAdapter()

    page_1_data = {
        "items": [
            {
                "id": "evt_1",
                "summary": "Meeting Page 1",
                "start": {"dateTime": "2026-10-15T10:00:00Z"},
                "end": {"dateTime": "2026-10-15T11:00:00Z"},
            }
        ],
        "nextPageToken": "token_page_2",
    }
    page_2_data = {
        "items": [
            {
                "id": "evt_2",
                "summary": "Meeting Page 2",
                "start": {"dateTime": "2026-10-15T14:00:00Z"},
                "end": {"dateTime": "2026-10-15T15:00:00Z"},
            }
        ],
        "nextPageToken": None,
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    res_1 = httpx.Response(status_code=200, json=page_1_data, request=httpx.Request("GET", "https://google.com"))
    res_2 = httpx.Response(status_code=200, json=page_2_data, request=httpx.Request("GET", "https://google.com"))
    mock_client.request = AsyncMock(side_effect=[res_1, res_2])

    adapter._client = mock_client
    start_dt = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    end_dt = datetime(2026, 10, 15, 23, 59, tzinfo=UTC)

    events = await adapter.list_events(access_token="test_tok", start_time=start_dt, end_time=end_dt)

    assert len(events) == 2
    assert events[0].external_id == "evt_1"
    assert events[1].external_id == "evt_2"
    assert mock_client.request.call_count == 2


# -----------------------------------------------------------------------------
# 8. Duplicate-Event Prevention (Stable External ID Upsert)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_event_prevention(test_db):
    """Verify syncing identical events multiple times does not insert duplicates."""
    mock_provider = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_provider)

    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="dedup@mentor.ai", timezone="UTC")
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        encrypted_access_token=encrypt_token("tok"),
        status="connected",
    )
    test_db.add_all([profile, conn])
    await test_db.commit()

    # Seed event in mock
    now = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    mock_provider.seed_event("Team Standup", start_time=now, end_time=now + timedelta(minutes=30))

    start_window = now - timedelta(hours=1)
    end_window = now + timedelta(hours=5)

    # Sync #1
    res1 = await CalendarService.sync_events(user_id, start_window, end_window, test_db)
    assert res1.synced_count == 1

    # Check database count
    stmt = select(CalendarEvent).where(CalendarEvent.user_id == user_id)
    items1 = (await test_db.execute(stmt)).scalars().all()
    assert len(items1) == 1

    # Sync #2 (repeat identical sync)
    res2 = await CalendarService.sync_events(user_id, start_window, end_window, test_db)
    assert res2.synced_count == 1

    items2 = (await test_db.execute(stmt)).scalars().all()
    # Total count remains exactly 1
    assert len(items2) == 1
    assert items2[0].title == "Team Standup"


# -----------------------------------------------------------------------------
# 9. Event Update and Deletion Synchronization
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_event_update_and_deletion_sync(test_db):
    """Verify modified remote events update in-place and deleted remote events are purged."""
    mock_provider = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_provider)

    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="update_del@mentor.ai", timezone="UTC")
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        encrypted_access_token=encrypt_token("tok"),
        status="connected",
    )
    test_db.add_all([profile, conn])
    await test_db.commit()

    now = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    seeded_event = mock_provider.seed_event("Original Title", start_time=now, end_time=now + timedelta(hours=1))

    # Initial sync
    await CalendarService.sync_events(user_id, now - timedelta(hours=1), now + timedelta(hours=5), test_db)
    ev_in_db = (await test_db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id))).scalar_one()
    assert ev_in_db.title == "Original Title"

    # 1. Update title remotely and sync again
    seeded_event.title = "Updated Title"
    await CalendarService.sync_events(user_id, now - timedelta(hours=1), now + timedelta(hours=5), test_db)
    ev_updated = (await test_db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id))).scalar_one()
    assert ev_updated.title == "Updated Title"
    assert ev_updated.id == ev_in_db.id  # Stable internal ID preserved

    # 2. Delete remotely and sync again
    await mock_provider.delete_event("tok", seeded_event.external_id)
    await CalendarService.sync_events(user_id, now - timedelta(hours=1), now + timedelta(hours=5), test_db)
    ev_deleted = (await test_db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id))).scalar_one_or_none()
    assert ev_deleted is None  # Purged from local DB!


# -----------------------------------------------------------------------------
# 10. Timezone Normalization and All-Day Boundaries
# -----------------------------------------------------------------------------
def test_all_day_and_timezone_normalization():
    """Verify all-day Google events and offset timestamps normalize cleanly to UTC."""
    adapter = GoogleCalendarAdapter()

    # 1. All-day item (date format YYYY-MM-DD)
    all_day_item = {
        "id": "allday_1",
        "summary": "University Holiday",
        "start": {"date": "2026-10-25"},
        "end": {"date": "2026-10-26"},
    }
    norm_allday = adapter._parse_google_event(all_day_item)
    assert norm_allday is not None
    assert norm_allday.is_all_day is True
    assert norm_allday.start_time.tzinfo == UTC
    assert norm_allday.start_time == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert norm_allday.end_time == datetime(2026, 10, 26, 0, 0, tzinfo=UTC)

    # 2. Offset timestamp (-04:00 EDT)
    offset_item = {
        "id": "offset_1",
        "summary": "NYC Lab Session",
        "start": {"dateTime": "2026-10-15T09:00:00-04:00"},
        "end": {"dateTime": "2026-10-15T10:00:00-04:00"},
    }
    norm_offset = adapter._parse_google_event(offset_item)
    assert norm_offset is not None
    assert norm_offset.start_time == datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
    assert norm_offset.end_time == datetime(2026, 10, 15, 14, 0, tzinfo=UTC)


# -----------------------------------------------------------------------------
# 11. Free-Slot Calculation With Fixed Events and Buffers
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_free_slot_and_conflict_calculation(test_db):
    """Test detect_conflicts calculates busy minutes and open slots accurately."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="slots@mentor.ai", timezone="UTC")
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="17:00:00",
    )
    test_db.add_all([profile, prefs])

    target_date = date(2026, 10, 15)

    # 11:00 AM to 12:30 PM meeting (90 mins busy)
    ev = CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Physics Lecture",
        start_time=datetime(2026, 10, 15, 11, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 30, tzinfo=UTC),
        source="google_calendar",
        is_fixed=True,
    )
    test_db.add(ev)
    await test_db.commit()

    res = await CalendarService.detect_conflicts(user_id=user_id, target_date=target_date, db=test_db)

    assert res.has_conflicts is True
    assert res.total_busy_minutes == 90
    assert len(res.conflicting_events) == 1
    assert res.conflicting_events[0]["title"] == "Physics Lecture"

    # Should have two open slots: 09:00 - 11:00 (120m) and 12:30 - 17:00 (270m)
    assert len(res.free_slots) == 2
    assert res.free_slots[0]["duration_minutes"] == 120
    assert res.free_slots[1]["duration_minutes"] == 270


# -----------------------------------------------------------------------------
# 12. Calendar API Failure and Recovery (Rate Limit & Timeout)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_api_rate_limit_and_timeout():
    """Verify provider raises appropriate domain exceptions on rate limit and timeouts."""
    adapter = GoogleCalendarAdapter()

    # Simulate rate limit 429
    mock_client_429 = AsyncMock(spec=httpx.AsyncClient)
    mock_client_429.request = AsyncMock(
        return_value=httpx.Response(status_code=429, request=httpx.Request("GET", "https://google.com"))
    )
    adapter._client = mock_client_429

    with pytest.raises(CalendarRateLimitException):
        await adapter.list_events(
            access_token="tok",
            start_time=datetime(2026, 10, 15, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 10, 15, 23, 59, tzinfo=UTC),
        )

    # Simulate network timeout
    mock_client_timeout = AsyncMock(spec=httpx.AsyncClient)
    mock_client_timeout.request = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
    adapter._client = mock_client_timeout

    with pytest.raises(CalendarTimeoutException):
        await adapter.list_events(
            access_token="tok",
            start_time=datetime(2026, 10, 15, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 10, 15, 23, 59, tzinfo=UTC),
        )


# -----------------------------------------------------------------------------
# 13. MCP Input Validation and Authorization Scoping
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mcp_authorization_and_validation(test_db):
    """Verify MCP tools reject unauthorized user_id access when token context is present."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # 1. Invalid UUID format rejected
    with pytest.raises(AppException) as exc:
        validate_mcp_user_authorization("not-a-valid-uuid")
    assert exc.value.error_code == "INVALID_USER_ID"

    # 2. Token context set to User A, but tool invoked with User B's ID -> FORBIDDEN
    reset_tok = authenticated_mcp_user.set(str(user_a))
    try:
        with pytest.raises(AppException) as exc:
            validate_mcp_user_authorization(str(user_b))
        assert exc.value.error_code == "FORBIDDEN_USER_ACCESS"
        assert exc.value.status_code == 403

        # Matching user_id succeeds
        validated = validate_mcp_user_authorization(str(user_a))
        assert validated == user_a
    finally:
        authenticated_mcp_user.reset(reset_tok)


# -----------------------------------------------------------------------------
# 14. Write-Action Approval Policy Enforcement
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_action_approval_enforcement(test_db):
    """Verify create_calendar_event via MCP stages pending_approval without mutating calendar."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="approval_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    start_iso = "2026-10-15T14:00:00Z"
    end_iso = "2026-10-15T15:00:00Z"

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_ctx():
        yield test_db

    # MCP tool call stages action
    with patch("app.services.mcp.server.get_db_context", side_effect=_test_ctx):
        res = await create_calendar_event(
            user_id=str(user_id),
            title="Project Review",
            start_time=start_iso,
            end_time=end_iso,
        )
    assert res["status"] == "staged_pending_approval"
    assert res["requires_human_approval"] is True
    action_id = uuid.UUID(res["action_id"])

    # Verify no calendar event was created in the database yet
    cal_res = await test_db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id))
    assert len(cal_res.scalars().all()) == 0

    # User explicitly approves the action
    confirm_res = await ActionService.confirm_action(
        db=test_db,
        user_id=user_id,
        action_id=action_id,
        confirmed=True,
    )
    assert confirm_res.status == "completed"
    assert confirm_res.verified is True

    # Now calendar event exists in database
    cal_res2 = await test_db.execute(select(CalendarEvent).where(CalendarEvent.user_id == user_id))
    created_events = cal_res2.scalars().all()
    assert len(created_events) == 1
    assert created_events[0].title == "Project Review"


# -----------------------------------------------------------------------------
# 15. Idempotent Action Execution & Concurrency Safety
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_action_execution(test_db):
    """Verify repeated idempotency_key returns existing action and duplicate confirm is blocked."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="idempotency_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    key = "idem-key-unique-789"
    payload = {"title": "Lab", "start_time": "2026-10-15T10:00:00Z", "end_time": "2026-10-15T11:00:00Z"}

    # Stage 1
    a1 = await ActionService.stage_action(test_db, user_id, "create_calendar_event", payload, idempotency_key=key)

    # Stage 2 (identical key)
    a2 = await ActionService.stage_action(test_db, user_id, "create_calendar_event", payload, idempotency_key=key)

    assert a1.id == a2.id

    # Confirm action
    await ActionService.confirm_action(test_db, user_id, a1.id, confirmed=True)

    # Confirming again raises ACTION_ALREADY_PROCESSED
    with pytest.raises(AppException) as exc:
        await ActionService.confirm_action(test_db, user_id, a1.id, confirmed=True)
    assert exc.value.error_code == "ACTION_ALREADY_PROCESSED"


# -----------------------------------------------------------------------------
# 16. External Outcome Verification Probe
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_external_outcome_verification_probe(test_db):
    """Verify verify_action independently verifies presence of created state."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="verify_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    payload = {"title": "Verified Seminar", "start_time": "2026-10-15T16:00:00Z", "end_time": "2026-10-15T17:00:00Z"}
    action = await ActionService.stage_action(test_db, user_id, "create_calendar_event", payload)

    # Uncompleted action reports not completed
    verify_pending = await ActionService.verify_action(test_db, user_id, action.id)
    assert verify_pending.verified is False

    # Execute and approve
    await ActionService.confirm_action(test_db, user_id, action.id, confirmed=True)

    # Verify completed action reports verified=True
    verify_completed = await ActionService.verify_action(test_db, user_id, action.id)
    assert verify_completed.verified is True
    assert verify_completed.status == "completed"
    assert verify_completed.details["title"] == "Verified Seminar"


# -----------------------------------------------------------------------------
# 17. Deterministic Scheduler Calendar Warnings Integration
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_calendar_connection_warnings(test_db):
    """Verify SchedulerService honestly warns when external calendar is disconnected or stale."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="warn_user@mentor.ai", timezone="UTC")
    prefs = UserPreferences(user_id=user_id, work_start_time="09:00:00", work_end_time="17:00:00")
    test_db.add_all([profile, prefs])
    await test_db.commit()

    # 1. No connection -> Warning present
    p1 = await SchedulerService.generate_proposal(test_db, user_id, date(2026, 10, 15))
    assert any("not connected" in w.lower() for w in p1.validation.warnings)

    # 2. Connected but never synced -> Warning present
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        encrypted_access_token=encrypt_token("tok"),
        status="connected",
        last_synced_at=None,
    )
    test_db.add(conn)
    await test_db.commit()

    p2 = await SchedulerService.generate_proposal(test_db, user_id, date(2026, 10, 15))
    assert any("never been synchronized" in w.lower() for w in p2.validation.warnings)

    # 3. Synced recently -> No disconnected/never-synced warning
    conn.last_synced_at = datetime.now(UTC) - timedelta(minutes=10)
    await test_db.commit()

    p3 = await SchedulerService.generate_proposal(test_db, user_id, date(2026, 10, 15))
    assert not any("not connected" in w.lower() for w in p3.validation.warnings)
    assert not any("never been synchronized" in w.lower() for w in p3.validation.warnings)
