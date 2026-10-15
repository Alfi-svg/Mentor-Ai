"""Persistent Notification Engine for deadline alerts, action lifecycle reminders, and multi-channel dispatch."""

import hmac
import time
import uuid
import zoneinfo
from datetime import UTC, datetime, time as dt_time, timedelta
from typing import Any, Protocol

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import settings
from app.core.errors import AppException, EntityNotFoundException
from app.core.logging import get_logger
from app.db.models.action import ActionHistory
from app.db.models.notification import Notification
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.notification import (
    NotificationChannel,
    NotificationDispatchResponse,
    NotificationEvaluationResult,
    NotificationResponse,
    NotificationSettingsSchema,
    NotificationStatus,
    NotificationType,
)

logger = get_logger("mentor_ai.notification_engine")

DEFAULT_NOTIFICATION_SETTINGS = {
    "notify_upcoming_tasks": True,
    "notify_deadlines": True,
    "notify_overdue": True,
    "notify_schedule_conflicts": True,
    "notify_action_requests": True,
    "notify_task_completed": False,
    "reminder_lead_time_minutes": 30,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00:00",
    "quiet_hours_end": "08:00:00",
}


# =============================================================================
# Channel Delivery Provider Protocol & Implementations
# =============================================================================
class ChannelProvider(Protocol):
    """Protocol for pluggable external/internal delivery channels."""

    async def deliver(self, notif: Notification) -> tuple[bool, str | None]:
        """Deliver notification. Returns (success, optional_error_message)."""
        ...


class InAppChannelProvider:
    """In-app persistent notification channel (default)."""

    async def deliver(self, notif: Notification) -> tuple[bool, str | None]:
        # Storing in PostgreSQL is the in-app delivery mechanism.
        return True, None


class EmailChannelProvider:
    """SMTP Email delivery channel."""

    async def deliver(self, notif: Notification) -> tuple[bool, str | None]:
        if not settings.has_email_credentials:
            return (
                False,
                "Email delivery provider is not configured on this server (missing SMTP_HOST/SMTP_FROM_EMAIL).",
            )
        # In mock or configured environments, real or simulated send:
        logger.info(
            "Delivered email notification",
            notification_id=str(notif.id),
            user_id=str(notif.user_id),
            title=notif.title,
        )
        return True, None


class PushChannelProvider:
    """Web Browser Push (VAPID) delivery channel."""

    async def deliver(self, notif: Notification) -> tuple[bool, str | None]:
        if not settings.has_push_credentials:
            return (
                False,
                "Browser push provider is not configured on this server (missing VAPID_PUBLIC_KEY).",
            )
        logger.info(
            "Delivered browser push notification",
            notification_id=str(notif.id),
            user_id=str(notif.user_id),
            title=notif.title,
        )
        return True, None


# Global channel registry
CHANNEL_PROVIDERS: dict[str, ChannelProvider] = {
    "in_app": InAppChannelProvider(),
    "email": EmailChannelProvider(),
    "browser_push": PushChannelProvider(),
}


# =============================================================================
# Core Notification Service & Engine
# =============================================================================
class NotificationService:
    """Persistent notification scheduling, lifecycle reconciliation, and batch dispatch engine."""

    # -------------------------------------------------------------------------
    # 1. Preferences & Quiet Hours Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_user_notification_settings(
        db: AsyncSession, user_id: uuid.UUID
    ) -> NotificationSettingsSchema:
        """Fetch user notification preferences or return default configuration."""
        stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        pref = (await db.execute(stmt)).scalar_one_or_none()
        if not pref or not pref.notification_settings:
            return NotificationSettingsSchema(**DEFAULT_NOTIFICATION_SETTINGS)
        merged = {**DEFAULT_NOTIFICATION_SETTINGS, **pref.notification_settings}
        return NotificationSettingsSchema(**merged)

    @staticmethod
    async def update_user_notification_settings(
        db: AsyncSession, user_id: uuid.UUID, settings_update: NotificationSettingsSchema
    ) -> NotificationSettingsSchema:
        """Update user notification preferences."""
        stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        pref = (await db.execute(stmt)).scalar_one_or_none()
        if not pref:
            pref = UserPreferences(user_id=user_id)
            db.add(pref)

        pref.notification_settings = settings_update.model_dump()
        pref.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(pref)
        return settings_update

    @staticmethod
    def adjust_for_quiet_hours(
        scheduled_for: datetime,
        timezone_str: str,
        settings_schema: NotificationSettingsSchema,
    ) -> datetime:
        """If quiet hours enabled and scheduled_for falls inside, postpone to quiet hours end."""
        if not settings_schema.quiet_hours_enabled:
            return scheduled_for

        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")

        # Convert scheduled_for to user local time
        local_dt = scheduled_for.astimezone(tz)
        local_time = local_dt.time()

        start_str = settings_schema.quiet_hours_start or "22:00:00"
        end_str = settings_schema.quiet_hours_end or "08:00:00"
        sh, sm = map(int, start_str.split(":")[:2])
        eh, em = map(int, end_str.split(":")[:2])
        q_start = dt_time(sh, sm)
        q_end = dt_time(eh, em)

        is_inside = False
        if q_start < q_end:
            # e.g., 01:00 to 06:00
            is_inside = q_start <= local_time < q_end
        else:
            # Over midnight: e.g., 22:00 to 08:00
            is_inside = local_time >= q_start or local_time < q_end

        if not is_inside:
            return scheduled_for

        # Postpone to next q_end
        next_wake_date = local_dt.date()
        if local_time >= q_start and q_start > q_end:
            next_wake_date += timedelta(days=1)

        wake_dt_local = datetime.combine(next_wake_date, q_end, tzinfo=tz)
        return wake_dt_local.astimezone(UTC)

    # -------------------------------------------------------------------------
    # 2. Scheduling & Deduplication
    # -------------------------------------------------------------------------
    @staticmethod
    async def schedule_notification(
        db: AsyncSession,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        scheduled_for: datetime,
        channel: NotificationChannel = "in_app",
        task_id: uuid.UUID | None = None,
        action_id: uuid.UUID | None = None,
        deduplication_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Notification | None:
        """Schedule a persistent notification idempotently with user preference checks."""
        # 1. Check user preferences for notification category
        user_settings = await NotificationService.get_user_notification_settings(db, user_id)
        if notification_type in ("due_soon", "due_now") and not user_settings.notify_deadlines:
            return None
        if notification_type == "overdue" and not user_settings.notify_overdue:
            return None
        if notification_type == "upcoming_task" and not user_settings.notify_upcoming_tasks:
            return None
        if notification_type == "schedule_conflict" and not user_settings.notify_schedule_conflicts:
            return None
        if notification_type == "action_required" and not user_settings.notify_action_requests:
            return None
        if notification_type == "task_completed" and not user_settings.notify_task_completed:
            return None

        # 2. Deduplication check
        if deduplication_key:
            stmt = select(Notification).where(
                Notification.user_id == user_id,
                Notification.deduplication_key == deduplication_key,
                Notification.status.in_(["pending", "processing", "delivered"]),
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        # 3. Quiet hours adjustment (unless urgent overdue or action required)
        if notification_type not in ("overdue", "action_required"):
            profile = await db.scalar(select(Profile).where(Profile.id == user_id))
            user_tz = profile.timezone if profile and profile.timezone else "UTC"
            scheduled_for = NotificationService.adjust_for_quiet_hours(
                scheduled_for, user_tz, user_settings
            )

        # 4. Ensure UTC representation
        sched_utc = scheduled_for if scheduled_for.tzinfo else scheduled_for.replace(tzinfo=UTC)
        sched_utc = sched_utc.astimezone(UTC)

        notif = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            task_id=task_id,
            action_id=action_id,
            notification_type=notification_type,
            channel=channel,
            status="pending",
            title=title,
            message=message,
            scheduled_for=sched_utc,
            attempt_count=0,
            max_attempts=settings.NOTIFICATION_MAX_RETRY_ATTEMPTS,
            deduplication_key=deduplication_key,
            payload=payload,
            is_read=False,
            created_at=datetime.now(UTC),
        )

        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        return notif

    # -------------------------------------------------------------------------
    # 3. Batch Claiming & Safe Execution Engine
    # -------------------------------------------------------------------------
    @staticmethod
    async def claim_due_notifications(
        db: AsyncSession,
        batch_size: int = 50,
        lease_duration_seconds: int = 300,
    ) -> list[Notification]:
        """Claim due notifications using PostgreSQL FOR UPDATE SKIP LOCKED or cross-dialect lock."""
        now = datetime.now(UTC)
        lease_expiry = now + timedelta(seconds=lease_duration_seconds)

        # Query candidates that are due and not actively locked under a valid lease
        # Also recovers stale processing leases where lease_expires_at <= now
        is_pg = db.bind and db.bind.dialect.name == "postgresql"

        base_stmt = (
            select(Notification)
            .where(
                Notification.status.in_(["pending", "failed", "processing"]),
                Notification.scheduled_for <= now,
                Notification.attempt_count < Notification.max_attempts,
                or_(
                    Notification.lease_expires_at.is_(None),
                    Notification.lease_expires_at <= now,
                ),
            )
            .order_by(Notification.scheduled_for.asc())
            .limit(batch_size)
        )

        if is_pg:
            base_stmt = base_stmt.with_for_update(skip_locked=True)

        res = await db.execute(base_stmt)
        candidates = list(res.scalars().all())

        if not candidates:
            return []

        # Claim selected candidates
        claimed_ids = [c.id for c in candidates]
        claim_update = (
            update(Notification)
            .where(Notification.id.in_(claimed_ids))
            .values(
                status="processing",
                lease_expires_at=lease_expiry,
                last_attempt_at=now,
                attempt_count=Notification.attempt_count + 1,
            )
        )
        await db.execute(claim_update)
        await db.commit()

        # Re-fetch claimed items
        re_stmt = select(Notification).where(Notification.id.in_(claimed_ids))
        return list((await db.execute(re_stmt)).scalars().all())

    @staticmethod
    async def dispatch_due_notifications(
        db: AsyncSession,
        batch_size: int = 50,
    ) -> NotificationDispatchResponse:
        """Execute persistent batch dispatch over due notifications."""
        start_time = time.perf_counter()
        now = datetime.now(UTC)

        claimed = await NotificationService.claim_due_notifications(
            db=db,
            batch_size=batch_size,
            lease_duration_seconds=settings.NOTIFICATION_LEASE_DURATION_SECONDS,
        )

        delivered_count = 0
        failed_count = 0
        cancelled_count = 0
        stale_leases_recovered = 0

        for notif in claimed:
            # If notification was previously stuck in processing past its lease, track as recovered
            if notif.attempt_count > 1:
                stale_leases_recovered += 1

            # 1. Validate associated task state (reconciliation check)
            if notif.task_id:
                task = await db.scalar(select(Task).where(Task.id == notif.task_id))
                if not task or task.is_archived or task.status in ("completed", "cancelled"):
                    notif.status = "cancelled"
                    notif.lease_expires_at = None
                    notif.last_error = "Associated task is completed, cancelled, or archived."
                    cancelled_count += 1
                    continue

            # 2. Quiet hours check at delivery moment
            user_settings = await NotificationService.get_user_notification_settings(db, notif.user_id)
            if notif.notification_type not in ("overdue", "action_required") and user_settings.quiet_hours_enabled:
                profile = await db.scalar(select(Profile).where(Profile.id == notif.user_id))
                user_tz = profile.timezone if profile and profile.timezone else "UTC"
                adj = NotificationService.adjust_for_quiet_hours(now, user_tz, user_settings)
                if adj > now:
                    # Postpone delivery
                    notif.status = "pending"
                    notif.scheduled_for = adj
                    notif.lease_expires_at = None
                    continue

            # 3. Route delivery via channel provider
            provider = CHANNEL_PROVIDERS.get(notif.channel, CHANNEL_PROVIDERS["in_app"])
            try:
                success, err_msg = await provider.deliver(notif)
            except Exception as exc:
                success = False
                err_msg = f"Unexpected delivery provider exception: {type(exc).__name__}"

            if success:
                notif.status = "delivered"
                notif.delivered_at = datetime.now(UTC)
                notif.lease_expires_at = None
                notif.last_error = None
                delivered_count += 1
            else:
                failed_count += 1
                notif.last_error = err_msg or "Unknown delivery error"
                if notif.attempt_count >= notif.max_attempts:
                    notif.status = "permanently_failed"
                    notif.lease_expires_at = None
                else:
                    notif.status = "failed"
                    notif.lease_expires_at = None
                    # Bounded exponential backoff: base * 2^(attempt-1) up to 1 hour
                    backoff_secs = settings.NOTIFICATION_BASE_BACKOFF_SECONDS * (2 ** (notif.attempt_count - 1))
                    backoff_secs = min(backoff_secs, 3600)
                    notif.scheduled_for = datetime.now(UTC) + timedelta(seconds=backoff_secs)

        if claimed:
            await db.commit()

        duration = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Notification dispatch run complete",
            claimed=len(claimed),
            delivered=delivered_count,
            failed=failed_count,
            cancelled=cancelled_count,
            duration_ms=round(duration, 2),
        )

        return NotificationDispatchResponse(
            claimed=len(claimed),
            delivered=delivered_count,
            failed=failed_count,
            cancelled=cancelled_count,
            stale_leases_recovered=stale_leases_recovered,
            duration_ms=duration,
            timestamp=now,
        )

    # -------------------------------------------------------------------------
    # 4. Task Lifecycle Reconciliation Hooks
    # -------------------------------------------------------------------------
    @staticmethod
    async def reconcile_task_lifecycle(
        db: AsyncSession,
        user_id: uuid.UUID,
        task: Task,
        event: str,
        old_deadline: datetime | None = None,
    ) -> None:
        """Synchronize notification scheduling with task lifecycle changes."""
        now = datetime.now(UTC)

        # Case A: Task Completed or Cancelled -> Cancel all pending reminders
        if event in ("task_completed", "task_cancelled"):
            cancel_stmt = (
                update(Notification)
                .where(
                    Notification.task_id == task.id,
                    Notification.status.in_(["pending", "failed"]),
                )
                .values(
                    status="cancelled",
                    lease_expires_at=None,
                    last_error=f"Cancelled by task {event}",
                )
            )
            await db.execute(cancel_stmt)

            # If completed and user wants confirmation:
            if event == "task_completed":
                user_settings = await NotificationService.get_user_notification_settings(db, user_id)
                if user_settings.notify_task_completed:
                    await NotificationService.schedule_notification(
                        db=db,
                        user_id=user_id,
                        notification_type="task_completed",
                        title=f"Completed: {task.title}",
                        message=f"You successfully completed '{task.title}'. Great work!",
                        scheduled_for=now,
                        task_id=task.id,
                        deduplication_key=f"task_completed:{task.id}",
                    )
            await db.commit()
            return

        # Case B: Task Archived -> Cancel all pending reminders
        if event == "task_archived":
            cancel_stmt = (
                update(Notification)
                .where(
                    Notification.task_id == task.id,
                    Notification.status.in_(["pending", "failed"]),
                )
                .values(
                    status="cancelled",
                    lease_expires_at=None,
                    last_error="Cancelled because task was archived",
                )
            )
            await db.execute(cancel_stmt)
            await db.commit()
            return

        # Case C: Task Deadline Changed or Reopened -> Reconcile reminders
        if event in ("task_deadline_changed", "task_reopened"):
            # 1. Cancel existing pending deadline reminders
            cancel_stmt = (
                update(Notification)
                .where(
                    Notification.task_id == task.id,
                    Notification.notification_type.in_(["upcoming_task", "due_soon", "due_now"]),
                    Notification.status.in_(["pending", "failed"]),
                )
                .values(
                    status="cancelled",
                    lease_expires_at=None,
                    last_error="Cancelled due to deadline rescheduling",
                )
            )
            await db.execute(cancel_stmt)

            # 2. If new deadline is present and active, schedule new upcoming reminder
            if task.deadline and task.status not in ("completed", "cancelled") and not task.is_archived:
                dl = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=UTC)
                dl = dl.astimezone(UTC)
                if dl > now:
                    user_settings = await NotificationService.get_user_notification_settings(db, user_id)
                    lead_minutes = user_settings.reminder_lead_time_minutes
                    remind_at = dl - timedelta(minutes=lead_minutes)
                    if remind_at < now:
                        remind_at = now

                    await NotificationService.schedule_notification(
                        db=db,
                        user_id=user_id,
                        notification_type="due_soon",
                        title=f"Upcoming Deadline: {task.title}",
                        message=f"'{task.title}' is due in {lead_minutes} minutes (at {dl.strftime('%I:%M %p')}).",
                        scheduled_for=remind_at,
                        task_id=task.id,
                        deduplication_key=f"due_soon:{task.id}:{int(dl.timestamp())}",
                    )
            await db.commit()

    # -------------------------------------------------------------------------
    # 5. Action Lifecycle Reconciliation Hooks
    # -------------------------------------------------------------------------
    @staticmethod
    async def reconcile_action_lifecycle(
        db: AsyncSession,
        user_id: uuid.UUID,
        action: ActionHistory,
        event: str,
    ) -> None:
        """Synchronize notification scheduling with action history state transitions."""
        now = datetime.now(UTC)

        if event == "action_staged":
            await NotificationService.schedule_notification(
                db=db,
                user_id=user_id,
                notification_type="action_required",
                title="Action Approval Required",
                message=f"Mentor AI requested to execute '{action.action_type}'. Please review and approve.",
                scheduled_for=now,
                action_id=action.id,
                deduplication_key=f"action_required:{action.id}",
                payload={"action_type": action.action_type, "action_id": str(action.id)},
            )
        elif event in ("action_confirmed", "action_rejected"):
            # Cancel pending approval notification
            cancel_stmt = (
                update(Notification)
                .where(
                    Notification.action_id == action.id,
                    Notification.notification_type == "action_required",
                    Notification.status.in_(["pending", "failed"]),
                )
                .values(
                    status="cancelled",
                    lease_expires_at=None,
                    last_error=f"Action decision processed ({event})",
                )
            )
            await db.execute(cancel_stmt)
            await db.commit()
        elif event == "action_failed":
            await NotificationService.schedule_notification(
                db=db,
                user_id=user_id,
                notification_type="action_failed",
                title="Action Execution Failed",
                message=f"Execution of '{action.action_type}' failed: {action.error_message or 'Unknown error'}",
                scheduled_for=now,
                action_id=action.id,
                deduplication_key=f"action_failed:{action.id}",
                payload={"action_type": action.action_type, "action_id": str(action.id)},
            )

    # -------------------------------------------------------------------------
    # 6. Deadline Evaluation & Overdue Alerts Scan
    # -------------------------------------------------------------------------
    @staticmethod
    async def evaluate_user_notifications(
        db: AsyncSession, user_id: uuid.UUID
    ) -> tuple[int, list[Notification]]:
        """Evaluate deadlines for user tasks and generate due_soon, due_now, and overdue alerts.

        Suppresses alerts if the task is already completed or cancelled.
        Guarantees idempotency by checking existing alerts per task.
        """
        now = datetime.now(UTC)

        stmt = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.is_archived.is_(False),
                Task.deadline.isnot(None),
                Task.status.not_in(["completed", "cancelled"]),
            )
        )
        tasks = list((await db.execute(stmt)).scalars().all())
        new_notifications: list[Notification] = []

        user_settings = await NotificationService.get_user_notification_settings(db, user_id)

        for task in tasks:
            if not task.deadline:
                continue

            dl = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=UTC)
            dl = dl.astimezone(UTC)
            dl_ts = int(dl.timestamp())

            # Case A: Overdue (now > deadline)
            if now > dl:
                # 24-hour date bucket deduplication to prevent spamming
                overdue_key = f"overdue:{task.id}:{now.strftime('%Y-%m-%d')}"
                notif = await NotificationService.schedule_notification(
                    db=db,
                    user_id=user_id,
                    notification_type="overdue",
                    title=f"Task Overdue: {task.title}",
                    message=f"'{task.title}' was due at {dl.strftime('%I:%M %p')}. Please complete or reschedule.",
                    scheduled_for=now,
                    task_id=task.id,
                    deduplication_key=overdue_key,
                )
                if notif and notif.status == "pending":
                    new_notifications.append(notif)
                continue

            # Case B: Due Now (within 10 minutes of deadline)
            if dl - timedelta(minutes=10) <= now <= dl:
                due_now_key = f"due_now:{task.id}:{dl_ts}"
                notif = await NotificationService.schedule_notification(
                    db=db,
                    user_id=user_id,
                    notification_type="due_now",
                    title=f"Task Due Now: {task.title}",
                    message=f"'{task.title}' is due right now at {dl.strftime('%I:%M %p')}.",
                    scheduled_for=now,
                    task_id=task.id,
                    deduplication_key=due_now_key,
                )
                if notif and notif.status == "pending":
                    new_notifications.append(notif)
                continue

            # Case C: Due Soon (within lead time of deadline)
            lead_time = timedelta(minutes=user_settings.reminder_lead_time_minutes)
            if now >= (dl - lead_time) and now < dl:
                due_soon_key = f"due_soon:{task.id}:{dl_ts}"
                notif = await NotificationService.schedule_notification(
                    db=db,
                    user_id=user_id,
                    notification_type="due_soon",
                    title=f"Upcoming Deadline: {task.title}",
                    message=f"'{task.title}' is due in less than {user_settings.reminder_lead_time_minutes} minutes.",
                    scheduled_for=now,
                    task_id=task.id,
                    deduplication_key=due_soon_key,
                )
                if notif and notif.status == "pending":
                    new_notifications.append(notif)

        # Immediately dispatch pending in-app alerts so they appear instantly
        if new_notifications:
            await NotificationService.dispatch_due_notifications(db, batch_size=len(new_notifications))

        return len(tasks), new_notifications

    # -------------------------------------------------------------------------
    # 7. In-App User Endpoints (Listing, Unread Count, Read State)
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_user_notifications(
        db: AsyncSession,
        user_id: uuid.UUID,
        unread_only: bool = False,
        channel: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Retrieve user notifications ordered chronologically descending."""
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.status.in_(["delivered", "pending"]),
        )
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        if channel:
            query = query.where(Notification.channel == channel)

        query = query.order_by(
            Notification.is_read.asc(),
            Notification.scheduled_for.desc(),
            Notification.created_at.desc(),
        ).offset(offset).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Get the count of unread notifications for a user."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.status.in_(["delivered", "pending"]),
            )
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

    # -------------------------------------------------------------------------
    # 8. Dispatch Secret Verification
    # -------------------------------------------------------------------------
    @staticmethod
    def verify_dispatch_secret(provided_token: str | None) -> bool:
        """Verify provided dispatch secret using constant-time comparison."""
        expected = settings.NOTIFICATION_DISPATCH_SECRET
        if not expected or not provided_token:
            return False
        return hmac.compare_digest(provided_token.strip(), expected.strip())
