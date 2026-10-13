"""Scheduler application service integrating database models with the pure scheduling engine."""

import uuid
import zoneinfo
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app.core.errors import AppException
from app.core.logging import get_logger
from app.db.models.action import AuditLog
from app.db.models.calendar import CalendarEvent
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.services.scheduler.engine import DeterministicSchedulerEngine
from app.services.scheduler.models import (
    FixedEvent,
    SchedulableTask,
    ScheduleProposal,
    TimeInterval,
)

logger = get_logger("mentor_ai.scheduler_service")


def resolve_working_interval(
    target_date: date,
    work_start_str: str,
    work_end_str: str,
    tz_name: str,
) -> TimeInterval:
    """Construct working window in local timezone and convert to timezone-aware UTC interval."""
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    sh, sm = map(int, work_start_str.split(":")[:2])
    eh, em = map(int, work_end_str.split(":")[:2])

    start_local = datetime.combine(target_date, time(sh, sm), tzinfo=tz)

    if (eh, em) <= (sh, sm):
        # Working period crosses midnight into following day
        end_local = datetime.combine(target_date + timedelta(days=1), time(eh, em), tzinfo=tz)
    else:
        end_local = datetime.combine(target_date, time(eh, em), tzinfo=tz)

    return TimeInterval(
        start_time=start_local.astimezone(UTC),
        end_time=end_local.astimezone(UTC),
    )


class SchedulerService:
    """Orchestrates schedule generation, validation, and persistence."""

    @staticmethod
    async def generate_proposal(
        db: AsyncSession,
        user_id: uuid.UUID,
        target_date: date,
        task_ids: list[uuid.UUID] | None = None,
        enforce_buffer: bool = True,
        override_timezone: str | None = None,
    ) -> ScheduleProposal:
        """Extract user constraints and tasks, execute deterministic solver, and return proposal."""
        # 1. Fetch user profile and preferences (safe defaults if unconfigured)
        profile_res = await db.execute(select(Profile).where(Profile.id == user_id))
        profile = profile_res.scalar_one_or_none()

        pref_res = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        preferences = pref_res.scalar_one_or_none()

        work_start = preferences.work_start_time if preferences else "09:00:00"
        work_end = preferences.work_end_time if preferences else "18:00:00"
        buffer_mins = preferences.buffer_minutes if preferences else 15
        auto_breaks = preferences.auto_schedule_breaks if preferences else True
        tz_name = override_timezone or (profile.timezone if profile else "UTC")

        # 2. Compute working window interval
        working_interval = resolve_working_interval(
            target_date=target_date,
            work_start_str=work_start,
            work_end_str=work_end,
            tz_name=tz_name,
        )

        # 3. Retrieve tasks to schedule
        if task_ids:
            tasks_stmt = select(Task).where(
                Task.user_id == user_id,
                Task.id.in_(task_ids),
                Task.is_archived.is_(False),
            )
        else:
            # Default to active pending/in_progress tasks
            tasks_stmt = select(Task).where(
                Task.user_id == user_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.is_archived.is_(False),
            )
        tasks_res = await db.execute(tasks_stmt)
        db_tasks = list(tasks_res.scalars().all())

        schedulable_tasks = [
            SchedulableTask(
                id=t.id,
                title=t.title,
                duration_minutes=t.duration_minutes,
                priority=t.priority,  # type: ignore[arg-type]
                deadline=t.deadline,
                energy_level=t.energy_level,  # type: ignore[arg-type]
                constraints=t.constraints,
                allow_split=bool(t.constraints.get("allow_split", False)),
            )
            for t in db_tasks
        ]

        # 4. Retrieve fixed calendar commitments overlapping with the working window
        cal_stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.end_time > working_interval.start_time,
            CalendarEvent.start_time < working_interval.end_time,
        )
        cal_res = await db.execute(cal_stmt)
        db_cal_events = list(cal_res.scalars().all())

        fixed_events = [
            FixedEvent(
                id=e.id,
                title=e.title,
                start_time=e.start_time,
                end_time=e.end_time,
                is_all_day=e.is_all_day,
                location=e.location,
            )
            for e in db_cal_events
        ]

        # 5. Execute deterministic scheduling engine
        engine = DeterministicSchedulerEngine(
            working_interval=working_interval,
            fixed_events=fixed_events,
            tasks=schedulable_tasks,
            target_date=target_date,
            timezone_name=tz_name,
            buffer_minutes=buffer_mins,
            enforce_buffer=enforce_buffer,
            auto_schedule_breaks=auto_breaks,
        )

        proposal = engine.generate_schedule()
        logger.info(
            "Schedule proposal generated",
            user_id=str(user_id),
            target_date=str(target_date),
            status=proposal.status,
            total_blocks=len(proposal.blocks),
            unscheduled_count=len(proposal.unscheduled_tasks),
        )
        return proposal

    @staticmethod
    async def persist_approved_schedule(
        db: AsyncSession,
        user_id: uuid.UUID,
        proposal: ScheduleProposal,
        client_ip: str | None = None,
    ) -> Schedule:
        """Persist an approved schedule proposal, superseding any prior schedule for the date."""
        if not proposal.validation.is_valid:
            raise AppException(
                detail=f"Cannot persist invalid schedule proposal: {'; '.join(proposal.validation.errors)}",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_SCHEDULE_PROPOSAL",
            )

        # 1. Supersede any existing active schedule for the target date
        await db.execute(
            update(Schedule)
            .where(
                Schedule.user_id == user_id,
                Schedule.schedule_date == proposal.target_date,
                Schedule.status == "accepted",
            )
            .values(status="superseded")
        )

        # 2. Create new Schedule entity
        new_schedule = Schedule(
            id=proposal.schedule_id,
            user_id=user_id,
            schedule_date=proposal.target_date,
            status="accepted",
            metadata_json={
                "timezone": proposal.timezone,
                "total_scheduled_minutes": proposal.total_scheduled_minutes,
                "total_free_minutes": proposal.total_free_minutes,
                "conflicts_count": len(proposal.conflicts),
            },
            created_at=datetime.now(UTC),
        )
        db.add(new_schedule)

        # 3. Create discrete ScheduleBlock entities
        for block_prop in proposal.blocks:
            sb = ScheduleBlock(
                id=block_prop.id,
                schedule_id=new_schedule.id,
                user_id=user_id,
                task_id=block_prop.task_id,
                calendar_event_id=block_prop.calendar_event_id,
                title=block_prop.title,
                start_time=block_prop.start_time,
                end_time=block_prop.end_time,
                block_type=block_prop.block_type,
                is_completed=False,
            )
            db.add(sb)

        # 4. Atomic Audit Log
        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="schedule_approved",
            resource_type="schedule",
            resource_id=str(new_schedule.id),
            details={
                "target_date": str(proposal.target_date),
                "blocks_count": len(proposal.blocks),
                "total_scheduled_minutes": proposal.total_scheduled_minutes,
            },
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(new_schedule)

        logger.info(
            "Schedule approved and persisted",
            schedule_id=str(new_schedule.id),
            user_id=str(user_id),
            date=str(proposal.target_date),
        )
        return new_schedule

    @staticmethod
    async def get_schedule_for_date(
        db: AsyncSession,
        user_id: uuid.UUID,
        target_date: date,
    ) -> Schedule | None:
        """Retrieve accepted schedule with blocks for a given user and target date."""
        stmt = (
            select(Schedule)
            .options(selectinload(Schedule.blocks))
            .where(
                Schedule.user_id == user_id,
                Schedule.schedule_date == target_date,
                Schedule.status == "accepted",
            )
            .order_by(Schedule.created_at.desc())
        )
        res = await db.execute(stmt)
        return res.scalars().first()
