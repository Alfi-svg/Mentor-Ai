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


def _format_time_display(dt: datetime, tz: zoneinfo.ZoneInfo) -> str:
    """Format UTC datetime into user timezone display, e.g. 09:30 AM."""
    dt_loc = dt.astimezone(tz)
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
        is_overdue = (
            (task.deadline is not None and task.deadline < now_utc and not is_completed)
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
        if item.raw_end > now_utc and not item.is_completed:
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
