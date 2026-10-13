"""Planner domain service orchestrating natural-language plan extraction and confirmation."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.action import AuditLog
from app.db.models.calendar import CalendarEvent
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.planner import (
    PlanConfirmRequest,
    PlanConfirmResponse,
    PlanGenerateRequest,
    PlanProposalResponse,
)
from app.schemas.task import TaskResponse
from app.services.ai.factory import parse_instruction_resilient
from app.services.ai.models import ExistingItemSummary, UserPlanContext
from app.services.scheduler.engine import DeterministicSchedulerEngine
from app.services.scheduler.models import FixedEvent, SchedulableTask, ScheduleProposal
from app.services.scheduler.service import SchedulerService, resolve_working_interval
from app.services.task_service import TaskService

logger = get_logger("mentor_ai.planner_service")


class PlannerService:
    """Orchestrates natural language parsing, clarification detection, preview generation, and plan confirmation."""

    @staticmethod
    async def generate_draft_plan(
        db: AsyncSession,
        user_id: uuid.UUID,
        req: PlanGenerateRequest,
    ) -> PlanProposalResponse:
        """Process user instruction, extract structured plan, detect missing info, and provide schedule preview.

        Does NOT mutate database or persist tasks.
        """
        # 1. Fetch user profile and preferences
        profile_res = await db.execute(select(Profile).where(Profile.id == user_id))
        profile = profile_res.scalar_one_or_none()

        pref_res = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        preferences = pref_res.scalar_one_or_none()

        tz_name = req.client_timezone or (profile.timezone if profile else "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
            tz_name = "UTC"

        now_in_tz = datetime.now(tz)
        today = now_in_tz.date()

        work_start = preferences.work_start_time if preferences else "09:00:00"
        work_end = preferences.work_end_time if preferences else "18:00:00"
        buffer_mins = preferences.buffer_minutes if preferences else 15
        auto_breaks = preferences.auto_schedule_breaks if preferences else True

        # Parse work start and end time objects
        sh, sm = map(int, work_start.split(":")[:2])
        eh, em = map(int, work_end.split(":")[:2])
        w_start_time = time(sh, sm)
        w_end_time = time(eh, em)

        # 2. Retrieve existing commitments for context
        cal_stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.end_time
            >= datetime.combine(today, time(0, 0), tzinfo=tz).astimezone(UTC),
            CalendarEvent.start_time
            <= datetime.combine(today + timedelta(days=2), time(23, 59), tzinfo=tz).astimezone(UTC),
        )
        cal_res = await db.execute(cal_stmt)
        existing_events = [
            ExistingItemSummary(
                id=str(e.id),
                title=e.title,
                start_time=e.start_time.isoformat(),
                end_time=e.end_time.isoformat(),
            )
            for e in cal_res.scalars().all()
        ]

        task_stmt = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.is_archived.is_(False),
            )
            .limit(10)
        )
        task_res = await db.execute(task_stmt)
        existing_tasks = [
            ExistingItemSummary(
                id=str(t.id),
                title=t.title,
                duration_minutes=t.duration_minutes,
                priority=t.priority,
            )
            for t in task_res.scalars().all()
        ]

        # 3. Assemble UserPlanContext
        context = UserPlanContext(
            current_date=today,
            timezone=tz_name,
            work_start_time=w_start_time,
            work_end_time=w_end_time,
            buffer_minutes=buffer_mins,
            existing_events=existing_events,
            existing_tasks=existing_tasks,
        )

        # 4. Invoke resilient AI parser
        parse_result = await parse_instruction_resilient(req.message, context)
        draft = parse_result.draft_plan

        # If user explicitly requested target_date, respect override
        effective_target_date = req.target_date or draft.target_date

        # 5. Check for missing information
        missing_info: list[str] = []
        for t in draft.tasks:
            if t.duration_minutes is None:
                missing_info.append(f"Estimated duration missing for task: '{t.title}'")

        if draft.intent == "clarification_needed" and not missing_info:
            missing_info.append("Request needs clarification before a schedule can be constructed.")

        # Determine if confirmation is possible
        requires_confirmation = (
            len(missing_info) == 0
            and draft.intent not in ["clarification_needed", "unsupported"]
            and (len(draft.tasks) > 0 or len(draft.fixed_events) > 0)
        )

        # 6. Generate Dry-Run Preview Schedule using Day 5 engine if feasible
        preview_schedule: ScheduleProposal | None = None
        if requires_confirmation and draft.tasks:
            try:
                working_interval = resolve_working_interval(
                    target_date=effective_target_date,
                    work_start_str=work_start,
                    work_end_str=work_end,
                    tz_name=tz_name,
                )

                # Combine existing calendar events for that day + new extracted fixed events
                preview_fixed_events: list[FixedEvent] = [
                    FixedEvent(
                        id=uuid.uuid4(),
                        title=fe.title,
                        start_time=fe.start_time,
                        end_time=fe.end_time,
                        location=fe.location,
                    )
                    for fe in draft.fixed_events
                ]

                # Also include existing calendar events for this date
                cal_date_stmt = select(CalendarEvent).where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.end_time > working_interval.start_time,
                    CalendarEvent.start_time < working_interval.end_time,
                )
                cal_date_res = await db.execute(cal_date_stmt)
                for db_evt in cal_date_res.scalars().all():
                    preview_fixed_events.append(
                        FixedEvent(
                            id=db_evt.id,
                            title=db_evt.title,
                            start_time=db_evt.start_time,
                            end_time=db_evt.end_time,
                            location=db_evt.location,
                        )
                    )

                # Schedulable tasks (ephemeral UUIDs for preview)
                preview_tasks: list[SchedulableTask] = [
                    SchedulableTask(
                        id=uuid.uuid4(),
                        title=dt.title,
                        duration_minutes=dt.duration_minutes or 45,
                        priority=dt.priority,
                        deadline=dt.deadline,
                        energy_level=dt.energy_level or "medium",
                    )
                    for dt in draft.tasks
                ]

                solver = DeterministicSchedulerEngine(
                    working_interval=working_interval,
                    fixed_events=preview_fixed_events,
                    tasks=preview_tasks,
                    target_date=effective_target_date,
                    timezone_name=tz_name,
                    buffer_minutes=buffer_mins,
                    enforce_buffer=True,
                    auto_schedule_breaks=auto_breaks,
                )
                preview_schedule = solver.generate_schedule()
            except Exception as exc:
                logger.warning("preview_schedule_failed", error=str(exc))
                preview_schedule = None

        return PlanProposalResponse(
            proposal_id=str(uuid.uuid4()),
            original_prompt=req.message,
            target_date=effective_target_date,
            intent=draft.intent,
            explanation=draft.explanation,
            fixed_events=draft.fixed_events,
            tasks=draft.tasks,
            missing_information=missing_info,
            clarification_question=draft.clarification_question,
            requires_confirmation=requires_confirmation,
            parser_used=parse_result.parser_used,
            fallback_applied=parse_result.fallback_applied,
            preview_schedule=preview_schedule,
        )

    @staticmethod
    async def confirm_plan(
        db: AsyncSession,
        user_id: uuid.UUID,
        req: PlanConfirmRequest,
        client_ip: str | None = None,
    ) -> PlanConfirmResponse:
        """Persist confirmed tasks and fixed events, then generate and save the schedule via Day 5 solver."""
        created_tasks: list[TaskResponse] = []
        created_events: list[dict[str, Any]] = []
        persisted_task_ids: list[uuid.UUID] = []

        # 1. Persist new tasks
        if req.persist_tasks and req.tasks:
            for task_payload in req.tasks:
                created_task_model = await TaskService.create_task(
                    db=db,
                    user_id=user_id,
                    payload=task_payload,
                    client_ip=client_ip,
                )
                created_tasks.append(TaskResponse.model_validate(created_task_model))
                persisted_task_ids.append(created_task_model.id)

        # 2. Persist new fixed events
        if req.fixed_events:
            for evt in req.fixed_events:
                db_event = CalendarEvent(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    title=evt.title,
                    start_time=evt.start_time,
                    end_time=evt.end_time,
                    location=evt.location,
                    is_fixed=True,
                    source="internal",
                )
                db.add(db_event)
                created_events.append(
                    {
                        "id": str(db_event.id),
                        "title": db_event.title,
                        "start_time": db_event.start_time.isoformat(),
                        "end_time": db_event.end_time.isoformat(),
                        "location": db_event.location,
                    }
                )

            await db.flush()

        # 3. Generate and persist schedule if requested
        proposal: ScheduleProposal | None = None
        persisted_sched_id: str | None = None

        if req.generate_schedule and (persisted_task_ids or created_events):
            proposal = await SchedulerService.generate_proposal(
                db=db,
                user_id=user_id,
                target_date=req.target_date,
                task_ids=persisted_task_ids if persisted_task_ids else None,
            )
            persisted_sched = await SchedulerService.persist_approved_schedule(
                db=db,
                user_id=user_id,
                proposal=proposal,
            )
            persisted_sched_id = str(persisted_sched.id)

        # 4. Record audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="plan_confirmed",
            resource_type="plan",
            resource_id=req.proposal_id or str(uuid.uuid4()),
            details={
                "target_date": req.target_date.isoformat(),
                "created_tasks_count": len(created_tasks),
                "created_events_count": len(created_events),
                "persisted_schedule_id": persisted_sched_id,
            },
            ip_address=client_ip,
        )
        db.add(audit)
        await db.commit()

        return PlanConfirmResponse(
            target_date=req.target_date,
            created_tasks=created_tasks,
            created_events=created_events,
            schedule=proposal,
            persisted_schedule_id=persisted_sched_id,
            status="confirmed",
        )
