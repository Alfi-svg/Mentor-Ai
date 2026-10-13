"""Unit and integration tests for Calendar Integration (Day 8).

Covers OAuth security, Fernet token encryption at rest, state validation,
multi-tenant isolation, event synchronization, timezone normalization,
scheduling conflict detection, two-phase human approvals, and resilient error handling.
"""

from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import (
    CryptoException,
    StateValidationException,
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    verify_oauth_state,
)
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.services.action_service import ActionService
from app.services.calendar.base import (
    CalendarAuthRevokedException,
)
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.models import CalendarEventCreate
from app.services.calendar.service import CalendarService
from tests.backend.conftest import USER_A_ID


# -----------------------------------------------------------------------------
# 1. Cryptographic Token Encryption & State Parameter Tests
# -----------------------------------------------------------------------------
def test_fernet_token_encryption_and_decryption() -> None:
    """Verify OAuth access and refresh tokens are encrypted at rest with Fernet."""
    raw_token = "ya29.a0AfH6SMB_secret_google_oauth_token_123456789"
    encrypted = encrypt_token(raw_token)

    # Must be encrypted ciphertext, not plaintext
    assert encrypted != raw_token
    assert "ya29" not in encrypted

    # Decrypting returns the original plaintext
    decrypted = decrypt_token(encrypted)
    assert decrypted == raw_token


def test_fernet_tampering_detection() -> None:
    """Verify tampered ciphertexts raise CryptoException."""
    raw_token = "valid_secret_token"
    encrypted = encrypt_token(raw_token)
    tampered = encrypted[:-5] + "AAAAA"

    with pytest.raises(CryptoException):
        decrypt_token(tampered)


def test_oauth_state_generation_and_verification() -> None:
    """Verify cryptographically signed OAuth state validates user ID."""
    state = generate_oauth_state(
        USER_A_ID, provider="google_calendar", expires_in_seconds=300
    )
    assert "." in state

    verified_uid = verify_oauth_state(state, expected_provider="google_calendar")
    assert verified_uid == USER_A_ID


def test_oauth_state_tampering_rejected() -> None:
    """Verify forged or altered state strings raise StateValidationException."""
    state = generate_oauth_state(USER_A_ID, provider="google_calendar")
    payload, sig = state.split(".", 1)
    tampered_sig = sig[:-4] + "ffff"

    with pytest.raises(StateValidationException):
        verify_oauth_state(
            f"{payload}.{tampered_sig}", expected_provider="google_calendar"
        )


def test_oauth_state_expiration_rejected() -> None:
    """Verify expired state tokens are strictly rejected."""
    expired_state = generate_oauth_state(
        USER_A_ID, provider="google_calendar", expires_in_seconds=-10
    )

    with pytest.raises(StateValidationException):
        verify_oauth_state(expired_state, expected_provider="google_calendar")


def test_oauth_state_provider_mismatch_rejected() -> None:
    """Verify state issued for one provider cannot be used for another."""
    state = generate_oauth_state(USER_A_ID, provider="google_calendar")

    with pytest.raises(StateValidationException):
        verify_oauth_state(state, expected_provider="apple_calendar")


# -----------------------------------------------------------------------------
# 2. Calendar Connection Lifecycle & Multi-Tenant Isolation
# -----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def setup_mock_calendar() -> None:
    """Set MockCalendarAdapter as provider for predictable isolated tests."""
    mock_adapter = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_adapter)
    yield
    CalendarService.set_provider_override(None)


def test_calendar_status_unconnected(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify unconnected user reports is_connected=False."""
    res = client.get("/api/v1/calendar/status", headers=user_a_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "google_calendar"
    assert data["is_connected"] is False


def test_calendar_connect_url_generation(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify /api/v1/calendar/connect returns authorization URL with valid state."""
    res = client.get("/api/v1/calendar/connect", headers=user_a_headers)
    assert res.status_code == 200
    data = res.json()
    assert "authorization_url" in data
    assert "state" in data
    assert data["provider"] in ["google_calendar", "mock_google_calendar"]

    # Verify state inside URL
    assert (
        verify_oauth_state(data["state"], expected_provider="mock_google_calendar")
        == USER_A_ID
    )


def test_calendar_oauth_callback_and_connection_activation(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify OAuth callback stores encrypted tokens and activates connection."""
    # 1. Generate valid state for User A
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")

    # 2. Simulate callback from OAuth provider
    cb_res = client.get(
        f"/api/v1/calendar/callback?code=mock_auth_code_99&state={state}"
    )
    assert cb_res.status_code == 200
    cb_data = cb_res.json()
    assert cb_data["status"] == "connected"
    assert cb_data["account_email"] == "student.test@university.edu"

    # 3. Query status endpoint for User A
    status_res = client.get("/api/v1/calendar/status", headers=user_a_headers)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["is_connected"] is True
    assert status_data["status_label"] == "Connected"
    assert status_data["account_email"] == "student.test@university.edu"


def test_calendar_multi_tenant_isolation(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
) -> None:
    """Verify User A's calendar connection and events are completely inaccessible to User B."""
    # 1. Connect User A's calendar
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")
    client.get(f"/api/v1/calendar/callback?code=code_user_a&state={state}")

    # 2. User A status is connected
    res_a = client.get("/api/v1/calendar/status", headers=user_a_headers)
    assert res_a.json()["is_connected"] is True

    # 3. User B status MUST remain unconnected
    res_b = client.get("/api/v1/calendar/status", headers=user_b_headers)
    assert res_b.json()["is_connected"] is False

    # 4. User B cannot disconnect User A's connection
    disc_b = client.post("/api/v1/calendar/disconnect", headers=user_b_headers)
    assert disc_b.status_code == 200

    # User A remains connected
    res_a_check = client.get("/api/v1/calendar/status", headers=user_a_headers)
    assert res_a_check.json()["is_connected"] is True


def test_calendar_disconnect_lifecycle(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify disconnecting calendar revokes access and marks disconnected."""
    # Connect first
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")
    client.get(f"/api/v1/calendar/callback?code=disconnect_test_code&state={state}")

    # Disconnect
    disc_res = client.post("/api/v1/calendar/disconnect", headers=user_a_headers)
    assert disc_res.status_code == 200
    assert disc_res.json()["status"] == "disconnected"

    # Status check confirms disconnected
    status_res = client.get("/api/v1/calendar/status", headers=user_a_headers)
    assert status_res.json()["is_connected"] is False


# -----------------------------------------------------------------------------
# 3. Synchronization, Timezone Normalization & Conflict Detection
# -----------------------------------------------------------------------------
def test_calendar_sync_and_timezone_normalization(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify events from provider are normalized to UTC and saved without duplicates."""
    # 1. Connect User A
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")
    client.get(f"/api/v1/calendar/callback?code=sync_test_code&state={state}")

    # 2. Seed mock provider with events
    mock_adapter = CalendarService.get_provider()
    assert isinstance(mock_adapter, MockCalendarAdapter)

    now = datetime.now(UTC)
    lecture_start = (now + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    lecture_end = lecture_start + timedelta(hours=1, minutes=30)
    mock_adapter.seed_event(
        title="CS 450: Operating Systems Lecture",
        start_time=lecture_start,
        end_time=lecture_end,
        location="Hall 101",
    )

    all_day_start = (now + timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    all_day_end = (now + timedelta(days=3)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    mock_adapter.seed_event(
        title="Midterm Exams Day",
        start_time=all_day_start,
        end_time=all_day_end,
        is_all_day=True,
    )

    # 3. Trigger manual sync
    sync_res = client.post(
        "/api/v1/calendar/sync?days_back=1&days_forward=5", headers=user_a_headers
    )
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["synced_count"] >= 2

    # 4. Query calendar events list
    events_res = client.get(
        "/api/v1/calendar/events",
        params={
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(days=5)).isoformat(),
        },
        headers=user_a_headers,
    )
    assert events_res.status_code == 200
    events = events_res.json()

    os_lecture = next((e for e in events if "Operating Systems" in e["title"]), None)
    assert os_lecture is not None
    assert os_lecture["source"] == "google_calendar"
    assert os_lecture["is_fixed"] is True
    assert os_lecture["location"] == "Hall 101"

    midterms = next((e for e in events if "Midterm Exams" in e["title"]), None)
    assert midterms is not None
    assert midterms["is_all_day"] is True

    # 5. Re-running sync MUST NOT duplicate events (idempotent upsert)
    sync_res_again = client.post(
        "/api/v1/calendar/sync?days_back=1&days_forward=5", headers=user_a_headers
    )
    assert sync_res_again.status_code == 200
    events_res_again = client.get(
        "/api/v1/calendar/events",
        params={
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(days=5)).isoformat(),
        },
        headers=user_a_headers,
    )
    matching_lectures = [
        e for e in events_res_again.json() if "Operating Systems" in e["title"]
    ]
    assert len(matching_lectures) == 1, "Duplicate event created on re-sync"


def test_detect_scheduling_conflicts(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify /api/v1/calendar/conflicts accurately computes busy intervals and free slots."""
    # Connect and seed
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")
    client.get(f"/api/v1/calendar/callback?code=conflicts_code&state={state}")

    mock_adapter = CalendarService.get_provider()
    assert isinstance(mock_adapter, MockCalendarAdapter)

    target_d = (datetime.now(UTC) + timedelta(days=3)).date()
    meeting_start = datetime.combine(
        target_d, datetime.strptime("10:00:00", "%H:%M:%S").time(), tzinfo=UTC
    )
    meeting_end = datetime.combine(
        target_d, datetime.strptime("11:30:00", "%H:%M:%S").time(), tzinfo=UTC
    )

    mock_adapter.seed_event(
        title="Project Sync Meeting",
        start_time=meeting_start,
        end_time=meeting_end,
    )
    client.post(
        "/api/v1/calendar/sync?days_back=0&days_forward=5", headers=user_a_headers
    )

    # Check conflicts for target date
    res = client.get(
        f"/api/v1/calendar/conflicts?target_date={target_d.isoformat()}",
        headers=user_a_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["target_date"] == target_d.isoformat()
    assert data["has_conflicts"] is True
    assert data["total_busy_minutes"] == 90
    assert any(c["title"] == "Project Sync Meeting" for c in data["conflicting_events"])
    assert len(data["free_slots"]) > 0


# -----------------------------------------------------------------------------
# 4. Two-Phase Action Approval with External Push & Read Verification
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_action_approval_pushes_to_calendar_with_read_verification(
    client: TestClient, user_a_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Verify staged calendar event creates remote event upon approval and verifies outcome."""
    # 1. Connect calendar for User A
    state = generate_oauth_state(USER_A_ID, provider="mock_google_calendar")
    client.get(f"/api/v1/calendar/callback?code=verify_test_code&state={state}")

    now = datetime.now(UTC)
    event_start = (now + timedelta(days=2, hours=1)).isoformat()
    event_end = (now + timedelta(days=2, hours=2)).isoformat()

    # 2. Stage action
    staged = await ActionService.stage_action(
        db=db_session,
        user_id=USER_A_ID,
        action_type="create_calendar_event",
        payload={
            "title": "Advising Session with Professor",
            "start_time": event_start,
            "end_time": event_end,
            "location": "Faculty Office 204",
        },
    )
    assert staged.status == "pending_approval"
    action_id = staged.id

    # 3. Before user approval: event MUST NOT be on the external provider
    mock_adapter = CalendarService.get_provider()
    assert isinstance(mock_adapter, MockCalendarAdapter)
    assert not any(
        e.title == "Advising Session with Professor"
        for e in mock_adapter._events.values()
    )

    # 4. User approves action
    confirm_res = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": True},
        headers=user_a_headers,
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["status"] == "completed"
    assert confirm_data["verified"] is True

    # 5. Remote calendar provider now has the event
    assert any(
        e.title == "Advising Session with Professor"
        for e in mock_adapter._events.values()
    )

    # 6. Database record contains external_id and source="google_calendar"
    ev_stmt = select(CalendarEvent).where(
        CalendarEvent.user_id == USER_A_ID,
        CalendarEvent.title == "Advising Session with Professor",
    )
    ev_res = await db_session.execute(ev_stmt)
    persisted = ev_res.scalar_one_or_none()
    assert persisted is not None
    assert persisted.external_id is not None
    assert persisted.source == "google_calendar"


@pytest.mark.asyncio
async def test_action_execution_fails_truthfully_if_read_verification_fails(
    db_session: AsyncSession,
) -> None:
    """Verify that if post-condition read verification fails, action is not marked completed."""
    mock_adapter = CalendarService.get_provider()
    assert isinstance(mock_adapter, MockCalendarAdapter)
    mock_adapter.simulate_read_verification_failure = True

    event_payload = CalendarEventCreate(
        title="Failed Event",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(hours=1),
    )

    with pytest.raises(Exception):
        await CalendarService.create_calendar_event(
            user_id=USER_A_ID,
            event_data=event_payload,
            db=db_session,
        )


# -----------------------------------------------------------------------------
# 5. Token Refresh & Edge Case Error Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_automatic_token_refresh_when_expired(db_session: AsyncSession) -> None:
    """Verify get_valid_access_token automatically refreshes an expired access token."""
    await db_session.execute(
        delete(ExternalConnection).where(ExternalConnection.user_id == USER_A_ID)
    )
    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=USER_A_ID,
        provider="google_calendar",
        provider_account_id="student@test.edu",
        encrypted_access_token=encrypt_token("old_expired_token"),
        encrypted_refresh_token=encrypt_token("valid_refresh_token"),
        token_expires_at=now - timedelta(minutes=5),  # expired 5 min ago
        status="connected",
        created_at=now,
        updated_at=now,
    )
    db_session.add(conn)
    await db_session.commit()

    valid_token = await CalendarService.get_valid_access_token(conn, db_session)
    assert valid_token != "old_expired_token"
    assert "mock_refreshed_access" in valid_token
    assert conn.token_expires_at > now


@pytest.mark.asyncio
async def test_revoked_token_transitions_connection_to_revoked(
    db_session: AsyncSession,
) -> None:
    """Verify revoked refresh token marks connection status as revoked."""
    await db_session.execute(
        delete(ExternalConnection).where(ExternalConnection.user_id == USER_A_ID)
    )
    mock_adapter = CalendarService.get_provider()
    assert isinstance(mock_adapter, MockCalendarAdapter)
    mock_adapter.simulate_token_revoked = True

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=USER_A_ID,
        provider="google_calendar",
        provider_account_id="student@test.edu",
        encrypted_access_token=encrypt_token("expired_token"),
        encrypted_refresh_token=encrypt_token("revoked_refresh_token"),
        token_expires_at=now - timedelta(minutes=5),
        status="connected",
        created_at=now,
        updated_at=now,
    )
    db_session.add(conn)
    await db_session.commit()

    with pytest.raises(CalendarAuthRevokedException):
        await CalendarService.get_valid_access_token(conn, db_session)

    assert conn.status == "revoked"
