"""Automated tests for automatic Task-to-Calendar synchronization and bidirectional reconciliation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.models import CalendarEventUpdate
from app.services.calendar.service import CalendarService
from app.services.calendar_sync_service import CalendarSyncService
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
def reset_calendar_override():
    """Reset provider overrides."""
    CalendarService.set_provider_override(None)
    yield
    CalendarService.set_provider_override(None)


async def setup_user_with_calendar(test_db, sync_enabled: bool = True):
    """Helper to seed a test user, profile, preferences, and active Google Calendar connection."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email=f"user_{user_id.hex[:6]}@example.com",
        full_name="Sync Test User",
        timezone="UTC",
    )
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="18:00:00",
        buffer_minutes=15,
        default_task_duration=45,
        calendar_auto_sync=sync_enabled,
    )
    conn = ExternalConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="google_calendar",
        provider_account_id="sync_tester@gmail.com",
        encrypted_access_token=encrypt_token("mock_access_token"),
        encrypted_refresh_token=encrypt_token("mock_refresh_token"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        status="connected",
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    test_db.add(profile)
    test_db.add(prefs)
    test_db.add(conn)
    await test_db.commit()
    return user_id


@pytest.mark.asyncio
async def test_auto_sync_creates_event_on_scheduled_task_creation(test_db):
    """Verify that creating a task with scheduled_start/end creates a calendar event."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    start_time = now + timedelta(hours=2)
    end_time = start_time + timedelta(minutes=60)

    task_payload = TaskCreateRequest(
        title="Prepare Operating Systems Presentation",
        duration_minutes=60,
        priority="P1",
        scheduled_start=start_time,
        scheduled_end=end_time,
    )

    task = await TaskService.create_task(db=test_db, user_id=user_id, payload=task_payload)

    assert task.calendar_sync_status == "synced"
    assert task.google_calendar_event_id is not None
    assert task.last_synced_at is not None

    # Check that event was registered in mock calendar
    assert task.google_calendar_event_id in mock_cal._events
    remote_evt = mock_cal._events[task.google_calendar_event_id]
    assert remote_evt.title == "Prepare Operating Systems Presentation"

    # Check local CalendarEvent cache
    local_ev = await test_db.scalar(
        select(CalendarEvent).where(CalendarEvent.external_id == task.google_calendar_event_id)
    )
    assert local_ev is not None
    assert local_ev.source == "google_calendar"


@pytest.mark.asyncio
async def test_rescheduling_task_updates_calendar_event(test_db):
    """Verify updating a task's scheduled time updates the external Google Calendar event."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    start_time = now + timedelta(hours=1)
    end_time = start_time + timedelta(minutes=45)

    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Database Lab Exercise",
            duration_minutes=45,
            scheduled_start=start_time,
            scheduled_end=end_time,
        ),
    )
    event_id = task.google_calendar_event_id
    assert event_id is not None

    # Reschedule by 3 hours
    new_start = start_time + timedelta(hours=3)
    new_end = end_time + timedelta(hours=3)
    updated_task = await TaskService.update_task(
        db=test_db,
        user_id=user_id,
        task_id=task.id,
        payload=TaskUpdateRequest(scheduled_start=new_start, scheduled_end=new_end),
    )

    assert updated_task.google_calendar_event_id == event_id
    assert updated_task.calendar_sync_status == "synced"

    remote_evt = mock_cal._events[event_id]
    assert remote_evt.start_time == new_start


@pytest.mark.asyncio
async def test_completing_task_updates_calendar_event_title(test_db):
    """Verify marking task as completed updates Google Calendar event summary to [DONE]."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Read Chapter 4",
            duration_minutes=30,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=1, minutes=30),
        ),
    )
    event_id = task.google_calendar_event_id

    # Mark completed
    await TaskService.complete_task(db=test_db, user_id=user_id, task_id=task.id)

    remote_evt = mock_cal._events[event_id]
    assert "[DONE]" in remote_evt.title
    assert "Read Chapter 4" in remote_evt.title


@pytest.mark.asyncio
async def test_archiving_task_removes_calendar_event(test_db):
    """Verify archiving or cancelling a scheduled task cleans up the calendar appointment."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Obsolete Review Meeting",
            duration_minutes=30,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=1, minutes=30),
        ),
    )
    event_id = task.google_calendar_event_id
    assert event_id in mock_cal._events

    # Archive task
    await TaskService.archive_task(db=test_db, user_id=user_id, task_id=task.id)

    # Event must be removed from calendar
    assert event_id not in mock_cal._events
    assert task.google_calendar_event_id is None


@pytest.mark.asyncio
async def test_reconcile_event_to_task_movement(test_db):
    """Verify moving an event on the calendar reconciles scheduled time on associated task."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Write Project Specification",
            duration_minutes=60,
            scheduled_start=now + timedelta(hours=2),
            scheduled_end=now + timedelta(hours=3),
        ),
    )
    ext_id = task.google_calendar_event_id

    # Simulate user moving event on Google Calendar by 2 hours later
    moved_start = now + timedelta(hours=4)
    moved_end = now + timedelta(hours=5)
    reconciled_task = await CalendarSyncService.reconcile_event_to_task(
        db=test_db,
        external_id=ext_id,
        user_id=user_id,
        start_time=moved_start,
        end_time=moved_end,
    )

    assert reconciled_task is not None
    assert reconciled_task.id == task.id
    assert _norm_dt(reconciled_task.scheduled_start) == _norm_dt(moved_start)
    assert _norm_dt(reconciled_task.scheduled_end) == _norm_dt(moved_end)


@pytest.mark.asyncio
async def test_calendar_sync_fault_tolerance(test_db):
    """Verify task operation succeeds even when calendar provider throws rate-limit errors."""
    mock_cal = MockCalendarAdapter()
    mock_cal.simulate_rate_limit = True
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Offline Resilient Task",
            duration_minutes=45,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=1, minutes=45),
        ),
    )

    # Task is persisted successfully without breaking caller!
    assert task.id is not None
    assert task.title == "Offline Resilient Task"
    assert task.calendar_sync_status == "failed"
    assert task.calendar_sync_error is not None

    # Now recover calendar provider and test retry
    mock_cal.simulate_rate_limit = False
    retry_result = await CalendarSyncService.sync_pending_tasks(db=test_db, user_id=user_id)
    assert retry_result["synced"] == 1
    assert retry_result["failed"] == 0

    await test_db.refresh(task)
    assert task.calendar_sync_status == "synced"
    assert task.google_calendar_event_id is not None


@pytest.mark.asyncio
async def test_task_creation_unscheduled_with_deadline_remains_unscheduled(test_db):
    """Creating a task with only a deadline and scheduling_preference='unscheduled' stays unscheduled."""
    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    deadline_dt = now + timedelta(days=2)

    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Term Paper Proposal",
            duration_minutes=90,
            priority="P1",
            deadline=deadline_dt,
            scheduling_preference="unscheduled",
        ),
    )

    # Must stay cleanly unscheduled
    assert task.scheduled_start is None
    assert task.scheduled_end is None
    assert task.calendar_sync_status == "unscheduled"
    assert task.google_calendar_event_id is None
    # Deadline must NOT be treated as start time
    assert _norm_dt(task.deadline) == _norm_dt(deadline_dt)

    # No schedule block should exist for an unscheduled task
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is None


@pytest.mark.asyncio
async def test_auto_schedule_task_finds_slot_and_syncs(test_db):
    """auto_schedule_task allocates a working slot within working hours and synchronizes to calendar."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    deadline_dt = (now + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)

    # 1. Create unscheduled task
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Algorithm Analysis Assignment",
            duration_minutes=60,
            priority="P2",
            deadline=deadline_dt,
            scheduling_preference="unscheduled",
        ),
    )
    assert task.scheduled_start is None
    assert task.calendar_sync_status == "unscheduled"

    # 2. Trigger auto_schedule_task on-demand
    scheduled_task, success, message = await TaskService.auto_schedule_task(
        db=test_db, user_id=user_id, task_id=task.id
    )

    assert success is True
    assert "successfully scheduled" in message.lower()
    assert scheduled_task.scheduled_start is not None
    assert scheduled_task.scheduled_end is not None
    assert scheduled_task.calendar_sync_status == "synced"
    assert scheduled_task.google_calendar_event_id is not None

    # Google Calendar event was created
    assert scheduled_task.google_calendar_event_id in mock_cal._events

    # ScheduleBlock exists
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is not None
    assert block.start_time == scheduled_task.scheduled_start


@pytest.mark.asyncio
async def test_task_deletion_cleans_up_calendar_event_and_schedule_block(test_db):
    """Deleting a task deletes the remote Google Calendar event, local CalendarEvent, and ScheduleBlock."""
    mock_cal = MockCalendarAdapter()
    CalendarService.set_provider_override(mock_cal)

    user_id = await setup_user_with_calendar(test_db, sync_enabled=True)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Temporary Meeting Preparation",
            duration_minutes=45,
            scheduled_start=now + timedelta(hours=2),
            scheduled_end=now + timedelta(hours=2, minutes=45),
            scheduling_preference="manual",
        ),
    )

    event_id = task.google_calendar_event_id
    assert event_id is not None
    assert event_id in mock_cal._events

    # ScheduleBlock exists
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is not None

    # Local CalendarEvent exists
    local_ev = await test_db.scalar(select(CalendarEvent).where(CalendarEvent.external_id == event_id))
    assert local_ev is not None

    # Delete task
    await TaskService.delete_task(db=test_db, user_id=user_id, task_id=task.id)

    # Remote event was deleted from Google Calendar
    assert event_id not in mock_cal._events

    # Local CalendarEvent was deleted
    local_ev_after = await test_db.scalar(select(CalendarEvent).where(CalendarEvent.external_id == event_id))
    assert local_ev_after is None

    # ScheduleBlock was deleted
    block_after = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block_after is None


@pytest.mark.asyncio
async def test_ensure_schedule_block_for_task_creates_and_links_schedule(test_db):
    """ensure_schedule_block_for_task creates Schedule on the fly and upserts ScheduleBlock."""
    user_id = await setup_user_with_calendar(test_db, sync_enabled=False)

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Self-Study Session",
            duration_minutes=60,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=2),
            scheduling_preference="manual",
        ),
    )

    # ScheduleBlock must exist with source="task"
    block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.task_id == task.id))
    assert block is not None
    assert block.title == "Self-Study Session"
    assert block.block_type == "task"
    assert block.is_completed is False

    # Complete the task
    await TaskService.complete_task(db=test_db, user_id=user_id, task_id=task.id)
    await test_db.refresh(block)
    assert block.is_completed is True
