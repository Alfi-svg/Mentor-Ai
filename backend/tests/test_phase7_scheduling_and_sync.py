"""Automated Unit and Integration Tests for Mentor AI Phase 7:
Intelligent Scheduling, Multi-Day Forward Search, Conflict Detection,
Automatic Calendar Sync, and Security Hardening.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.notification import Notification
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import ScheduleBlock
from app.db.models.task import Task
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.services.calendar.base import CalendarProviderException
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.service import CalendarService
from app.services.calendar_sync_service import CalendarSyncService
from app.services.notification_service import NotificationService
from app.services.task_service import TaskService


def _norm_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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
def setup_mock_calendar():
    """Ensure mock calendar provider is active during tests."""
    mock_adapter = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_adapter)
    yield mock_adapter
    CalendarService.set_provider_override(None)


async def setup_test_user(db, email="phase7_user@test.com", timezone="Asia/Dhaka") -> uuid.UUID:
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email=email,
        full_name="Phase 7 Test User",
        timezone=timezone,
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
    db.add(profile)
    db.add(prefs)
    await db.commit()
    return user_id


async def setup_google_calendar_connection(db, user_id: uuid.UUID, status: str = "connected"):
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        provider_account_id="gcal_account_phase7",
        encrypted_access_token="encrypted_test_token",
        encrypted_refresh_token="encrypted_test_refresh",
        token_expires_at=datetime.now(UTC) + timedelta(hours=2),
        scopes=["https://www.googleapis.com/auth/calendar.events"],
        status=status,
        metadata_json={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(conn)
    await db.commit()
    return conn


@pytest.mark.asyncio
async def test_case_a_user_supplies_start_time_creates_schedule_and_syncs(test_db):
    """Case A: User supplies start time. ScheduleBlock and Google Calendar event are created."""
    user_id = await setup_test_user(test_db, email="case_a@test.com")
    await setup_google_calendar_connection(test_db, user_id)

    now = datetime.now(UTC)
    start_time = now + timedelta(hours=2)
    end_time = start_time + timedelta(minutes=60)

    with patch("app.services.calendar.service.CalendarService.get_valid_access_token", new_callable=AsyncMock) as mock_tok:
        mock_tok.return_value = "mock_access_token"
        task = await TaskService.create_task(
            db=test_db,
            user_id=user_id,
            payload=TaskCreateRequest(
                title="Prepare Phase 7 Lecture",
                duration_minutes=60,
                scheduled_start=start_time,
                scheduled_end=end_time,
                scheduling_preference="manual",
            ),
        )

    assert _norm_dt(task.scheduled_start) == _norm_dt(start_time)
    assert _norm_dt(task.scheduled_end) == _norm_dt(end_time)
    assert task.calendar_sync_status == "synced"
    assert task.google_calendar_event_id is not None

    # Verify ScheduleBlock was created
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is not None
    assert _norm_dt(block.start_time) == _norm_dt(start_time)
    assert _norm_dt(block.end_time) == _norm_dt(end_time)


@pytest.mark.asyncio
async def test_case_a_conflict_detection_alerts_user_with_schedule_conflict_notification(test_db):
    """Case A: When user manually places a task over an existing calendar commitment, a schedule_conflict alert is created."""
    user_id = await setup_test_user(test_db, email="conflict_user@test.com")
    now = datetime.now(UTC)

    # Existing fixed event
    fixed_ev = CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Final Exam",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=3),
        source="internal",
        is_fixed=True,
    )
    test_db.add(fixed_ev)
    await test_db.commit()

    # User manually schedules a task overlapping with Final Exam
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Read Chapter 4",
            duration_minutes=45,
            scheduled_start=now + timedelta(hours=2),
            scheduling_preference="manual",
        ),
    )

    assert task.scheduled_start is not None

    # Check that a schedule_conflict notification was scheduled
    notif = await test_db.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.notification_type == "schedule_conflict",
            Notification.task_id == task.id,
        )
    )
    assert notif is not None
    assert "Final Exam" in notif.message


@pytest.mark.asyncio
async def test_case_b_deadline_only_task_strictly_remains_unscheduled(test_db):
    """Case B: User supplies only a deadline. Deadline must NEVER be treated as start time."""
    user_id = await setup_test_user(test_db, email="deadline_only@test.com")
    deadline = datetime.now(UTC) + timedelta(days=2)

    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Essay Draft Due",
            deadline=deadline,
            duration_minutes=90,
            scheduling_preference="unscheduled",
        ),
    )

    assert _norm_dt(task.deadline) == _norm_dt(deadline)
    assert task.scheduled_start is None
    assert task.scheduled_end is None
    assert task.calendar_sync_status == "unscheduled"

    # Must NOT have a ScheduleBlock
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is None


@pytest.mark.asyncio
async def test_case_c_multi_day_auto_schedule_finds_forward_slot(test_db):
    """Case C: User asks Mentor AI to auto-schedule. Multi-day forward solver finds earliest non-conflicting slot."""
    user_id = await setup_test_user(test_db, email="auto_multi_day@test.com", timezone="UTC")
    await setup_google_calendar_connection(test_db, user_id)

    # Task with deadline 3 days in the future
    deadline = datetime.now(UTC) + timedelta(days=3)
    with patch("app.services.calendar.service.CalendarService.get_valid_access_token", new_callable=AsyncMock) as mock_tok:
        mock_tok.return_value = "mock_access_token"
        task = await TaskService.create_task(
            db=test_db,
            user_id=user_id,
            payload=TaskCreateRequest(
                title="Write Thesis Abstract",
                duration_minutes=45,
                priority="P1",
                deadline=deadline,
                scheduling_preference="auto",
            ),
        )

    assert task.scheduled_start is not None
    assert task.scheduled_end is not None
    assert _norm_dt(task.scheduled_end) <= _norm_dt(deadline)
    assert task.calendar_sync_status == "synced"


@pytest.mark.asyncio
async def test_case_d_expired_deadline_preserved_truthfully_as_unscheduled(test_db):
    """Case D: If deadline has already passed, auto-schedule preserves task as unscheduled and explains why."""
    user_id = await setup_test_user(test_db, email="past_dl@test.com")
    past_deadline = datetime.now(UTC) - timedelta(hours=2)

    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Past Due Assignment",
            deadline=past_deadline,
            duration_minutes=60,
            scheduling_preference="auto",
        ),
    )

    assert task.scheduled_start is None
    assert task.scheduled_end is None
    assert task.calendar_sync_status == "unscheduled"


@pytest.mark.asyncio
async def test_sync_lifecycle_reauthorization_required_on_403(test_db):
    """Sync Lifecycle: When Google Calendar returns 403 insufficient scopes, status becomes reauthorization_required."""
    user_id = await setup_test_user(test_db, email="reauth_test@test.com")
    conn = await setup_google_calendar_connection(test_db, user_id)

    now = datetime.now(UTC)
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Sync Test Task",
        duration_minutes=60,
        scheduled_start=now + timedelta(hours=1),
        scheduled_end=now + timedelta(hours=2),
        calendar_sync_status="pending",
        created_at=now,
        updated_at=now,
    )
    test_db.add(task)
    await test_db.commit()

    with patch("app.services.calendar.service.CalendarService.get_valid_access_token", new_callable=AsyncMock) as mock_tok, \
         patch("app.services.calendar.service.CalendarService.get_provider") as mock_prov_fn:
        mock_tok.return_value = "mock_token"
        mock_prov = AsyncMock()
        mock_prov.create_event.side_effect = CalendarProviderException(
            detail="Request had insufficient authentication scopes", status_code=403
        )
        mock_prov_fn.return_value = mock_prov

        success = await CalendarSyncService.sync_task_to_calendar(test_db, task, user_id)
        assert success is False

    await test_db.refresh(task)
    assert task.calendar_sync_status == "reauthorization_required"
    assert "Google Calendar permission missing" in task.calendar_sync_error
    assert conn.metadata_json.get("scope_insufficient") is True


@pytest.mark.asyncio
async def test_background_sync_pending_tasks_worker(test_db):
    """Background Worker: sync_pending_and_failed_tasks finds pending tasks and synchronizes them."""
    user_id = await setup_test_user(test_db, email="bg_sync@test.com")
    await setup_google_calendar_connection(test_db, user_id)

    now = datetime.now(UTC)
    pending_task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Offline Created Task",
        duration_minutes=45,
        scheduled_start=now + timedelta(hours=3),
        scheduled_end=now + timedelta(hours=4),
        calendar_sync_status="pending",
        created_at=now,
        updated_at=now,
    )
    test_db.add(pending_task)
    await test_db.commit()

    with patch("app.services.calendar.service.CalendarService.get_valid_access_token", new_callable=AsyncMock) as mock_tok:
        mock_tok.return_value = "mock_token"
        synced_count = await CalendarSyncService.sync_pending_and_failed_tasks(test_db, limit=10)

    assert synced_count >= 1
    await test_db.refresh(pending_task)
    assert pending_task.calendar_sync_status == "synced"
    assert pending_task.google_calendar_event_id is not None


@pytest.mark.asyncio
async def test_dispatch_secret_verification_security_hardening():
    """Security Hardening: verify_dispatch_secret requires configured token and rejects empty/unconfigured tokens."""
    # When NOTIFICATION_DISPATCH_SECRET is empty string (default)
    with patch.object(settings, "NOTIFICATION_DISPATCH_SECRET", ""):
        assert NotificationService.verify_dispatch_secret("mentor-ai-dispatch-sec-2026-v1") is False
        assert NotificationService.verify_dispatch_secret("") is False
        assert NotificationService.verify_dispatch_secret(None) is False

    # When configured with a valid secret
    with patch.object(settings, "NOTIFICATION_DISPATCH_SECRET", "rotated-prod-secret-987"):
        assert NotificationService.verify_dispatch_secret("rotated-prod-secret-987") is True
        assert NotificationService.verify_dispatch_secret("wrong-token") is False
        assert NotificationService.verify_dispatch_secret("") is False
        assert NotificationService.verify_dispatch_secret(None) is False
