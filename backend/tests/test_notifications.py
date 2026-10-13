"""Tests for the NotificationService: deadline evaluation, suppression, and idempotency."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.notification import Notification
from app.db.models.profile import Profile
from app.db.models.task import Task
from app.services.notification_service import NotificationService


@pytest.fixture
async def async_db():
    """Create a temporary in-memory async SQLite engine and session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_deadline_notifications_and_suppression(async_db):
    """Verify that overdue and due_soon tasks trigger alerts, while completed tasks suppress them."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="test@mentor.ai")
    async_db.add(profile)
    await async_db.commit()

    now = datetime.now(UTC)

    # 1. Overdue Task (due 2 hours ago)
    overdue_task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Overdue Report",
        deadline=now - timedelta(hours=2),
        status="pending",
    )

    # 2. Due Soon Task (due in 30 minutes)
    due_soon_task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Upcoming Client Presentation",
        deadline=now + timedelta(minutes=30),
        status="pending",
    )

    # 3. Completed Task (due 1 hour ago, but finished by user) -> MUST BE SUPPRESSED!
    completed_task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Completed Homework",
        deadline=now - timedelta(hours=1),
        status="completed",
    )

    async_db.add_all([overdue_task, due_soon_task, completed_task])
    await async_db.commit()

    # Run evaluation
    total_eval, new_notifs = await NotificationService.evaluate_user_notifications(
        db=async_db,
        user_id=user_id,
    )

    assert total_eval == 2  # Only active tasks evaluated (completed task ignored)
    assert len(new_notifs) == 2

    types = {n.notification_type for n in new_notifs}
    assert "overdue" in types
    assert "due_soon" in types

    # Verify suppression of completed task
    task_ids = {n.task_id for n in new_notifs}
    assert completed_task.id not in task_ids

    # 4. Verify IDEMPOTENCY: second run should not create duplicate alerts
    total_eval_2, new_notifs_2 = await NotificationService.evaluate_user_notifications(
        db=async_db,
        user_id=user_id,
    )
    assert len(new_notifs_2) == 0  # No duplicate alerts!

    # 5. Verify unread count and mark as read
    unread_count = await NotificationService.get_unread_count(db=async_db, user_id=user_id)
    assert unread_count == 2

    # Mark all read
    marked = await NotificationService.mark_all_as_read(db=async_db, user_id=user_id)
    assert marked == 2

    unread_count_after = await NotificationService.get_unread_count(db=async_db, user_id=user_id)
    assert unread_count_after == 0
