"""Automatic Task-to-Calendar synchronization engine and bidirectional reconciliation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.profile import UserPreferences
from app.db.models.task import Task
from app.services.calendar.base import CalendarProviderException
from app.services.calendar.models import (
    CalendarEventCreate,
    CalendarEventUpdate,
)
from app.services.calendar.service import CalendarService
from app.services.notification_service import NotificationService

logger = get_logger("mentor_ai.calendar_sync")


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class CalendarSyncService:
    """Manages bidirectional task scheduling synchronization with Google Calendar."""

    @classmethod
    async def is_sync_enabled_for_user(
        cls, db: AsyncSession, user_id: uuid.UUID
    ) -> tuple[bool, ExternalConnection | None]:
        """Check if user has Google Calendar connected and auto-sync enabled."""
        pref_stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        pref_res = await db.execute(pref_stmt)
        pref = pref_res.scalar_one_or_none()
        if pref and not getattr(pref, "calendar_auto_sync", True):
            return False, None

        conn_stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_calendar",
            ExternalConnection.status == "connected",
        )
        conn_res = await db.execute(conn_stmt)
        conn = conn_res.scalar_one_or_none()
        if not conn:
            return False, None

        return True, conn

    @classmethod
    async def sync_task_to_calendar(
        cls, db: AsyncSession, task: Task, user_id: uuid.UUID
    ) -> bool:
        """Idempotently create or update Google Calendar event for a scheduled task."""
        is_enabled, conn = await cls.is_sync_enabled_for_user(db, user_id)
        if not is_enabled or not conn:
            # Calendar not connected or sync disabled
            if task.calendar_sync_status != "unsynced" and not task.google_calendar_event_id:
                task.calendar_sync_status = "unsynced"
                await db.commit()
            return False

        # If task is archived or cancelled, remove remote calendar event if it exists
        if task.is_archived or task.status == "cancelled":
            if task.google_calendar_event_id:
                ext_id = task.google_calendar_event_id
                try:
                    access_token = await CalendarService.get_valid_access_token(conn, db)
                    provider = CalendarService.get_provider()
                    await provider.delete_event(access_token, ext_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to delete cancelled/archived task event from Google Calendar",
                        task_id=str(task.id),
                        external_id=ext_id,
                        error=str(exc),
                    )

                # Delete matching local CalendarEvent cache if present
                local_ev_stmt = select(CalendarEvent).where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.external_id == ext_id,
                )
                local_res = await db.execute(local_ev_stmt)
                local_ev = local_res.scalar_one_or_none()
                if local_ev:
                    await db.delete(local_ev)

                task.google_calendar_event_id = None
                task.calendar_sync_status = "synced"
                task.calendar_sync_error = None
                task.last_synced_at = datetime.now(UTC)
                await db.commit()
                return True
            return False

        # If task is not scheduled with start/end time, it shouldn't have an active calendar event
        if not task.scheduled_start or not task.scheduled_end:
            if task.google_calendar_event_id:
                ext_id = task.google_calendar_event_id
                try:
                    access_token = await CalendarService.get_valid_access_token(conn, db)
                    provider = CalendarService.get_provider()
                    await provider.delete_event(access_token, ext_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove unscheduled task event from Google Calendar",
                        task_id=str(task.id),
                        external_id=ext_id,
                        error=str(exc),
                    )

                local_ev_stmt = select(CalendarEvent).where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.external_id == ext_id,
                )
                local_res = await db.execute(local_ev_stmt)
                local_ev = local_res.scalar_one_or_none()
                if local_ev:
                    await db.delete(local_ev)

                task.google_calendar_event_id = None
                task.calendar_sync_status = "unsynced"
                task.calendar_sync_error = None
                await db.commit()
            return False

        # Task has designated scheduled slot!
        summary = f"[DONE] {task.title}" if task.status == "completed" else task.title
        desc_lines = [
            "Mentor AI Scheduled Task",
            f"Priority: {task.priority}",
            f"Status: {task.status}",
            f"Duration: {task.duration_minutes} min",
            f"Task ID: {task.id}",
        ]
        if task.description:
            desc_lines.append("")
            desc_lines.append(task.description)
        event_description = "\n".join(desc_lines)

        try:
            access_token = await CalendarService.get_valid_access_token(conn, db)
            provider = CalendarService.get_provider()

            if task.google_calendar_event_id:
                # Update existing event
                update_payload = CalendarEventUpdate(
                    title=summary,
                    description=event_description,
                    start_time=task.scheduled_start,
                    end_time=task.scheduled_end,
                )
                try:
                    remote_event = await provider.update_event(
                        access_token, task.google_calendar_event_id, update_payload
                    )
                except CalendarProviderException as cpe:
                    if getattr(cpe, "status_code", None) == 404:
                        # Remote event was deleted out-of-band; recreate
                        create_payload = CalendarEventCreate(
                            title=summary,
                            description=event_description,
                            start_time=task.scheduled_start,
                            end_time=task.scheduled_end,
                        )
                        remote_event = await provider.create_event(access_token, create_payload)
                        task.google_calendar_event_id = remote_event.external_id
                    else:
                        raise
            else:
                # Create new event on Google Calendar
                create_payload = CalendarEventCreate(
                    title=summary,
                    description=event_description,
                    start_time=task.scheduled_start,
                    end_time=task.scheduled_end,
                )
                remote_event = await provider.create_event(access_token, create_payload)
                task.google_calendar_event_id = remote_event.external_id

            # Update or create corresponding local CalendarEvent cache entry
            local_ev_stmt = select(CalendarEvent).where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.external_id == task.google_calendar_event_id,
            )
            local_res = await db.execute(local_ev_stmt)
            local_ev = local_res.scalar_one_or_none()
            if not local_ev:
                local_ev = CalendarEvent(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    title=summary,
                    description=event_description,
                    start_time=task.scheduled_start,
                    end_time=task.scheduled_end,
                    is_all_day=False,
                    is_fixed=True,
                    source="google_calendar",
                    external_id=task.google_calendar_event_id,
                    created_at=datetime.now(UTC),
                )
                db.add(local_ev)
            else:
                local_ev.title = summary
                local_ev.description = event_description
                local_ev.start_time = task.scheduled_start
                local_ev.end_time = task.scheduled_end

            task.calendar_sync_status = "synced"
            task.calendar_sync_error = None
            task.last_synced_at = datetime.now(UTC)
            await db.commit()

            logger.info(
                "Task synced to Google Calendar successfully",
                task_id=str(task.id),
                user_id=str(user_id),
                google_event_id=task.google_calendar_event_id,
            )
            return True

        except CalendarProviderException as exc:
            if exc.status_code == 403 or "insufficient" in str(exc).lower():
                meta = dict(conn.metadata_json or {})
                meta["scope_insufficient"] = True
                conn.metadata_json = meta
                conn.scopes = [s for s in (conn.scopes or []) if "calendar" not in s]
            logger.error(
                "Failed to sync task to Google Calendar",
                task_id=str(task.id),
                user_id=str(user_id),
                error=str(exc),
            )
            task.calendar_sync_status = "failed"
            task.calendar_sync_error = (
                "Google Calendar permission missing. Please reconnect Google Calendar."
                if (exc.status_code == 403 or "insufficient" in str(exc).lower())
                else str(exc)
            )
            await db.commit()
            return False
        except Exception as exc:
            logger.error(
                "Failed to sync task to Google Calendar",
                task_id=str(task.id),
                user_id=str(user_id),
                error=str(exc),
            )
            task.calendar_sync_status = "failed"
            task.calendar_sync_error = str(exc)
            await db.commit()
            return False

    @classmethod
    async def reconcile_event_to_task(
        cls,
        db: AsyncSession,
        external_id: str,
        user_id: uuid.UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> Task | None:
        """Update task scheduled times when its associated calendar event is moved."""
        stmt = select(Task).where(
            Task.user_id == user_id,
            Task.google_calendar_event_id == external_id,
        )
        res = await db.execute(stmt)
        task = res.scalar_one_or_none()
        if not task:
            return None

        task.scheduled_start = _ensure_utc(start_time)
        task.scheduled_end = _ensure_utc(end_time)
        diff_mins = int((end_time - start_time).total_seconds() / 60)
        if diff_mins > 0:
            task.duration_minutes = diff_mins
        task.last_synced_at = datetime.now(UTC)
        task.calendar_sync_status = "synced"
        await db.commit()
        await db.refresh(task)

        # Reconcile reminders and deadlines
        await NotificationService.reconcile_task_lifecycle(
            db=db, user_id=user_id, task=task, event="task_deadline_changed"
        )

        logger.info(
            "Reconciled calendar event movement back to task",
            task_id=str(task.id),
            external_id=external_id,
            new_start=task.scheduled_start.isoformat(),
        )
        return task

    @classmethod
    async def sync_pending_tasks(
        cls, db: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, Any]:
        """Retry synchronization for all pending or failed scheduled tasks."""
        stmt = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.is_archived.is_(False),
                Task.scheduled_start.isnot(None),
                Task.calendar_sync_status.in_(["pending", "failed", "unsynced"]),
            )
            .order_by(Task.scheduled_start.asc())
        )
        res = await db.execute(stmt)
        tasks = list(res.scalars().all())

        synced_count = 0
        failed_count = 0
        errors: list[str] = []

        for task in tasks:
            success = await cls.sync_task_to_calendar(db, task, user_id)
            if success:
                synced_count += 1
            else:
                failed_count += 1
                if task.calendar_sync_error:
                    errors.append(f"{task.title}: {task.calendar_sync_error}")

        return {
            "total_attempted": len(tasks),
            "synced": synced_count,
            "failed": failed_count,
            "errors": errors[:5],
        }
