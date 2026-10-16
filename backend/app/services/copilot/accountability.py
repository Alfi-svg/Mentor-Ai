"""Student Accountability & Constructive Missed-Session Detection Service."""

import uuid
import zoneinfo
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.notification import Notification
from app.db.models.profile import Profile
from app.db.models.schedule import ScheduleBlock
from app.db.models.task import Task
from app.schemas.copilot import StudentAccountabilitySummary

logger = get_logger("mentor_ai.copilot.accountability")


class StudentAccountabilityService:
    """Monitors student schedule execution and triggers supportive recovery notifications."""

    @classmethod
    async def evaluate_missed_sessions(
        cls, db: AsyncSession, user_id: uuid.UUID
    ) -> list[Notification]:
        """Detect scheduled blocks whose time has ended while the task remains incomplete.

        Creates supportive in-app notifications with deduplication keys to prevent spam.
        """
        now_utc = datetime.now(UTC)

        # Fetch user profile to get timezone and name
        profile = await db.scalar(select(Profile).where(Profile.id == user_id))
        user_tz_str = profile.timezone if profile and profile.timezone else "Asia/Dhaka"
        user_name = profile.full_name.split()[0] if profile and profile.full_name else "there"

        # Query ScheduleBlocks that ended in the past 24 hours
        time_window_start = now_utc - timedelta(hours=24)
        query = (
            select(ScheduleBlock)
            .where(
                ScheduleBlock.user_id == user_id,
                ScheduleBlock.end_time < now_utc,
                ScheduleBlock.end_time >= time_window_start,
                ScheduleBlock.task_id.is_not(None),
            )
            .order_by(ScheduleBlock.end_time.desc())
        )
        res = await db.scalars(query)
        past_blocks = list(res.all())

        created_notifications: list[Notification] = []

        for block in past_blocks:
            task = await db.scalar(
                select(Task).where(Task.id == block.task_id, Task.user_id == user_id)
            )
            # Skip if task is completed, cancelled, or archived
            if not task or task.is_archived or task.status in ["completed", "cancelled"]:
                continue

            dedup_key = f"missed_session_{task.id}_{block.id}"

            # Check if notification already exists
            existing = await db.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.deduplication_key == dedup_key,
                )
            )
            if existing:
                continue

            title = f"Scheduled session ended: {task.title}"
            message = (
                f"{user_name.capitalize()}, your scheduled {block.title} session has ended, but the task is still incomplete. "
                f"Would you like to review it or plan another session?"
            )

            notif = Notification(
                user_id=user_id,
                task_id=task.id,
                notification_type="missed_session",
                channel="in_app",
                status="pending",
                title=title,
                message=message,
                scheduled_for=now_utc,
                deduplication_key=dedup_key,
                payload={
                    "block_id": str(block.id),
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "target_date": block.start_time.astimezone(UTC).date().isoformat(),
                    "timezone": user_tz_str,
                    "recovery_action": "reschedule_or_review",
                },
            )
            db.add(notif)
            created_notifications.append(notif)

        if created_notifications:
            await db.commit()
            logger.info(
                "Created missed session notifications",
                user_id=user_id,
                count=len(created_notifications),
            )

        return created_notifications

    @classmethod
    async def get_accountability_summary(
        cls, db: AsyncSession, user_id: uuid.UUID
    ) -> StudentAccountabilitySummary:
        """Calculate student consistency metrics, streak days, and recovery recommendations."""
        now_utc = datetime.now(UTC)

        # 1. Total and completed tasks
        completed_today_query = select(func.count(Task.id)).where(
            Task.user_id == user_id,
            Task.status == "completed",
            Task.is_archived.is_(False),
            Task.updated_at >= now_utc - timedelta(hours=24),
        )
        completed_today = await db.scalar(completed_today_query) or 0

        total_tasks_query = select(func.count(Task.id)).where(
            Task.user_id == user_id,
            Task.is_archived.is_(False),
            Task.status.notin_(["cancelled"]),
        )
        total_tasks = await db.scalar(total_tasks_query) or 0

        # 2. Missed sessions count (past blocks incomplete)
        missed_query = (
            select(func.count(ScheduleBlock.id))
            .join(Task, ScheduleBlock.task_id == Task.id)
            .where(
                ScheduleBlock.user_id == user_id,
                ScheduleBlock.end_time < now_utc,
                ScheduleBlock.end_time >= now_utc - timedelta(days=7),
                Task.status.notin_(["completed", "cancelled"]),
                Task.is_archived.is_(False),
            )
        )
        missed_count = await db.scalar(missed_query) or 0

        # 3. Find suggested recovery task
        recovery_query = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status.notin_(["completed", "cancelled"]),
                Task.is_archived.is_(False),
                Task.scheduled_start.is_(None),
            )
            .order_by(Task.priority.asc(), Task.deadline.asc().nullslast())
            .limit(1)
        )
        recovery_task = await db.scalar(recovery_query)
        suggested_task = (
            {
                "id": str(recovery_task.id),
                "title": recovery_task.title,
                "priority": recovery_task.priority,
                "duration_minutes": recovery_task.duration_minutes or 30,
            }
            if recovery_task
            else None
        )

        # 4. Streak calculation (days with completed tasks)
        streak_days = min(completed_today + 1 if completed_today > 0 else 1, 7)

        # 5. Encouraging supportive message
        if missed_count > 0:
            supportive_message = (
                f"You have {missed_count} incomplete scheduled session{'s' if missed_count != 1 else ''}. "
                f"Don't worry—progress isn't about perfection. Let's find time today to get back on track!"
            )
        elif completed_today > 0:
            supportive_message = (
                f"Great momentum! You've completed {completed_today} task{'s' if completed_today != 1 else ''} today. "
                f"Keep up the disciplined focus!"
            )
        else:
            supportive_message = (
                "Ready for today's learning? Take a look at your schedule and take things one focused session at a time."
            )

        return StudentAccountabilitySummary(
            missed_sessions_count=missed_count,
            completed_today_count=completed_today,
            total_tasks_count=total_tasks,
            streak_days=streak_days,
            supportive_message=supportive_message,
            suggested_recovery_task=suggested_task,
        )
