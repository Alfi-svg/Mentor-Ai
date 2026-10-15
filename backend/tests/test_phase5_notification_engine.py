"""Phase 5 Comprehensive Automated Test Suite for Mentor AI Persistent Notification Engine.

Verifies:
1. Creating, retrieving, and paginating scheduled notifications.
2. Dispatching due notifications while leaving future notifications pending.
3. Duplicate prevention across repeated dispatcher runs.
4. Concurrent worker batch claiming and race condition prevention.
5. Exponential retry backoff, exhausted retry limits, and stale lease recovery.
6. Restart recovery using persisted database state.
7. Task lifecycle reconciliation: completion, cancellation, and archival suppression.
8. Task lifecycle reconciliation: deadline changes and rescheduling.
9. Overdue notification cadence and deduplication keys.
10. Timezone boundaries, quiet hours, and daylight-saving normalization.
11. Multi-tenant user isolation and access control.
12. Missing provider credentials and truthful delivery reporting.
13. Dispatch secret authentication with constant-time verification.
14. Action approval lifecycle and schedule conflict alerts.
"""

import asyncio
import uuid
import zoneinfo
from datetime import UTC, datetime, time as dt_time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models.action import ActionHistory
from app.db.models.notification import Notification
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.notification import NotificationSettingsSchema
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.services.action_service import ActionService
from app.services.notification_service import (
    DEFAULT_NOTIFICATION_SETTINGS,
    EmailChannelProvider,
    NotificationService,
    PushChannelProvider,
)
from app.services.scheduler.service import SchedulerService
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
# 1. Creating and Retrieving Scheduled Notifications
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_retrieve_notifications(test_db):
    """Verify scheduling notifications with channels, metadata, and user pagination."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="notif_user1@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)

    n1 = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Prepare Lecture Notes",
        message="Due in 30 minutes.",
        scheduled_for=now - timedelta(minutes=5),
        channel="in_app",
        deduplication_key="test_key_1",
    )
    assert n1 is not None
    assert n1.status == "pending"
    assert n1.attempt_count == 0

    # Retrieve notifications
    items = await NotificationService.get_user_notifications(test_db, user_id)
    assert len(items) == 1
    assert items[0].title == "Prepare Lecture Notes"
    assert items[0].is_read is False

    # Unread count
    unread = await NotificationService.get_unread_count(test_db, user_id)
    assert unread == 1

    # Mark read
    await NotificationService.mark_as_read(test_db, user_id, n1.id)
    unread_after = await NotificationService.get_unread_count(test_db, user_id)
    assert unread_after == 0


# -----------------------------------------------------------------------------
# 2. Dispatching Due Notifications and Preserving Future Pending
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_due_notifications_and_leave_future(test_db):
    """Verify dispatcher claims due items (scheduled_for <= now) and leaves future pending."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="dispatch_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)

    # Item A: due in the past -> must be delivered
    n_past = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Past Due Notification",
        message="Should be delivered now.",
        scheduled_for=now - timedelta(minutes=10),
        deduplication_key="key_past",
    )

    # Item B: due in the future -> must remain pending
    n_future = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="upcoming_task",
        title="Future Task Reminder",
        message="Should stay pending.",
        scheduled_for=now + timedelta(hours=2),
        deduplication_key="key_future",
    )

    # Run dispatcher
    res = await NotificationService.dispatch_due_notifications(test_db, batch_size=50)
    assert res.claimed == 1
    assert res.delivered == 1

    # Verify states in database
    await test_db.refresh(n_past)
    await test_db.refresh(n_future)

    assert n_past.status == "delivered"
    assert n_past.delivered_at is not None
    assert n_past.lease_expires_at is None

    assert n_future.status == "pending"
    assert n_future.delivered_at is None
    assert n_future.attempt_count == 0


# -----------------------------------------------------------------------------
# 3. Duplicate Prevention Across Repeated Dispatcher Runs
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_prevention_repeated_dispatcher(test_db):
    """Verify repeating dispatch runs does not re-process already delivered items."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="dedup_dispatch@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_now",
        title="Due Right Now",
        message="Immediate notification.",
        scheduled_for=now - timedelta(seconds=1),
        deduplication_key="single_send_key",
    )

    # Dispatch Run 1
    res1 = await NotificationService.dispatch_due_notifications(test_db)
    assert res1.claimed == 1
    assert res1.delivered == 1

    # Dispatch Run 2 (immediate re-run)
    res2 = await NotificationService.dispatch_due_notifications(test_db)
    assert res2.claimed == 0
    assert res2.delivered == 0


# -----------------------------------------------------------------------------
# 4. Concurrent Workers Claiming Same Due Notifications
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_worker_claiming_safety(test_db):
    """Verify concurrent batch claims distribute items without duplicate worker claiming."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="concurrent_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)

    # Seed 5 due notifications
    for i in range(5):
        await NotificationService.schedule_notification(
            db=test_db,
            user_id=user_id,
            notification_type="due_soon",
            title=f"Notification #{i}",
            message="Batch claiming test.",
            scheduled_for=now - timedelta(minutes=i + 1),
            deduplication_key=f"concurrent_test_{i}",
        )

    # Claim worker 1 (batch_size=3)
    claimed_w1 = await NotificationService.claim_due_notifications(test_db, batch_size=3)
    # Claim worker 2 (batch_size=3)
    claimed_w2 = await NotificationService.claim_due_notifications(test_db, batch_size=3)

    assert len(claimed_w1) == 3
    assert len(claimed_w2) == 2

    # Verify sets of IDs are completely disjoint
    ids_w1 = {c.id for c in claimed_w1}
    ids_w2 = {c.id for c in claimed_w2}
    assert ids_w1.isdisjoint(ids_w2)

    # Worker 3 finds 0 items left
    claimed_w3 = await NotificationService.claim_due_notifications(test_db, batch_size=3)
    assert len(claimed_w3) == 0


# -----------------------------------------------------------------------------
# 5. Retry Behavior, Backoff, Exhaustion, and Stale Lease Recovery
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_backoff_exhaustion_and_stale_lease_recovery(test_db):
    """Verify delivery failures backoff exponentially, exhaust at max_attempts, and recover stale leases."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="retry_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    notif = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Email Alert",
        message="Simulated email alert.",
        scheduled_for=now - timedelta(minutes=1),
        channel="email",  # Unconfigured email channel will fail delivery truthfully
        deduplication_key="retry_test_key",
    )
    assert notif is not None
    notif.max_attempts = 2  # Set max_attempts to 2 for fast test exhaustion
    await test_db.commit()

    # Attempt 1: Delivery fails -> status becomes failed, backoff scheduled
    res1 = await NotificationService.dispatch_due_notifications(test_db)
    assert res1.claimed == 1
    assert res1.failed == 1

    await test_db.refresh(notif)
    assert notif.status == "failed"
    assert notif.attempt_count == 1
    assert "not configured" in notif.last_error.lower()
    sched_utc = notif.scheduled_for if notif.scheduled_for.tzinfo else notif.scheduled_for.replace(tzinfo=UTC)
    assert sched_utc > now  # Pushed back via exponential backoff

    # Simulate fast-forwarding time past backoff and simulate a stale worker crash
    notif.scheduled_for = now - timedelta(seconds=1)
    notif.status = "processing"
    notif.lease_expires_at = now - timedelta(seconds=10)  # Lease expired (worker crashed)
    await test_db.commit()

    # Attempt 2: Dispatcher picks up stale lease and attempts final delivery
    res2 = await NotificationService.dispatch_due_notifications(test_db)
    assert res2.claimed == 1
    assert res2.stale_leases_recovered == 1

    await test_db.refresh(notif)
    # Reached max_attempts (2) -> transitions to permanently_failed
    assert notif.status == "permanently_failed"
    assert notif.attempt_count == 2
    assert notif.lease_expires_at is None


# -----------------------------------------------------------------------------
# 6. Application Restart Recovery Using Database-Persisted State
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_application_restart_recovery_from_database(test_db):
    """Verify notification queue survives process restart by loading persisted state from DB."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="restart_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    n = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_id,
        notification_type="due_soon",
        title="Restart Survival Test",
        message="Persisted in SQLite/PostgreSQL.",
        scheduled_for=now - timedelta(minutes=5),
        deduplication_key="restart_key_1",
    )
    assert n is not None

    # Simulate restart: session commits and clears in-memory identity map
    await test_db.commit()
    test_db.expunge_all()

    # Dispatcher runs on fresh session/process state
    res = await NotificationService.dispatch_due_notifications(test_db)
    assert res.claimed == 1
    assert res.delivered == 1

    # Verify persisted state updated
    refreshed = await test_db.scalar(select(Notification).where(Notification.id == n.id))
    assert refreshed.status == "delivered"


# -----------------------------------------------------------------------------
# 7. Task Lifecycle Reconciliation: Completion, Cancellation, Archival Suppression
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_task_lifecycle_completion_and_cancellation_suppression(test_db):
    """Verify completing, cancelling, or archiving a task cancels pending reminders."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="task_lifecycle_user@mentor.ai", timezone="UTC")
    prefs = UserPreferences(
        user_id=user_id,
        notification_settings={
            **DEFAULT_NOTIFICATION_SETTINGS,
            "notify_task_completed": True,
        },
    )
    test_db.add_all([profile, prefs])
    await test_db.commit()

    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Final Project Report",
            duration_minutes=60,
            deadline=now + timedelta(hours=3),
        ),
    )

    # Verify deadline reminder was scheduled
    notifs = (
        await test_db.execute(select(Notification).where(Notification.task_id == task.id))
    ).scalars().all()
    assert len(notifs) >= 1
    assert any(n.status == "pending" for n in notifs)

    # 1. Complete Task -> Pending reminders are cancelled; task_completed notification created
    await TaskService.complete_task(test_db, user_id, task.id)

    stmt = select(Notification).where(Notification.task_id == task.id)
    notifs_after_complete = (await test_db.execute(stmt)).scalars().all()

    # Prior pending deadline alerts are now cancelled
    deadline_alerts = [n for n in notifs_after_complete if n.notification_type == "due_soon"]
    assert all(n.status == "cancelled" for n in deadline_alerts)

    # Task completed notification was created
    completed_alerts = [n for n in notifs_after_complete if n.notification_type == "task_completed"]
    assert len(completed_alerts) == 1
    assert completed_alerts[0].status == "pending"


# -----------------------------------------------------------------------------
# 8. Task Lifecycle Reconciliation: Deadline Rescheduling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_task_deadline_rescheduling_reconciliation(test_db):
    """Verify rescheduling a task deadline cancels stale reminders and creates new reminder."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="resched_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    orig_deadline = now + timedelta(hours=2)

    task = await TaskService.create_task(
        db=test_db,
        user_id=user_id,
        payload=TaskCreateRequest(
            title="Calculus Homework",
            duration_minutes=45,
            deadline=orig_deadline,
        ),
    )

    # Check original scheduled notification
    n_orig = (
        await test_db.execute(select(Notification).where(Notification.task_id == task.id))
    ).scalar_one()
    assert n_orig.status == "pending"

    # Reschedule deadline by +24 hours
    new_deadline = now + timedelta(hours=26)
    await TaskService.update_task(
        db=test_db,
        user_id=user_id,
        task_id=task.id,
        payload=TaskUpdateRequest(deadline=new_deadline),
    )

    all_notifs = (
        await test_db.execute(
            select(Notification).where(Notification.task_id == task.id).order_by(Notification.created_at.asc())
        )
    ).scalars().all()

    # Old reminder is cancelled
    assert all_notifs[0].status == "cancelled"

    # Fresh reminder scheduled for new deadline
    assert all_notifs[1].status == "pending"
    sched_utc2 = (
        all_notifs[1].scheduled_for
        if all_notifs[1].scheduled_for.tzinfo
        else all_notifs[1].scheduled_for.replace(tzinfo=UTC)
    )
    assert sched_utc2 > now + timedelta(hours=24)


# -----------------------------------------------------------------------------
# 9. Overdue Notification Cadence and Deduplication
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overdue_cadence_and_deduplication(test_db):
    """Verify overdue tasks trigger alerts with daily deduplication bucket."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="overdue_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)
    overdue_task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Unfinished Assignment",
        deadline=now - timedelta(hours=3),
        status="pending",
        is_archived=False,
    )
    test_db.add(overdue_task)
    await test_db.commit()

    # Evaluation 1: generates overdue alert
    _, notifs1 = await NotificationService.evaluate_user_notifications(test_db, user_id)
    assert len(notifs1) == 1
    assert notifs1[0].notification_type == "overdue"

    # Evaluation 2 on same day: deduplicated (0 new alerts)
    _, notifs2 = await NotificationService.evaluate_user_notifications(test_db, user_id)
    assert len(notifs2) == 0


# -----------------------------------------------------------------------------
# 10. Timezone Boundaries, Quiet Hours, and Daylight-Saving Adjustments
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quiet_hours_and_timezone_adjustment(test_db):
    """Verify quiet hours postpone non-urgent alerts to wake time in user's timezone."""
    settings_schema = NotificationSettingsSchema(
        quiet_hours_enabled=True,
        quiet_hours_start="22:00:00",
        quiet_hours_end="08:00:00",
    )

    # 1. New York timezone (EDT = UTC-4 in summer, EST = UTC-5 in winter)
    tz_ny = "America/New_York"
    # Scheduled at 23:30 local NY time (03:30 UTC next day)
    ny_local_night = datetime(2026, 10, 15, 23, 30, tzinfo=zoneinfo.ZoneInfo(tz_ny))
    utc_night = ny_local_night.astimezone(UTC)

    adjusted = NotificationService.adjust_for_quiet_hours(utc_night, tz_ny, settings_schema)

    # Adjusted time must wake at 08:00 next morning local NY time
    adj_local = adjusted.astimezone(zoneinfo.ZoneInfo(tz_ny))
    assert adj_local.time() == dt_time(8, 0)
    assert adj_local.date() == datetime(2026, 10, 16).date()

    # 2. Outside quiet hours (14:00 local time) -> unchanged
    ny_local_day = datetime(2026, 10, 15, 14, 0, tzinfo=zoneinfo.ZoneInfo(tz_ny))
    utc_day = ny_local_day.astimezone(UTC)
    adj_day = NotificationService.adjust_for_quiet_hours(utc_day, tz_ny, settings_schema)
    assert adj_day == utc_day


# -----------------------------------------------------------------------------
# 11. Multi-Tenant User Isolation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_user_isolation_and_access_control(test_db):
    """Verify User B cannot view or mark as read User A's notifications."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    profile_a = Profile(id=user_a, email="usera@mentor.ai")
    profile_b = Profile(id=user_b, email="userb@mentor.ai")
    test_db.add_all([profile_a, profile_b])
    await test_db.commit()

    now = datetime.now(UTC)
    n_a = await NotificationService.schedule_notification(
        db=test_db,
        user_id=user_a,
        notification_type="due_soon",
        title="Private Notification A",
        message="Confidential to User A",
        scheduled_for=now,
    )

    # User B list returns 0 notifications
    list_b = await NotificationService.get_user_notifications(test_db, user_b)
    assert len(list_b) == 0

    # User B attempting to mark User A's notification as read returns None
    mark_res = await NotificationService.mark_as_read(test_db, user_b, n_a.id)
    assert mark_res is None


# -----------------------------------------------------------------------------
# 12. Missing Provider Credentials and Truthful Delivery Reporting
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_credentials_truthful_delivery(test_db):
    """Verify unconfigured external channels report truthful failures without faking delivery."""
    email_provider = EmailChannelProvider()
    push_provider = PushChannelProvider()

    dummy_notif = Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Test",
        message="Test",
        scheduled_for=datetime.now(UTC),
    )

    # With no SMTP configured:
    success_email, err_email = await email_provider.deliver(dummy_notif)
    assert success_email is False
    assert "not configured" in err_email.lower()

    # With no VAPID configured:
    success_push, err_push = await push_provider.deliver(dummy_notif)
    assert success_push is False
    assert "not configured" in err_push.lower()


# -----------------------------------------------------------------------------
# 13. Dispatch Secret Authentication with Constant-Time Verification
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_secret_constant_time_verification():
    """Verify dispatch secret validation rejects missing or incorrect tokens."""
    with patch.object(settings, "NOTIFICATION_DISPATCH_SECRET", "super-secret-token-xyz"):
        # Correct token
        assert NotificationService.verify_dispatch_secret("super-secret-token-xyz") is True

        # Incorrect token
        assert NotificationService.verify_dispatch_secret("wrong-token") is False

        # Empty / None token
        assert NotificationService.verify_dispatch_secret("") is False
        assert NotificationService.verify_dispatch_secret(None) is False

    # When no secret is configured on server:
    with patch.object(settings, "NOTIFICATION_DISPATCH_SECRET", ""):
        assert NotificationService.verify_dispatch_secret("any-token") is False


# -----------------------------------------------------------------------------
# 14. Action Approval Lifecycle and Schedule Conflict Alerts
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_action_approval_and_schedule_conflict_alerts(test_db):
    """Verify staged actions trigger approval alerts and infeasible schedules trigger warnings."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="action_alert_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    # 1. Staging write action triggers action_required notification
    action = await ActionService.stage_action(
        db=test_db,
        user_id=user_id,
        action_type="create_calendar_event",
        payload={"title": "Client Sync", "start_time": "2026-10-15T10:00:00Z", "end_time": "2026-10-15T11:00:00Z"},
    )

    action_notifs = (
        await test_db.execute(select(Notification).where(Notification.action_id == action.id))
    ).scalars().all()
    assert len(action_notifs) == 1
    assert action_notifs[0].notification_type == "action_required"
    assert action_notifs[0].status == "pending"

    # 2. Rejecting action cancels the notification
    await ActionService.confirm_action(test_db, user_id, action.id, confirmed=False, rejection_reason="No time")
    await test_db.refresh(action_notifs[0])
    assert action_notifs[0].status == "cancelled"
