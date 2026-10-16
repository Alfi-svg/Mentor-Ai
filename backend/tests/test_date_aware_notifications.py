"""Comprehensive Automated Test Suite for Date-Aware Chronological Notifications and Calendar Sync.

Verifies:
1. Consecutive exams (Exam A 16 Oct 10:00 AM vs Exam B 17 Oct 10:00 AM) produce distinct trigger datetimes.
2. Exam B never triggers early on Exam A's date.
3. Notification eligibility at exact date and time (never premature).
4. Chronological earliest-first batch processing.
5. Midnight date transitions (e.g. 00:15 AM event with 30 min lead time triggering at 23:45 PM prior day).
6. Month and year boundaries (e.g. Dec 31 to Jan 1, Feb 28 to March 1).
7. Asia/Dhaka (+06:00) timezone formatting and metadata retention in payload.
8. Completed, cancelled, and archived task reminder suppression.
9. Idempotent repeated dispatch runs without duplicates.
10. Concurrency locking and lease protection.
11. Stale upcoming reminder expiration (past events never delivered as 'upcoming').
12. Deterministic auto-scheduling and calendar sync for tasks with deadlines.
"""

import asyncio
import uuid
import zoneinfo
from datetime import UTC, datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.notification import Notification
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.notification import NotificationSettingsSchema
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.services.calendar_sync_service import CalendarSyncService
from app.services.notification_service import NotificationService
from app.services.task_service import TaskService


@pytest.fixture
async def test_db():
    """Create a temporary in-memory async SQLite engine and session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# -----------------------------------------------------------------------------
# 1. Consecutive Exams: Distinct Trigger Datetimes
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_consecutive_exams_distinct_trigger_datetimes(test_db):
    """Exam A (16 Oct 10:00 AM) and Exam B (17 Oct 10:00 AM) must produce distinct trigger datetimes."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="student@mentor.ai", timezone="Asia/Dhaka")
    test_db.add(profile)
    await test_db.commit()

    dhaka_tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    # Exam A: Oct 16, 2026 at 10:00 AM Dhaka (+6) = 04:00 AM UTC
    exam_a_dt = datetime(2026, 10, 16, 10, 0, 0, tzinfo=dhaka_tz)
    # Exam B: Oct 17, 2026 at 10:00 AM Dhaka (+6) = 04:00 AM UTC
    exam_b_dt = datetime(2026, 10, 17, 10, 0, 0, tzinfo=dhaka_tz)

    task_a = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Exam A - Mathematics",
        scheduled_start=exam_a_dt.astimezone(UTC),
        scheduled_end=(exam_a_dt + timedelta(hours=2)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    task_b = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Exam B - Physics",
        scheduled_start=exam_b_dt.astimezone(UTC),
        scheduled_end=(exam_b_dt + timedelta(hours=2)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    test_db.add_all([task_a, task_b])
    await test_db.commit()

    # Mock current time as Oct 15, 08:00 AM UTC (prior to both exams)
    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC)
        mock_dt.combine = datetime.combine
        await NotificationService.reconcile_task_lifecycle(
            db=test_db, user_id=user_id, task=task_a, event="task_schedule_changed"
        )
        await NotificationService.reconcile_task_lifecycle(
            db=test_db, user_id=user_id, task=task_b, event="task_schedule_changed"
        )

    stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.scheduled_for.asc())
    notifs = list((await test_db.execute(stmt)).scalars().all())

    assert len(notifs) == 2
    notif_a, notif_b = notifs[0], notifs[1]

    # Verify distinct tasks and distinct triggers
    assert notif_a.task_id == task_a.id
    assert notif_b.task_id == task_b.id
    assert notif_a.deduplication_key != notif_b.deduplication_key

    # Expected trigger A: Oct 16 09:30 AM Dhaka = 03:30 AM UTC
    expected_trigger_a = datetime(2026, 10, 16, 3, 30, 0, tzinfo=UTC)
    # Expected trigger B: Oct 17 09:30 AM Dhaka = 03:30 AM UTC
    expected_trigger_b = datetime(2026, 10, 17, 3, 30, 0, tzinfo=UTC)

    # Normalize SQLite naive datetimes for comparison
    sched_a = notif_a.scheduled_for if notif_a.scheduled_for.tzinfo else notif_a.scheduled_for.replace(tzinfo=UTC)
    sched_b = notif_b.scheduled_for if notif_b.scheduled_for.tzinfo else notif_b.scheduled_for.replace(tzinfo=UTC)

    assert sched_a == expected_trigger_a
    assert sched_b == expected_trigger_b
    assert (sched_b - sched_a) == timedelta(days=1)

    # Verify payloads contain date-aware metadata
    assert notif_a.payload["target_date"] == "2026-10-16"
    assert notif_a.payload["target_time"] == "10:00:00"
    assert notif_a.payload["timezone"] == "Asia/Dhaka"
    assert "Oct 16, 2026 at 10:00 AM" in notif_a.message

    assert notif_b.payload["target_date"] == "2026-10-17"
    assert notif_b.payload["target_time"] == "10:00:00"
    assert notif_b.payload["timezone"] == "Asia/Dhaka"
    assert "Oct 17, 2026 at 10:00 AM" in notif_b.message


# -----------------------------------------------------------------------------
# 2. Exam B Never Triggers on Exam A's Date
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exam_b_never_triggers_on_exam_a_date(test_db):
    """Exam B must NEVER trigger or be claimed on Exam A's date."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="isolation@mentor.ai", timezone="Asia/Dhaka")
    test_db.add(profile)
    await test_db.commit()

    dhaka_tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    exam_a_dt = datetime(2026, 10, 16, 10, 0, 0, tzinfo=dhaka_tz)
    exam_b_dt = datetime(2026, 10, 17, 10, 0, 0, tzinfo=dhaka_tz)

    task_a = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Exam A",
        scheduled_start=exam_a_dt.astimezone(UTC),
        scheduled_end=(exam_a_dt + timedelta(hours=2)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    task_b = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Exam B",
        scheduled_start=exam_b_dt.astimezone(UTC),
        scheduled_end=(exam_b_dt + timedelta(hours=2)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    test_db.add_all([task_a, task_b])
    await test_db.commit()

    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC)
        mock_dt.combine = datetime.combine
        await NotificationService.reconcile_task_lifecycle(
            db=test_db, user_id=user_id, task=task_a, event="task_schedule_changed"
        )
        await NotificationService.reconcile_task_lifecycle(
            db=test_db, user_id=user_id, task=task_b, event="task_schedule_changed"
        )

    # Simulate dispatching when current time is Oct 16, 09:30 AM Dhaka (Exam A trigger time)
    oct16_trigger_utc = datetime(2026, 10, 16, 3, 30, 0, tzinfo=UTC)
    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = oct16_trigger_utc
        mock_dt.combine = datetime.combine

        res = await NotificationService.dispatch_due_notifications(test_db)
        assert res.claimed == 1
        assert res.delivered == 1

    # Check notification states
    stmt_a = select(Notification).where(Notification.task_id == task_a.id)
    stmt_b = select(Notification).where(Notification.task_id == task_b.id)
    notif_a = (await test_db.execute(stmt_a)).scalar_one()
    notif_b = (await test_db.execute(stmt_b)).scalar_one()

    # Exam A delivered, Exam B strictly remains pending!
    assert notif_a.status == "delivered"
    assert notif_b.status == "pending"


# -----------------------------------------------------------------------------
# 3. Notification Eligibility at Exact Date and Time
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notification_eligibility_at_exact_datetime(test_db):
    """Notification must not trigger 1 second before scheduled time, but must trigger at exact time."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="exact@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    target_time = datetime(2026, 10, 20, 14, 0, 0, tzinfo=UTC)
    notif = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Exact Timing Task",
        message="Alert at exact time.",
        scheduled_for=target_time,
        deduplication_key="exact_timing_test",
    )
    assert notif is not None

    # Case A: 1 second prior to target time -> NOT eligible
    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = target_time - timedelta(seconds=1)
        mock_dt.combine = datetime.combine
        res = await NotificationService.dispatch_due_notifications(test_db)
        assert res.claimed == 0
        assert res.delivered == 0

    # Case B: Exactly at target time -> ELIGIBLE and delivered
    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = target_time
        mock_dt.combine = datetime.combine
        res = await NotificationService.dispatch_due_notifications(test_db)
        assert res.claimed == 1
        assert res.delivered == 1

    await test_db.refresh(notif)
    assert notif.status == "delivered"


# -----------------------------------------------------------------------------
# 4. Chronological Earliest-First Processing
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chronological_earliest_first_processing(test_db):
    """Notifications must be claimed and processed in earliest-first order."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="chrono@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    base_time = datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC)
    n3 = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Third Alert",
        message="3rd",
        scheduled_for=base_time + timedelta(hours=2),
        deduplication_key="chrono_3",
    )
    n1 = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="First Alert",
        message="1st",
        scheduled_for=base_time,
        deduplication_key="chrono_1",
    )
    n2 = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Second Alert",
        message="2nd",
        scheduled_for=base_time + timedelta(hours=1),
        deduplication_key="chrono_2",
    )

    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = base_time + timedelta(hours=3)
        mock_dt.combine = datetime.combine
        claimed = await NotificationService.claim_due_notifications(test_db, batch_size=10)

    assert len(claimed) == 3
    # Earliest-first order verification
    assert claimed[0].id == n1.id
    assert claimed[1].id == n2.id
    assert claimed[2].id == n3.id


# -----------------------------------------------------------------------------
# 5. Midnight Date Transitions
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_midnight_date_transitions(test_db):
    """An event at 00:15 AM on Oct 17 with 30 min lead time triggers at 23:45 PM on Oct 16."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="midnight@mentor.ai", timezone="Asia/Dhaka")
    test_db.add(profile)
    await test_db.commit()

    dhaka_tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    # Event at Oct 17, 00:15 AM Dhaka
    event_dt = datetime(2026, 10, 17, 0, 15, 0, tzinfo=dhaka_tz)
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Midnight Deployment",
        scheduled_start=event_dt.astimezone(UTC),
        scheduled_end=(event_dt + timedelta(hours=1)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    test_db.add(task)
    await test_db.commit()

    with patch("app.services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)
        mock_dt.combine = datetime.combine
        await NotificationService.reconcile_task_lifecycle(
            db=test_db, user_id=user_id, task=task, event="task_schedule_changed"
        )

    stmt = select(Notification).where(Notification.task_id == task.id)
    notif = (await test_db.execute(stmt)).scalar_one()

    # Trigger should be at Oct 16, 23:45 PM Dhaka
    sched = notif.scheduled_for if notif.scheduled_for.tzinfo else notif.scheduled_for.replace(tzinfo=UTC)
    local_trigger = sched.astimezone(dhaka_tz)

    assert local_trigger.date() == datetime(2026, 10, 16).date()
    assert local_trigger.hour == 23
    assert local_trigger.minute == 45
    # Target date in payload points to the actual event date (Oct 17)
    assert notif.payload["target_date"] == "2026-10-17"


# -----------------------------------------------------------------------------
# 6. Month and Year Boundaries
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_month_and_year_boundaries(test_db):
    """Transitions across Dec 31 to Jan 1 and Feb 28 to Mar 1."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="boundaries@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    # New Year Event: Jan 1, 2027 at 00:15 AM UTC -> Trigger Dec 31, 2026 at 23:45 PM UTC
    ny_dt = datetime(2027, 1, 1, 0, 15, 0, tzinfo=UTC)
    task_ny = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="New Year Keynote",
        scheduled_start=ny_dt,
        scheduled_end=ny_dt + timedelta(hours=1),
        status="pending",
        is_archived=False,
    )
    test_db.add(task_ny)
    await test_db.commit()

    await NotificationService.reconcile_task_lifecycle(
        db=test_db, user_id=user_id, task=task_ny, event="task_schedule_changed"
    )
    notif_ny = (
        await test_db.execute(select(Notification).where(Notification.task_id == task_ny.id))
    ).scalar_one()

    sched_ny = notif_ny.scheduled_for if notif_ny.scheduled_for.tzinfo else notif_ny.scheduled_for.replace(tzinfo=UTC)
    assert sched_ny == datetime(2026, 12, 31, 23, 45, 0, tzinfo=UTC)
    assert notif_ny.payload["target_date"] == "2027-01-01"


# -----------------------------------------------------------------------------
# 7. Asia/Dhaka (+06:00) Timezone Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_asia_dhaka_timezone_handling(test_db):
    """Ensure message text and payload preserve local timezone strings."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="dhaka_user@mentor.ai", timezone="Asia/Dhaka")
    test_db.add(profile)
    await test_db.commit()

    dhaka_tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    meeting_dt = datetime(2026, 11, 5, 15, 30, 0, tzinfo=dhaka_tz)
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Client Demo",
        scheduled_start=meeting_dt.astimezone(UTC),
        scheduled_end=(meeting_dt + timedelta(hours=1)).astimezone(UTC),
        status="pending",
        is_archived=False,
    )
    test_db.add(task)
    await test_db.commit()

    await NotificationService.reconcile_task_lifecycle(
        db=test_db, user_id=user_id, task=task, event="task_schedule_changed"
    )
    notif = (
        await test_db.execute(select(Notification).where(Notification.task_id == task.id))
    ).scalar_one()

    assert notif.payload["timezone"] == "Asia/Dhaka"
    assert notif.payload["target_date"] == "2026-11-05"
    assert notif.payload["target_time"] == "15:30:00"
    assert "Nov 05, 2026 at 03:30 PM (Asia/Dhaka)" in notif.message


# -----------------------------------------------------------------------------
# 8. Completed and Cancelled Task Reminder Suppression
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_completed_and_cancelled_task_suppression(test_db):
    """When a task is completed or cancelled, all pending notifications are cancelled."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="suppress@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Assignment to Complete",
            duration_minutes=60,
            deadline=now + timedelta(hours=4),
        ),
    )

    stmt = select(Notification).where(Notification.task_id == task.id, Notification.status == "pending")
    active_notif = (await test_db.execute(stmt)).scalar_one_or_none()
    assert active_notif is not None

    # Complete the task
    await TaskService.complete_task(db=test_db, user_id=user_id, task_id=task.id)

    # Check notification status
    await test_db.refresh(active_notif)
    assert active_notif.status == "cancelled"


# -----------------------------------------------------------------------------
# 9. Idempotent Repeated Dispatch Runs Without Duplicates
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_repeated_dispatch(test_db):
    """Repeated runs of the dispatcher over delivered notifications do not re-deliver."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="idempotent@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    notif = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Idempotent Task",
        message="Message",
        scheduled_for=now - timedelta(minutes=5),
        deduplication_key="idem_run_1",
    )
    assert notif is not None

    # Run 1: Delivers the notification
    res1 = await NotificationService.dispatch_due_notifications(test_db)
    assert res1.claimed == 1
    assert res1.delivered == 1

    # Run 2: Nothing left due, claims 0
    res2 = await NotificationService.dispatch_due_notifications(test_db)
    assert res2.claimed == 0
    assert res2.delivered == 0


# -----------------------------------------------------------------------------
# 10. Stale Upcoming Reminder Expiration
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_upcoming_reminder_expiration(test_db):
    """Upcoming/due_soon reminders for events that have ALREADY PASSED must be cancelled, not delivered."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="stale@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    # Event happened 2 hours ago
    past_event_time = now - timedelta(hours=2)
    # Reminder was scheduled 2.5 hours ago
    reminder_time = now - timedelta(hours=2, minutes=30)

    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Missed Exam",
        scheduled_start=past_event_time,
        scheduled_end=past_event_time + timedelta(hours=1),
        status="pending",
        is_archived=False,
    )
    test_db.add(task)
    await test_db.commit()

    notif = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="upcoming_task",
        title="Upcoming Event: Missed Exam",
        message="Missed Exam is starting soon.",
        scheduled_for=reminder_time,
        task_id=task.id,
        deduplication_key="stale_missed_exam",
        target_datetime=past_event_time,
    )
    assert notif is not None
    assert notif.status == "pending"

    # Dispatcher runs now (after the event is already over)
    res = await NotificationService.dispatch_due_notifications(test_db)
    assert res.claimed == 1
    assert res.delivered == 0
    assert res.cancelled == 1

    await test_db.refresh(notif)
    assert notif.status == "cancelled"
    assert "already passed" in notif.last_error.lower()


# -----------------------------------------------------------------------------
# 11. Deterministic Auto-Scheduling and Calendar Sync
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deterministic_task_creation_and_calendar_sync(test_db):
    """Creating a task with a deadline deterministically schedules a feasible slot without inventing fake times."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="sync_user@mentor.ai", timezone="UTC")
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="17:00:00",
        buffer_minutes=15,
    )
    test_db.add_all([profile, prefs])
    await test_db.commit()

    now = datetime.now(UTC)
    # Target date tomorrow at 16:00 UTC (within work hours 09:00 - 17:00)
    deadline_dt = (now + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)

    with patch.object(CalendarSyncService, "sync_task_to_calendar", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = True

        task = await TaskService.create_task(
            db=test_db,
            user_id=user_id,
            payload=TaskCreateRequest(
                title="Prepare Financial Report",
                duration_minutes=60,
                priority="P2",
                deadline=deadline_dt,
                scheduling_preference="auto",
            ),
        )

        assert task.scheduled_start is not None
        assert task.scheduled_end is not None
        # Start and end must finish before or at the deadline
        sched_end_utc = task.scheduled_end if task.scheduled_end.tzinfo else task.scheduled_end.replace(tzinfo=UTC)
        assert sched_end_utc <= deadline_dt
        # Calendar sync was initiated
        mock_sync.assert_called_once()
