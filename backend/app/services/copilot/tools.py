"""Deterministic schedule intelligence tools for Mentor AI Copilot."""

import uuid
import zoneinfo
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.calendar import CalendarEvent
from app.db.models.profile import Profile
from app.db.models.schedule import ScheduleBlock
from app.db.models.task import Task
from app.schemas.copilot import (
    CopilotScheduleItem,
    CopilotScheduleSummary,
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Guarantee datetime is timezone-aware in UTC, handling SQLite naive returns."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_time_display(dt: datetime, tz: zoneinfo.ZoneInfo) -> str:
    """Format UTC datetime into user timezone display, e.g. 09:30 AM."""
    dt_utc = _ensure_utc(dt)
    if dt_utc is None:
        return ""
    dt_loc = dt_utc.astimezone(tz)
    return dt_loc.strftime("%I:%M %p").lstrip("0")


async def resolve_user_timezone(db: AsyncSession, user_id: uuid.UUID, default_tz: str = "Asia/Dhaka") -> str:
    """Fetch user profile configured timezone or fall back to default."""
    profile = await db.scalar(select(Profile).where(Profile.id == user_id))
    if profile and profile.timezone:
        return profile.timezone
    return default_tz


async def get_today_schedule(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> CopilotScheduleSummary:
    """Retrieve today's complete schedule in user timezone."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")
        user_tz_str = "Asia/Dhaka"

    now_utc = datetime.now(UTC)
    now_loc = now_utc.astimezone(tz)
    today = now_loc.date()

    return await get_schedule_for_date(db, user_id, today.isoformat(), user_tz_str)


async def get_schedule_for_date(
    db: AsyncSession, user_id: uuid.UUID, target_date_str: str, user_tz_str: str = "Asia/Dhaka"
) -> CopilotScheduleSummary:
    """Retrieve complete schedule for a specific date in user timezone."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")
        user_tz_str = "Asia/Dhaka"

    target_date = date.fromisoformat(target_date_str)
    start_of_day_loc = datetime.combine(target_date, time(0, 0, 0), tzinfo=tz)
    end_of_day_loc = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)

    start_of_day_utc = start_of_day_loc.astimezone(UTC)
    end_of_day_utc = end_of_day_loc.astimezone(UTC)
    now_utc = datetime.now(UTC)

    # 1. Fetch ScheduleBlocks for this day
    blocks_query = (
        select(ScheduleBlock)
        .where(
            ScheduleBlock.user_id == user_id,
            ScheduleBlock.start_time >= start_of_day_utc,
            ScheduleBlock.start_time <= end_of_day_utc,
        )
        .order_by(ScheduleBlock.start_time.asc())
    )
    blocks_res = await db.scalars(blocks_query)
    blocks = list(blocks_res.all())

    # Load associated tasks
    task_ids = [b.task_id for b in blocks if b.task_id]
    tasks_map: dict[uuid.UUID, Task] = {}
    if task_ids:
        tasks_res = await db.scalars(
            select(Task).where(Task.id.in_(task_ids), Task.user_id == user_id)
        )
        for t in tasks_res.all():
            tasks_map[t.id] = t

    # 2. Fetch CalendarEvents for this day
    events_query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_time >= start_of_day_utc,
            CalendarEvent.start_time <= end_of_day_utc,
        )
        .order_by(CalendarEvent.start_time.asc())
    )
    events_res = await db.scalars(events_query)
    events = list(events_res.all())

    # 3. Assemble Chronological Scheduled Items
    scheduled_items: list[CopilotScheduleItem] = []

    for b in blocks:
        task = tasks_map.get(b.task_id) if b.task_id else None
        # Skip archived or cancelled tasks
        if task and (task.is_archived or task.status == "cancelled"):
            continue

        is_completed = (task.status == "completed") if task else False
        task_dl = _ensure_utc(task.deadline) if task else None
        is_overdue = (
            (task_dl is not None and task_dl < now_utc and not is_completed)
            if task
            else False
        )
        sync_status = task.calendar_sync_status if task else None
        priority = task.priority if task else None

        scheduled_items.append(
            CopilotScheduleItem(
                id=str(b.id),
                title=b.title,
                item_type="task",
                start_time=_format_time_display(b.start_time, tz),
                end_time=_format_time_display(b.end_time, tz),
                raw_start=b.start_time,
                raw_end=b.end_time,
                status=task.status if task else "scheduled",
                is_completed=is_completed,
                is_overdue=is_overdue,
                priority=priority,
                task_id=task.id if task else None,
                sync_status=sync_status,
            )
        )

    for ev in events:
        scheduled_items.append(
            CopilotScheduleItem(
                id=str(ev.id),
                title=ev.title,
                item_type="calendar_event",
                start_time=_format_time_display(ev.start_time, tz),
                end_time=_format_time_display(ev.end_time, tz),
                raw_start=ev.start_time,
                raw_end=ev.end_time,
                status="confirmed",
                is_completed=False,
                is_overdue=False,
                event_id=ev.id,
            )
        )

    # Sort all scheduled items strictly chronologically by start time
    scheduled_items.sort(key=lambda item: item.raw_start)

    # 4. Fetch Unscheduled Tasks & Deadlines for target date
    deadlines_query = select(Task).where(
        Task.user_id == user_id,
        Task.is_archived.is_(False),
        Task.status.notin_(["completed", "cancelled"]),
        Task.deadline >= start_of_day_utc,
        Task.deadline <= end_of_day_utc,
    )
    deadlines_res = await db.scalars(deadlines_query)
    deadline_tasks = list(deadlines_res.all())

    deadlines: list[dict[str, Any]] = []
    for dt_task in deadline_tasks:
        deadlines.append(
            {
                "id": str(dt_task.id),
                "title": dt_task.title,
                "deadline_time": _format_time_display(dt_task.deadline, tz)
                if dt_task.deadline
                else None,
                "priority": dt_task.priority,
                "status": dt_task.status,
            }
        )

    # Fetch unscheduled tasks that have no start time
    unscheduled_query = select(Task).where(
        Task.user_id == user_id,
        Task.is_archived.is_(False),
        Task.status.notin_(["completed", "cancelled"]),
        Task.scheduled_start.is_(None),
    ).limit(5)
    unscheduled_res = await db.scalars(unscheduled_query)
    unscheduled_tasks = [
        {
            "id": str(t.id),
            "title": t.title,
            "duration_minutes": t.duration_minutes,
            "priority": t.priority,
            "deadline": _format_time_display(t.deadline, tz) if t.deadline else None,
        }
        for t in unscheduled_res.all()
    ]

    # 5. Determine Next Action
    next_action: str | None = None
    next_action_time: str | None = None
    for item in scheduled_items:
        raw_e = _ensure_utc(item.raw_end)
        if raw_e and raw_e > now_utc and not item.is_completed:
            next_action = item.title
            next_action_time = item.start_time
            break

    if not next_action and deadlines:
        next_action = f"Complete {deadlines[0]['title']} before deadline"
        next_action_time = deadlines[0].get("deadline_time")

    # 6. Build Human-Readable Natural Summary Text
    date_label = "Today" if target_date == now_utc.astimezone(tz).date() else target_date.strftime("%A, %b %d")
    total_count = len(scheduled_items)

    lines = []
    if total_count > 0 or deadlines:
        items_part = f"{total_count} scheduled item{'s' if total_count != 1 else ''}"
        deadlines_part = f"{len(deadlines)} deadline{'s' if len(deadlines) != 1 else ''}"
        if total_count > 0 and deadlines:
            lines.append(f"{date_label} you have {items_part} and {deadlines_part}:")
        elif total_count > 0:
            lines.append(f"{date_label} you have {items_part}:")
        else:
            lines.append(f"{date_label} you have {deadlines_part}:")

        for item in scheduled_items:
            prefix = "[Completed] " if item.is_completed else ""
            lines.append(f"• {item.start_time} — {prefix}{item.title} ({item.item_type.replace('_', ' ').capitalize()})")

        for dl in deadlines:
            lines.append(f"• Due at {dl.get('deadline_time', 'end of day')} — {dl['title']} (Deadline)")

        if next_action:
            lines.append(f"\nYour next scheduled focus is **{next_action}**{f' at {next_action_time}' if next_action_time else ''}.")
    else:
        lines.append(f"You have no scheduled tasks or calendar events for {date_label}.")
        if unscheduled_tasks:
            lines.append(f"However, you have {len(unscheduled_tasks)} unscheduled task(s) in your backlog ready to be planned.")

    summary_text = "\n".join(lines)

    return CopilotScheduleSummary(
        target_date=target_date_str,
        timezone=user_tz_str,
        total_items=len(scheduled_items),
        scheduled_items=scheduled_items,
        unscheduled_tasks=unscheduled_tasks,
        deadlines=deadlines,
        next_action=next_action,
        next_action_time=next_action_time,
        summary_text=summary_text,
    )


async def get_upcoming_deadlines(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka", days: int = 7
) -> list[dict[str, Any]]:
    """Retrieve upcoming deadlines within the next N days."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")

    now_utc = datetime.now(UTC)
    end_horizon = now_utc + timedelta(days=days)

    query = (
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.is_archived.is_(False),
            Task.status.notin_(["completed", "cancelled"]),
            Task.deadline.is_not(None),
            Task.deadline >= now_utc,
            Task.deadline <= end_horizon,
        )
        .order_by(Task.deadline.asc())
    )
    res = await db.scalars(query)
    tasks = res.all()

    return [
        {
            "id": str(t.id),
            "title": t.title,
            "deadline": _format_time_display(t.deadline, tz) if t.deadline else None,
            "deadline_raw": t.deadline.isoformat() if t.deadline else None,
            "priority": t.priority,
            "status": t.status,
            "duration_minutes": t.duration_minutes,
        }
        for t in tasks
    ]


async def get_overdue_tasks(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> list[dict[str, Any]]:
    """Retrieve incomplete tasks whose deadline has already elapsed."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")

    now_utc = datetime.now(UTC)

    query = (
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.is_archived.is_(False),
            Task.status.notin_(["completed", "cancelled"]),
            Task.deadline.is_not(None),
            Task.deadline < now_utc,
        )
        .order_by(Task.deadline.asc())
    )
    res = await db.scalars(query)
    tasks = res.all()

    return [
        {
            "id": str(t.id),
            "title": t.title,
            "deadline": _format_time_display(t.deadline, tz) if t.deadline else None,
            "deadline_raw": t.deadline.isoformat() if t.deadline else None,
            "priority": t.priority,
            "status": t.status,
            "duration_minutes": t.duration_minutes,
        }
        for t in tasks
    ]


async def get_completed_tasks(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Retrieve recently completed tasks for progress review."""
    query = (
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == "completed",
            Task.is_archived.is_(False),
        )
        .order_by(Task.updated_at.desc())
        .limit(limit)
    )
    res = await db.scalars(query)
    tasks = res.all()

    return [
        {
            "id": str(t.id),
            "title": t.title,
            "priority": t.priority,
            "completed_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tasks
    ]


# -----------------------------------------------------------------------------
# Phase 9: OpenAI Agent Tools (Tasks, Google Calendar, Gmail, Education)
# -----------------------------------------------------------------------------

async def get_today_tasks(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> dict[str, Any]:
    """Retrieve today's tasks and scheduled blocks with distinction between scheduled and unscheduled."""
    summary = await get_today_schedule(db=db, user_id=user_id, user_tz_str=user_tz_str)
    tasks_only = [item for item in summary.scheduled_items if item.item_type == "task"]
    return {
        "date": summary.target_date,
        "timezone": summary.timezone,
        "scheduled_tasks_count": len(tasks_only),
        "scheduled_tasks": [
            {
                "id": t.id,
                "task_id": str(t.task_id) if t.task_id else None,
                "title": t.title,
                "start_time": t.start_time,
                "end_time": t.end_time,
                "status": t.status,
                "priority": t.priority,
                "is_completed": t.is_completed,
                "is_overdue": t.is_overdue,
            }
            for t in tasks_only
        ],
        "unscheduled_tasks": summary.unscheduled_tasks,
        "deadlines_today": summary.deadlines,
        "next_focus": summary.next_action,
        "next_focus_time": summary.next_action_time,
    }


async def get_task_details(
    db: AsyncSession, user_id: uuid.UUID, task_id: str
) -> dict[str, Any]:
    """Retrieve full details of a specific task by its UUID."""
    try:
        t_uuid = uuid.UUID(task_id)
    except ValueError:
        return {"error": f"Invalid task ID format: {task_id}"}

    query = select(Task).where(Task.id == t_uuid, Task.user_id == user_id)
    task = await db.scalar(query)
    if not task:
        return {"error": f"Task with ID {task_id} not found."}

    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "duration_minutes": task.duration_minutes,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "scheduled_start": task.scheduled_start.isoformat() if task.scheduled_start else None,
        "scheduled_end": task.scheduled_end.isoformat() if task.scheduled_end else None,
        "calendar_sync_status": task.calendar_sync_status,
        "is_archived": task.is_archived,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


async def get_task_summary(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> dict[str, Any]:
    """Retrieve aggregated task metrics, study streak, completed today, and overdue count."""
    from app.services.copilot.accountability import StudentAccountabilityService

    accountability = await StudentAccountabilityService.get_accountability_summary(
        db=db, user_id=user_id
    )
    overdue_items = await get_overdue_tasks(db=db, user_id=user_id, user_tz_str=user_tz_str)
    upcoming = await get_upcoming_deadlines(db=db, user_id=user_id, user_tz_str=user_tz_str, days=7)

    return {
        "streak_days": accountability.streak_days,
        "completed_today": accountability.completed_today_count,
        "missed_sessions_count": accountability.missed_sessions_count,
        "overdue_tasks_count": len(overdue_items),
        "upcoming_deadlines_next_7_days": len(upcoming),
        "supportive_advice": accountability.supportive_message,
    }


# Calendar Tools
async def get_today_calendar_events(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> dict[str, Any]:
    """Retrieve external Google Calendar events for today in user's timezone."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")

    now_loc = datetime.now(UTC).astimezone(tz)
    today_str = now_loc.date().isoformat()
    return await get_calendar_events_for_date(db, user_id, today_str, user_tz_str)


async def get_calendar_events_for_date(
    db: AsyncSession, user_id: uuid.UUID, date_str: str, user_tz_str: str = "Asia/Dhaka"
) -> dict[str, Any]:
    """Retrieve calendar events for a specific date (YYYY-MM-DD) in user's timezone."""
    from app.services.calendar.service import CalendarService

    status = await CalendarService.get_status(user_id=user_id, db=db)
    is_connected = status.is_connected and status.has_sufficient_scopes

    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return {"error": f"Invalid date format: {date_str}. Expected YYYY-MM-DD."}

    start_loc = datetime.combine(target_date, time(0, 0, 0), tzinfo=tz)
    end_loc = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)
    start_utc = start_loc.astimezone(UTC)
    end_utc = end_loc.astimezone(UTC)

    # If connected, trigger quick sync to ensure fresh calendar projection
    if is_connected:
        try:
            await CalendarService.sync_events(
                user_id=user_id, start_time=start_utc, end_time=end_utc, db=db
            )
        except Exception as exc:
            pass  # Fall back to existing cached records if provider sync times out

    events_query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_time >= start_utc,
            CalendarEvent.start_time <= end_utc,
        )
        .order_by(CalendarEvent.start_time.asc())
    )
    res = await db.scalars(events_query)
    events = list(res.all())

    items = [
        {
            "id": str(e.id),
            "title": e.title,
            "description": e.description,
            "start_time": _format_time_display(e.start_time, tz),
            "end_time": _format_time_display(e.end_time, tz),
            "raw_start": e.start_time.isoformat(),
            "raw_end": e.end_time.isoformat(),
            "location": e.location,
            "source": e.source,
            "is_all_day": e.is_all_day,
        }
        for e in events
    ]

    return {
        "date": date_str,
        "is_connected": is_connected,
        "account_email": status.account_email,
        "events_count": len(items),
        "events": items,
        "message": None if is_connected else (status.message or "Google Calendar is not connected. Connect in Settings."),
    }


async def get_upcoming_calendar_events(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka", days: int = 7
) -> dict[str, Any]:
    """Retrieve upcoming calendar events for the next N days."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")

    now_utc = datetime.now(UTC)
    end_utc = now_utc + timedelta(days=days)

    events_query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_time >= now_utc,
            CalendarEvent.start_time <= end_utc,
        )
        .order_by(CalendarEvent.start_time.asc())
    )
    res = await db.scalars(events_query)
    events = list(res.all())

    return {
        "upcoming_days": days,
        "total_events": len(events),
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "start_time": _format_time_display(e.start_time, tz),
                "end_time": _format_time_display(e.end_time, tz),
                "date": e.start_time.astimezone(tz).date().isoformat(),
                "location": e.location,
                "is_all_day": e.is_all_day,
            }
            for e in events
        ],
    }


async def get_calendar_event_details(
    db: AsyncSession, user_id: uuid.UUID, event_id: str
) -> dict[str, Any]:
    """Retrieve details for a specific calendar event."""
    try:
        e_uuid = uuid.UUID(event_id)
    except ValueError:
        return {"error": f"Invalid event ID: {event_id}"}

    query = select(CalendarEvent).where(CalendarEvent.id == e_uuid, CalendarEvent.user_id == user_id)
    ev = await db.scalar(query)
    if not ev:
        return {"error": f"Calendar event {event_id} not found."}

    return {
        "id": str(ev.id),
        "title": ev.title,
        "description": ev.description,
        "start_time": ev.start_time.isoformat(),
        "end_time": ev.end_time.isoformat(),
        "location": ev.location,
        "source": ev.source,
        "external_id": ev.external_id,
    }


# Gmail Tools
async def search_gmail_messages(
    db: AsyncSession, user_id: uuid.UUID, query: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Search or list recent Gmail messages for authenticated user."""
    from app.services.gmail.service import GmailService

    status = await GmailService.get_status(user_id=user_id, db=db)
    if not status.is_connected or not status.has_sufficient_scopes:
        return {
            "is_connected": False,
            "messages": [],
            "unread_count": 0,
            "message": "Gmail account is not connected or missing read scopes. Please connect Gmail in Settings.",
        }

    try:
        messages = await GmailService.list_messages(
            user_id=user_id, db=db, query=query, limit=limit
        )
        items = []
        unread_count = 0
        for m in messages:
            is_unread = "UNREAD" in (m.labels or [])
            if is_unread:
                unread_count += 1
            items.append(
                {
                    "id": m.id,
                    "thread_id": m.thread_id,
                    "sender": m.sender,
                    "subject": m.subject,
                    "date": m.date,
                    "snippet": m.snippet,
                    "is_unread": is_unread,
                }
            )

        return {
            "is_connected": True,
            "account_email": status.account_email,
            "query": query,
            "total_fetched": len(items),
            "unread_count": unread_count,
            "messages": items,
        }
    except Exception as exc:
        return {
            "is_connected": True,
            "messages": [],
            "error": str(exc),
            "message": f"Could not retrieve Gmail messages: {exc}",
        }


async def get_gmail_message(
    db: AsyncSession, user_id: uuid.UUID, message_id: str
) -> dict[str, Any]:
    """Fetch and sanitize complete detail of a specific Gmail message."""
    from app.services.gmail.service import GmailService

    try:
        detail = await GmailService.get_message(user_id=user_id, message_id=message_id, db=db)
        return {
            "id": detail.id,
            "thread_id": detail.thread_id,
            "sender": detail.sender,
            "subject": detail.subject,
            "date": detail.date,
            "snippet": detail.snippet,
            "body_plain": detail.body_plain[:2000] if detail.body_plain else "",
            "labels": detail.labels,
        }
    except Exception as exc:
        return {"error": f"Failed to retrieve email {message_id}: {exc}"}


async def get_gmail_thread(
    db: AsyncSession, user_id: uuid.UUID, thread_id: str
) -> dict[str, Any]:
    """Fetch messages belonging to a Gmail thread."""
    from app.services.gmail.service import GmailService

    try:
        messages = await GmailService.list_messages(
            user_id=user_id, db=db, query=f"thread:{thread_id}", limit=10
        )
        return {
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": [
                {
                    "id": m.id,
                    "sender": m.sender,
                    "subject": m.subject,
                    "date": m.date,
                    "snippet": m.snippet,
                }
                for m in messages
            ],
        }
    except Exception as exc:
        return {"error": f"Failed to retrieve thread {thread_id}: {exc}"}


async def summarize_gmail_message(
    db: AsyncSession, user_id: uuid.UUID, message_id: str
) -> dict[str, Any]:
    """Summarize an email distinguishing verified facts from interpretations."""
    from app.services.gmail.service import GmailService

    try:
        summary_res = await GmailService.summarize_message(
            user_id=user_id, message_id=message_id, db=db
        )
        return {
            "message_id": summary_res.message_id,
            "sender": summary_res.sender,
            "subject": summary_res.subject,
            "verified_facts": summary_res.verified_facts,
            "summary": summary_res.ai_interpretation,
        }
    except Exception as exc:
        return {"error": f"Could not summarize email {message_id}: {exc}"}


async def prepare_gmail_reply_tool(
    db: AsyncSession, user_id: uuid.UUID, target_query_or_recipient: str, reply_intent: str
) -> dict[str, Any]:
    """Draft a contextual reply to an email thread. Requires explicit confirmation before sending."""
    from app.services.copilot.email_copilot import CopilotEmailService

    prompt = f"Reply to {target_query_or_recipient}: {reply_intent}"
    draft = await CopilotEmailService.prepare_email_reply(db=db, user_id=user_id, prompt=prompt)

    return {
        "status": draft.status,
        "requires_confirmation": True,
        "approval_id": draft.approval_id,
        "thread_id": draft.thread_id,
        "recipient_email": draft.recipient_email,
        "recipient_name": draft.recipient_name,
        "subject": draft.subject,
        "body": draft.body,
        "context_summary": draft.context_summary,
        "clarification_question": draft.clarification_question,
        "candidates": draft.candidates,
    }


async def confirm_and_send_gmail_reply_tool(
    db: AsyncSession,
    user_id: uuid.UUID,
    approval_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Send an email only after verifying the user's explicit confirmation token."""
    from app.services.copilot.email_copilot import CopilotEmailService

    success, message, details = await CopilotEmailService.send_confirmed_email(
        db=db,
        user_id=user_id,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        thread_id=thread_id,
        approval_id=approval_id,
    )
    return {
        "success": success,
        "message": message,
        "details": details,
    }


# Educational & Accountability Tools
def search_educational_resources_tool(query: str) -> dict[str, Any]:
    """Search verified educational courses, lectures, videos, and documentation."""
    from app.services.copilot.search import EducationalSearchService

    resources, topic = EducationalSearchService.search_educational_resources(query)
    return {
        "topic": topic,
        "count": len(resources),
        "resources": [
            {
                "title": r.title,
                "url": r.url,
                "platform": r.platform,
                "topic": r.topic,
                "difficulty": r.difficulty,
                "is_free": r.is_free,
                "description": r.description,
                "why_recommended": r.why_recommended,
            }
            for r in resources
        ],
    }


async def get_student_accountability_tool(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve student study streak, missed sessions, and supportive recovery recommendations."""
    from app.services.copilot.accountability import StudentAccountabilityService

    accountability = await StudentAccountabilityService.get_accountability_summary(
        db=db, user_id=user_id
    )
    return {
        "streak_days": accountability.streak_days,
        "completed_today_count": accountability.completed_today_count,
        "missed_sessions_count": accountability.missed_sessions_count,
        "supportive_message": accountability.supportive_message,
        "suggested_recovery_task": accountability.suggested_recovery_task,
    }


# Proactive Daily Briefing Tool
async def get_daily_briefing(
    db: AsyncSession, user_id: uuid.UUID, user_tz_str: str = "Asia/Dhaka"
) -> dict[str, Any]:
    """Compile comprehensive, deterministic daily briefing across schedule, tasks, calendar, and Gmail."""
    from app.services.calendar.service import CalendarService

    user_tz = await resolve_user_timezone(db, user_id, user_tz_str)
    try:
        tz = zoneinfo.ZoneInfo(user_tz)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Dhaka")
        user_tz = "Asia/Dhaka"

    now_utc = datetime.now(UTC)
    now_loc = now_utc.astimezone(tz)
    today_date = now_loc.date()
    target_date_str = today_date.isoformat()
    hour = now_loc.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # 1. Fetch Today's Full Schedule (Blocks + Events + Backlog)
    today_schedule = await get_today_schedule(db=db, user_id=user_id, user_tz_str=user_tz)
    scheduled_items = today_schedule.scheduled_items
    calendar_events = [it for it in scheduled_items if it.item_type == "calendar_event"]
    task_blocks = [it for it in scheduled_items if it.item_type == "task"]
    unscheduled_tasks = today_schedule.unscheduled_tasks

    # 2. Check Google Calendar Status
    cal_connected = False
    cal_account_email: str | None = None
    try:
        cal_status = await CalendarService.get_status(user_id=user_id, db=db)
        cal_connected = bool(cal_status.is_connected)
        cal_account_email = cal_status.account_email
    except Exception:
        cal_connected = False

    # 3. Fetch Overdue Tasks
    overdue_tasks = await get_overdue_tasks(db=db, user_id=user_id, user_tz_str=user_tz)

    # 4. Fetch Upcoming Deadlines (Next 72 hours)
    upcoming_deadlines = await get_upcoming_deadlines(db=db, user_id=user_id, user_tz_str=user_tz, days=3)

    # 5. Fetch Gmail Messages (Unread & Important)
    gmail_res = await search_gmail_messages(db=db, user_id=user_id, query="is:unread", limit=5)
    gmail_connected = bool(gmail_res.get("is_connected", False))
    unread_emails_count = int(gmail_res.get("unread_count", 0))
    unread_messages = gmail_res.get("messages", [])
    gmail_account_email = gmail_res.get("account_email")

    # 6. Fetch Student Consistency / Streak
    accountability = await get_student_accountability_tool(db=db, user_id=user_id)
    streak_days = int(accountability.get("streak_days", 0))
    completed_today_count = int(accountability.get("completed_today_count", 0))

    # 7. Deterministic Recommended First Focus Logic
    # Priority Hierarchy:
    # 1. Critical Overdue Task (P1 or P2)
    # 2. Currently Active or Next Scheduled Focus Block Today
    # 3. Imminent Deadline (within next 72 hours)
    # 4. Any remaining overdue task (P3/P4)
    # 5. High-priority backlog task
    # 6. All clear
    recommended_focus: dict[str, Any] = {
        "task_id": None,
        "title": "All caught up!",
        "priority": None,
        "reason": "You have no overdue tasks, scheduled blocks, or approaching deadlines right now.",
        "action_type": "all_clear",
        "scheduled_time": None,
        "deadline": None,
    }

    # Step 1: Check Critical Overdue Tasks (P1 or P2)
    critical_overdue = [
        t for t in overdue_tasks if str(t.get("priority", "")).upper() in ("P1", "P2", "URGENT", "HIGH")
    ]
    if critical_overdue:
        # Sort P1 before P2
        critical_overdue.sort(key=lambda x: (0 if str(x.get("priority", "")).upper() == "P1" else 1))
        t = critical_overdue[0]
        p_label = str(t.get("priority", "P1")).upper()
        recommended_focus = {
            "task_id": t["id"],
            "title": t["title"],
            "priority": p_label,
            "reason": f"This task is overdue (due {t.get('deadline') or 'earlier'}) with {p_label} priority. Resolving it clears your backlog and protects your schedule.",
            "action_type": "overdue",
            "deadline": t.get("deadline"),
            "scheduled_time": None,
        }
    # Step 2: Check Today's Scheduled Focus Blocks
    elif task_blocks:
        uncompleted_blocks = [b for b in task_blocks if not b.is_completed]
        if uncompleted_blocks:
            first_block = uncompleted_blocks[0]
            recommended_focus = {
                "task_id": first_block.task_id or first_block.id,
                "title": first_block.title,
                "priority": str(first_block.priority).upper() if first_block.priority else "P2",
                "reason": f"You have a dedicated study session scheduled from {first_block.start_time} to {first_block.end_time}. Staying on schedule preserves your study momentum.",
                "action_type": "scheduled_block",
                "scheduled_time": f"{first_block.start_time} – {first_block.end_time}",
                "deadline": None,
            }
    # Step 3: Check Approaching Deadlines (next 72 hours)
    if recommended_focus["action_type"] == "all_clear" and upcoming_deadlines:
        sorted_dl = sorted(
            upcoming_deadlines,
            key=lambda x: (
                0 if str(x.get("priority", "")).upper() == "P1" else (
                    1 if str(x.get("priority", "")).upper() == "P2" else 2
                )
            ),
        )
        d = sorted_dl[0]
        p_label = str(d.get("priority", "P2")).upper()
        recommended_focus = {
            "task_id": d["id"],
            "title": d["title"],
            "priority": p_label,
            "reason": f"This task has an approaching academic deadline due on {d.get('deadline_time') or 'soon'} ({p_label}). Tackling it early avoids last-minute cramming.",
            "action_type": "upcoming_deadline",
            "deadline": d.get("deadline_time"),
            "scheduled_time": None,
        }
    # Step 4: Check Any Other Overdue Task
    if recommended_focus["action_type"] == "all_clear" and overdue_tasks:
        t = overdue_tasks[0]
        recommended_focus = {
            "task_id": t["id"],
            "title": t["title"],
            "priority": str(t.get("priority", "P3")).upper(),
            "reason": f"This task was due {t.get('deadline') or 'earlier'}. Completing or rescheduling it keeps your task list clean.",
            "action_type": "overdue",
            "deadline": t.get("deadline"),
            "scheduled_time": None,
        }
    # Step 5: Check Unscheduled Backlog Tasks
    if recommended_focus["action_type"] == "all_clear" and unscheduled_tasks:
        u = unscheduled_tasks[0]
        recommended_focus = {
            "task_id": u["id"],
            "title": u["title"],
            "priority": str(u.get("priority", "P3")).upper(),
            "reason": "Your scheduled blocks are clear. Starting this priority item from your backlog builds positive academic momentum.",
            "action_type": "backlog",
            "deadline": u.get("deadline"),
            "scheduled_time": None,
        }

    # 8. Assemble Clean Markdown Text
    date_display = now_loc.strftime("%A, %B %d, %Y")
    lines: list[str] = [
        f"## 🌅 {greeting}! Here is your Daily Briefing for {date_display}",
        f"*Timezone: `{user_tz}` | Local Time: `{now_loc.strftime('%I:%M %p').lstrip('0')}`*",
        "",
        "### 🎯 Recommended First Focus",
    ]

    if recommended_focus["action_type"] != "all_clear":
        p_badge = f"`{recommended_focus['priority']}`" if recommended_focus.get("priority") else ""
        time_info = ""
        if recommended_focus.get("scheduled_time"):
            time_info = f" • **Time:** {recommended_focus['scheduled_time']}"
        elif recommended_focus.get("deadline"):
            time_info = f" • **Due:** {recommended_focus['deadline']}"

        lines.extend([
            f"> **{recommended_focus['title']}** {p_badge}{time_info}",
            f"> **Why:** {recommended_focus['reason']}",
            "",
        ])
    else:
        lines.extend([
            "> **All Caught Up!**",
            f"> **Why:** {recommended_focus['reason']}",
            "",
        ])

    lines.append("---")
    lines.append("### 📅 Today's Schedule & Commitments")
    if scheduled_items:
        lines.append(f"You have **{len(scheduled_items)}** scheduled item{'s' if len(scheduled_items) != 1 else ''} today:")
        for item in scheduled_items:
            type_tag = "Google Event" if item.item_type == "calendar_event" else "Study Block"
            status_tag = " *(completed)*" if item.is_completed else ""
            lines.append(f"- **{item.start_time} – {item.end_time}**: {item.title} `[{type_tag}]`{status_tag}")
    else:
        lines.append("- No fixed events or focus blocks scheduled for today. Your day is open for self-paced study.")

    if not cal_connected:
        lines.append("> ℹ️ *Google Calendar is not connected. Connect in Settings to view external courses and meetings.*")

    lines.append("")
    lines.append("### ⚠️ Deadlines & Overdue Tasks")
    if overdue_tasks:
        lines.append(f"**Overdue ({len(overdue_tasks)}):**")
        for ot in overdue_tasks[:4]:
            lines.append(f"- 🔴 **{ot['title']}** (Due {ot.get('deadline') or 'earlier'}, `{ot.get('priority', 'P3')}`)")
        if len(overdue_tasks) > 4:
            lines.append(f"- *...and {len(overdue_tasks) - 4} more overdue task(s).*")
    else:
        lines.append("- ✅ **No overdue tasks.** Your backlog is clean!")

    if upcoming_deadlines:
        lines.append(f"**Upcoming Deadlines ({len(upcoming_deadlines)} in next 72h):**")
        for dl in upcoming_deadlines[:4]:
            lines.append(f"- ⏳ **{dl['title']}** (Due {dl.get('deadline_time') or 'soon'}, `{dl.get('priority', 'P2')}`)")
    elif not overdue_tasks:
        lines.append("- ✅ **No approaching deadlines** in the next 3 days.")

    lines.append("")
    lines.append("### 📬 Gmail & Communications")
    if gmail_connected:
        if unread_messages:
            lines.append(f"You have **{unread_emails_count} unread email{'s' if unread_emails_count != 1 else ''}** in `{gmail_account_email or 'Gmail'}`:")
            for m in unread_messages[:3]:
                sender_name = m['sender'].split("<")[0].strip() if "<" in m['sender'] else m['sender']
                lines.append(f"- 📩 From **{sender_name}**: \"{m['subject']}\"")
        else:
            lines.append(f"- ✅ Connected as `{gmail_account_email or 'active user'}`. Inbox is caught up (0 unread).")
    else:
        lines.append("> ℹ️ *Gmail is not connected. Connect in Settings to review important academic emails and instructor announcements.*")

    lines.append("")
    lines.append("### ⚡ Consistency & Progress")
    lines.append(f"- **Current Study Streak:** 🔥 **{streak_days} day{'s' if streak_days != 1 else ''}**")
    lines.append(f"- **Completed Today:** ✅ **{completed_today_count} task{'s' if completed_today_count != 1 else ''}**")

    formatted_md = "\n".join(lines)

    # 9. Spoken Concise Script for Audio
    rec_title = recommended_focus["title"]
    if recommended_focus["action_type"] != "all_clear":
        focus_phrase = f"your top recommendation is to focus on {rec_title}"
    else:
        focus_phrase = "your schedule is all clear with no pending deadlines"

    sched_phrase = f"{len(scheduled_items)} scheduled session{'s' if len(scheduled_items) != 1 else ''}"
    overdue_phrase = f"{len(overdue_tasks)} overdue item{'s' if len(overdue_tasks) != 1 else ''}"
    spoken_summary = (
        f"{greeting}! Here is your daily briefing for {now_loc.strftime('%A, %B %d')}. "
        f"Right now, {focus_phrase}. "
        f"You have {sched_phrase}, {overdue_phrase}, and {unread_emails_count} unread emails. "
        f"Let's make today productive!"
    )

    # 10. Structured Briefing Payload
    briefing_payload = {
        "target_date": target_date_str,
        "timezone": user_tz,
        "greeting": greeting,
        "recommended_focus": recommended_focus,
        "scheduled_items_count": len(task_blocks),
        "calendar_events_count": len(calendar_events),
        "overdue_count": len(overdue_tasks),
        "upcoming_deadlines_count": len(upcoming_deadlines),
        "unread_emails_count": unread_emails_count,
        "gmail_status": "connected" if gmail_connected else "disconnected",
        "gmail_account_email": gmail_account_email,
        "calendar_status": "connected" if cal_connected else "disconnected",
        "calendar_account_email": cal_account_email,
        "streak_days": streak_days,
        "completed_today_count": completed_today_count,
        "summary_text": f"Briefing for {date_display}: {len(scheduled_items)} events/blocks, {len(overdue_tasks)} overdue, {len(upcoming_deadlines)} upcoming deadlines.",
    }

    return {
        "briefing_payload": briefing_payload,
        "schedule_summary": today_schedule,
        "formatted_markdown": formatted_md,
        "spoken_summary": spoken_summary,
        "recommended_focus": recommended_focus,
        "scheduled_items_count": len(task_blocks),
        "calendar_events_count": len(calendar_events),
        "overdue_count": len(overdue_tasks),
        "upcoming_deadlines_count": len(upcoming_deadlines),
        "unread_emails_count": unread_emails_count,
        "gmail_status": "connected" if gmail_connected else "disconnected",
        "calendar_status": "connected" if cal_connected else "disconnected",
        "streak_days": streak_days,
        "completed_today_count": completed_today_count,
    }
