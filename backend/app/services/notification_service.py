"""Notification service for deadline monitoring, alert generation, and status management."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification import Notification
from app.db.models.task import Task


class NotificationService:
    """Service handling task deadline evaluations and notifications."""

    @staticmethod
    async def evaluate_user_notifications(
        db: AsyncSession, user_id: uuid.UUID
    ) -> tuple[int, list[Notification]]:
        """Evaluate deadlines for user tasks and generate due_soon, due_now, and overdue alerts.

        Suppresses alerts if the task is already completed or cancelled.
        Guarantees idempotency by checking existing alerts per task.
        """
        now = datetime.now(UTC)

        # 1. Fetch active tasks with deadlines (ignore completed/cancelled)
        stmt = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.is_archived.is_(False),
                Task.deadline.isnot(None),
                Task.status.not_in(["completed", "cancelled"]),
            )
        )
        result = await db.execute(stmt)
        tasks = list(result.scalars().all())

        new_notifications: list[Notification] = []

        for task in tasks:
            if not task.deadline:
                continue

            dl = task.deadline
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=UTC)
            else:
                dl = dl.astimezone(UTC)

            # Query existing notification types for this task
            existing_result = await db.execute(
                select(Notification.notification_type).where(
                    Notification.task_id == task.id,
                    Notification.user_id == user_id,
                )
            )
            existing_types = set(existing_result.scalars().all())

            # Case A: Overdue (now > deadline)
            if now > dl:
                if "overdue" not in existing_types:
                    notif = Notification(
                        user_id=user_id,
                        task_id=task.id,
                        notification_type="overdue",
                        title=f"Task Overdue: {task.title}",
                        message=f"'{task.title}' was due at {dl.strftime('%I:%M %p')}. Please complete or reschedule.",
                        scheduled_for=dl,
                        delivered_at=now,
                        is_read=False,
                    )
                    db.add(notif)
                    new_notifications.append(notif)
                continue

            # Case B: Due Now (within 10 minutes of deadline)
            if dl - timedelta(minutes=10) <= now <= dl:
                if "due_now" not in existing_types and "overdue" not in existing_types:
                    notif = Notification(
                        user_id=user_id,
                        task_id=task.id,
                        notification_type="due_now",
                        title=f"Task Due Now: {task.title}",
                        message=f"'{task.title}' is due right now at {dl.strftime('%I:%M %p')}.",
                        scheduled_for=dl,
                        delivered_at=now,
                        is_read=False,
                    )
                    db.add(notif)
                    new_notifications.append(notif)
                continue

            # Case C: Due Soon (within 1 hour of deadline)
            if now >= dl - timedelta(hours=1) and now < dl:
                if (
                    "due_soon" not in existing_types
                    and "due_now" not in existing_types
                    and "overdue" not in existing_types
                ):
                    notif = Notification(
                        user_id=user_id,
                        task_id=task.id,
                        notification_type="due_soon",
                        title=f"Upcoming Deadline: {task.title}",
                        message=f"'{task.title}' is due in less than 1 hour (at {dl.strftime('%I:%M %p')}).",
                        scheduled_for=dl - timedelta(hours=1),
                        delivered_at=now,
                        is_read=False,
                    )
                    db.add(notif)
                    new_notifications.append(notif)

        if new_notifications:
            await db.commit()
            for n in new_notifications:
                await db.refresh(n)

        return len(tasks), new_notifications

    @staticmethod
    async def get_user_notifications(
        db: AsyncSession,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Retrieve user notifications ordered chronologically descending."""
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))

        query = query.order_by(
            Notification.is_read.asc(),
            Notification.scheduled_for.desc(),
            Notification.created_at.desc(),
        ).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Get the count of unread notifications for a user."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification | None:
        """Mark a specific notification as read."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        result = await db.execute(stmt)
        notif = result.scalar_one_or_none()
        if not notif:
            return None

        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notif)
        return notif

    @staticmethod
    async def mark_all_as_read(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Mark all unread notifications as read for a user."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=now)
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount or 0
