import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.crypto import encrypt_token
from app.core.errors import AppException
from app.db.base import Base
from app.db.models.connection import ExternalConnection
from app.db.models.profile import Profile
from app.services.calendar.base import CalendarProviderException
from app.services.calendar.models import CalendarEventCreate
from app.services.calendar.service import CalendarService, check_calendar_scopes
from app.services.gmail.base import GmailProviderException
from app.services.gmail.google import _safe_b64decode
from app.services.gmail.service import GmailService, check_gmail_scopes


@pytest.fixture
async def test_db():
    """Create in-memory async SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_calendar_scopes_detection():
    # Insufficient: empty or only identity scopes
    valid, missing = check_calendar_scopes([])
    assert valid is False
    assert "https://www.googleapis.com/auth/calendar.events" in missing

    valid, missing = check_calendar_scopes(["openid", "https://www.googleapis.com/auth/userinfo.email"])
    assert valid is False
    assert "https://www.googleapis.com/auth/calendar.events" in missing

    # Sufficient with calendar.events
    valid, missing = check_calendar_scopes([
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/calendar.events",
    ])
    assert valid is True
    assert len(missing) == 0

    # Sufficient with full calendar scope
    valid, missing = check_calendar_scopes([
        "openid",
        "https://www.googleapis.com/auth/calendar",
    ])
    assert valid is True
    assert len(missing) == 0


def test_gmail_scopes_detection():
    # Insufficient: empty or only email
    valid, missing = check_gmail_scopes([])
    assert valid is False
    assert "https://www.googleapis.com/auth/gmail.readonly" in missing

    # Missing read scope (e.g. only email profile)
    valid, missing = check_gmail_scopes(["https://www.googleapis.com/auth/userinfo.email"])
    assert valid is False
    assert "https://www.googleapis.com/auth/gmail.readonly" in missing

    # Sufficient with readonly scope
    valid, missing = check_gmail_scopes(["https://www.googleapis.com/auth/gmail.readonly"])
    assert valid is True
    assert len(missing) == 0

    # Sufficient with readonly and modify
    valid, missing = check_gmail_scopes([
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/userinfo.email",
    ])
    assert valid is True
    assert len(missing) == 0

    # Sufficient with full mail.google.com
    valid, missing = check_gmail_scopes(["https://mail.google.com/"])
    assert valid is True
    assert len(missing) == 0


def test_safe_b64decode_padding():
    # 0 padding bytes needed (len % 4 == 0)
    assert _safe_b64decode("SGVsbG8gV29ybGQ=") == "Hello World"
    # missing padding
    assert _safe_b64decode("SGVsbG8gV29ybGQ") == "Hello World"
    # arbitrary string
    assert _safe_b64decode("TWVudG9yIEFJ") == "Mentor AI"
    # empty or invalid
    assert _safe_b64decode("") == ""


@pytest.mark.asyncio
async def test_calendar_get_status_insufficient_scopes(test_db: AsyncSession):
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="cal.insufficient@test.edu", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        provider_account_id="cal.insufficient@test.edu",
        encrypted_access_token=encrypt_token("access-tok"),
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    with patch.object(settings, "GOOGLE_CLIENT_ID", "mock-client-id"), patch.object(settings, "GOOGLE_CLIENT_SECRET", "mock-secret"):
        status = await CalendarService.get_status(user_id=user_id, db=test_db)
        assert status.is_connected is True
        assert status.has_sufficient_scopes is False
        assert status.status_label == "insufficient_scopes"
        assert "https://www.googleapis.com/auth/calendar.events" in status.missing_scopes


@pytest.mark.asyncio
async def test_gmail_get_status_insufficient_scopes(test_db: AsyncSession):
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="gmail.insufficient@test.edu", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_gmail",
        provider_account_id="gmail.insufficient@test.edu",
        encrypted_access_token=encrypt_token("access-tok"),
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    with patch.object(settings, "GOOGLE_GMAIL_CLIENT_ID", "mock-gmail-id"), patch.object(settings, "GOOGLE_GMAIL_CLIENT_SECRET", "mock-gmail-secret"):
        status = await GmailService.get_status(user_id=user_id, db=test_db)
        assert status.is_connected is True
        assert status.has_sufficient_scopes is False
        assert status.status_label == "insufficient_scopes"
        assert "https://www.googleapis.com/auth/gmail.readonly" in status.missing_scopes


@pytest.mark.asyncio
async def test_create_calendar_event_scope_insufficient_interception(test_db: AsyncSession):
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="cal.scope403@test.edu", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        provider_account_id="cal.scope403@test.edu",
        encrypted_access_token=encrypt_token("access-tok"),
        scopes=["https://www.googleapis.com/auth/calendar.events"],
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    mock_provider = AsyncMock()
    mock_provider.create_event.side_effect = CalendarProviderException(
        "Google Calendar create failed (403): Request had insufficient authentication scopes ACCESS_TOKEN_SCOPE_INSUFFICIENT",
        status_code=403,
    )

    with patch.object(settings, "GOOGLE_CLIENT_ID", "mock-client-id"), patch.object(settings, "GOOGLE_CLIENT_SECRET", "mock-secret"):
        with patch.object(CalendarService, "get_provider", return_value=mock_provider):
            with pytest.raises(AppException) as exc_info:
                await CalendarService.create_calendar_event(
                    user_id=user_id,
                    event_data=CalendarEventCreate(
                        title="Math Lecture",
                        start_time=now,
                        end_time=now,
                    ),
                    db=test_db,
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.error_code == "CALENDAR_SCOPE_INSUFFICIENT"

        # Verify that conn status was updated in DB
        await test_db.refresh(conn)
        assert conn.metadata_json.get("scope_insufficient") is True

        # Now verify get_status reports insufficient_scopes
        status = await CalendarService.get_status(user_id=user_id, db=test_db)
        assert status.has_sufficient_scopes is False
        assert status.status_label == "insufficient_scopes"


@pytest.mark.asyncio
async def test_gmail_list_messages_scope_insufficient_interception(test_db: AsyncSession):
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="gmail.scope403@test.edu", timezone="UTC")
    test_db.add(profile)

    now = datetime.now(UTC)
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_gmail",
        provider_account_id="gmail.scope403@test.edu",
        encrypted_access_token=encrypt_token("access-tok"),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        status="connected",
        created_at=now,
        updated_at=now,
    )
    test_db.add(conn)
    await test_db.commit()

    mock_provider = AsyncMock()
    mock_provider.list_messages.side_effect = GmailProviderException(
        "Forbidden: Missing required Gmail scope.",
        status_code=403,
    )

    with patch.object(GmailService, "get_provider", return_value=mock_provider):
        with pytest.raises(AppException) as exc_info:
            await GmailService.list_messages(user_id=user_id, db=test_db)
        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "GMAIL_SCOPE_INSUFFICIENT"

    # Verify that conn was updated
    await test_db.refresh(conn)
    assert conn.metadata_json.get("scope_insufficient") is True

    # Status reflects insufficient scopes
    status = await GmailService.get_status(user_id=user_id, db=test_db)
    assert status.has_sufficient_scopes is False
    assert status.status_label == "insufficient_scopes"
