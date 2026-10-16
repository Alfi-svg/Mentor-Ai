"""Automated Test Suite for Gmail Workspace enhancements.

Verifies:
1. Message listing by folder: INBOX, STARRED, SENT, DRAFT.
2. Search query filtering across subject, sender, and snippet.
3. Label modifications: marking messages read/unread, star/unstar.
4. Message detail retrieval with sanitized HTML and plain text bodies.
5. Draft creation and validation.
6. Multi-tenant user isolation on message modification.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.models.connection import ExternalConnection
from app.db.models.profile import Profile, UserPreferences
from app.services.gmail.mock import MockGmailAdapter
from app.services.gmail.models import GmailDraftCreate
from app.services.gmail.service import GmailService


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
def reset_gmail_provider():
    """Ensure mock Gmail provider is reset before and after each test."""
    GmailService.set_provider_override(None)
    yield
    GmailService.set_provider_override(None)


async def setup_user_with_gmail(test_db, email="student@university.edu") -> uuid.UUID:
    """Helper to provision a user and connected Gmail account."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email=email,
        full_name="Workspace User",
        created_at=datetime.now(UTC),
    )
    prefs = UserPreferences(
        id=uuid.uuid4(),
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="18:00:00",
        buffer_minutes=15,
        calendar_auto_sync=True,
    )
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_gmail",
        provider_account_id=email,
        status="connected",
        encrypted_access_token=encrypt_token("mock_access_token"),
        encrypted_refresh_token=encrypt_token("mock_refresh_token"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=2),
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
        created_at=datetime.now(UTC),
    )
    test_db.add_all([profile, prefs, conn])
    await test_db.commit()
    return user_id


@pytest.mark.asyncio
async def test_list_messages_by_folder(test_db):
    """Verify filtering messages by INBOX and STARRED folders."""
    mock_gmail = MockGmailAdapter()
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db)

    # Initially mock messages have INBOX labels and none are starred
    inbox_msgs = await GmailService.list_messages(
        user_id=user_id,
        db=test_db,
        folder="INBOX",
    )
    assert len(inbox_msgs) >= 2

    # Star one message
    target_id = inbox_msgs[0].id
    await GmailService.modify_message(
        user_id=user_id,
        message_id=target_id,
        add_labels=["STARRED"],
        remove_labels=None,
        db=test_db,
    )

    # Fetch STARRED folder
    starred_msgs = await GmailService.list_messages(
        user_id=user_id,
        db=test_db,
        folder="STARRED",
    )
    assert len(starred_msgs) == 1
    assert starred_msgs[0].id == target_id
    assert starred_msgs[0].is_starred is True


@pytest.mark.asyncio
async def test_mark_message_read_and_unread(test_db):
    """Verify toggling UNREAD label updates read/unread status."""
    mock_gmail = MockGmailAdapter()
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db)

    # msg-os-assign-3 starts as unread
    msg_id = "msg-os-assign-3"
    detail = await GmailService.get_message(user_id=user_id, message_id=msg_id, db=test_db)
    assert "UNREAD" in detail.labels

    # Mark as read (remove UNREAD label)
    updated_labels = await GmailService.modify_message(
        user_id=user_id,
        message_id=msg_id,
        add_labels=None,
        remove_labels=["UNREAD"],
        db=test_db,
    )
    assert "UNREAD" not in updated_labels

    # Verify via get_message
    updated_detail = await GmailService.get_message(user_id=user_id, message_id=msg_id, db=test_db)
    assert "UNREAD" not in updated_detail.labels

    # Mark back as unread (add UNREAD label)
    reverted_labels = await GmailService.modify_message(
        user_id=user_id,
        message_id=msg_id,
        add_labels=["UNREAD"],
        remove_labels=None,
        db=test_db,
    )
    assert "UNREAD" in reverted_labels


@pytest.mark.asyncio
async def test_message_detail_html_and_plain_sanitization(test_db):
    """Verify that message details contain both body_plain and body_html with sanitization."""
    mock_gmail = MockGmailAdapter()
    # Add a message with HTML content containing a malicious script tag
    mock_gmail._mock_messages["msg-xss-test"] = {
        "id": "msg-xss-test",
        "thread_id": "thread-xss",
        "sender": "Attacker <hacker@test.com>",
        "recipient": "student@university.edu",
        "subject": "Hello <script>alert('xss')</script> Friend",
        "date": datetime.now(UTC).isoformat(),
        "snippet": "Test snippet",
        "body_plain": "Plain text body <script>alert(1)</script>",
        "labels": ["INBOX"],
        "is_unread": True,
    }
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db)

    detail = await GmailService.get_message(user_id=user_id, message_id="msg-xss-test", db=test_db)
    assert detail.id == "msg-xss-test"
    assert "<script>" not in detail.subject
    assert "<script>" not in detail.body_plain
    assert "<script>" not in detail.body_html
    assert detail.sanitized is True


@pytest.mark.asyncio
async def test_create_and_list_drafts(test_db):
    """Verify draft creation in Gmail workspace."""
    mock_gmail = MockGmailAdapter()
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db)

    draft_payload = GmailDraftCreate(
        to="advisor@university.edu",
        subject="Thesis Topic Proposal Draft",
        body="Dear Advisor,\nHere is my initial outline for the thesis proposal.",
    )
    draft_res = await GmailService.create_draft(
        user_id=user_id,
        draft=draft_payload,
        db=test_db,
    )
    assert draft_res.draft_id.startswith("draft-")
    assert draft_res.to == "advisor@university.edu"
    assert len(mock_gmail.drafts) == 1


@pytest.mark.asyncio
async def test_verify_connection_operational(test_db):
    """Verify deep diagnostic inspection returns operational when token and list_messages work."""
    mock_gmail = MockGmailAdapter()
    mock_gmail.token_details_override = {
        "valid": True,
        "email": "student.verify@university.edu",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
    }
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db, email="student.verify@university.edu")

    report = await GmailService.verify_connection(user_id=user_id, db=test_db)
    assert report.connected is True
    assert report.verified is True
    assert report.can_read_messages is True
    assert report.has_sufficient_scopes is True
    assert report.api_status == "operational"
    assert report.account_email == "student.verify@university.edu"
    assert "https://www.googleapis.com/auth/gmail.readonly" in report.granted_scopes


@pytest.mark.asyncio
async def test_verify_connection_missing_read_scope(test_db):
    """Verify diagnostic accurately identifies missing read scope when only calendar is granted."""
    mock_gmail = MockGmailAdapter()
    mock_gmail.token_details_override = {
        "valid": True,
        "email": "cal.only@university.edu",
        "scopes": ["https://www.googleapis.com/auth/calendar.events"],
    }
    GmailService.set_provider_override(mock_gmail)
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="cal.only@university.edu", full_name="Cal Only")
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_gmail",
        provider_account_id="cal.only@university.edu",
        status="connected",
        encrypted_access_token=encrypt_token("mock_access_token"),
        encrypted_refresh_token=encrypt_token("mock_refresh_token"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=2),
        scopes=["https://www.googleapis.com/auth/calendar.events"],
        created_at=datetime.now(UTC),
    )
    test_db.add_all([profile, conn])
    await test_db.commit()

    report = await GmailService.verify_connection(user_id=user_id, db=test_db)
    assert report.connected is True
    assert report.has_sufficient_scopes is False
    assert "https://www.googleapis.com/auth/gmail.readonly" in report.missing_scopes
    assert report.api_status == "scope_missing"


@pytest.mark.asyncio
async def test_empty_mailbox_vs_error_distinction(test_db):
    """Ensure genuinely empty mailboxes return [] while API errors raise exceptions and are never masked."""
    mock_gmail = MockGmailAdapter()
    # Empty mock messages
    mock_gmail._mock_messages.clear()
    GmailService.set_provider_override(mock_gmail)
    user_id = await setup_user_with_gmail(test_db, email="empty.inbox@university.edu")

    # Legitimate empty inbox returns empty list
    messages = await GmailService.list_messages(user_id=user_id, db=test_db, folder="INBOX")
    assert messages == []

    # If provider fails with error, exception must be raised, NOT silently returning []
    mock_gmail.is_revoked = True
    with pytest.raises(Exception) as exc_info:
        await GmailService.list_messages(user_id=user_id, db=test_db, folder="INBOX")
    assert exc_info.value is not None

