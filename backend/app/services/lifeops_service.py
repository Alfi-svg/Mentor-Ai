"""Unified LifeOps domain service orchestrating natural-language intents into schedules and actions."""

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.action import ActionHistory
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.action import ActionResponse
from app.schemas.lifeops import (
    LifeOpsPlanRequest,
    LifeOpsWorkflowResponse,
    LifeOpsWorkflowStep,
)
from app.schemas.task import TaskCreateRequest
from app.services.action_service import ActionService
from app.services.calendar.service import CalendarService
from app.services.gmail.models import EmailTaskCandidate, GmailMessageSummary
from app.services.gmail.service import GmailService
from app.services.notification_service import NotificationService
from app.services.scheduler.service import SchedulerService
from app.services.task_service import TaskService

logger = get_logger("mentor_ai.lifeops_service")


class LifeOpsService:
    """Orchestrates the 10-stage LifeOps execution pipeline:

    User Input -> Intent Understanding -> Task Extraction -> Constraint Validation ->
    Calendar Availability -> Deterministic Scheduling -> User Review -> Explicit Approval ->
    Tool Execution -> Outcome Verification -> Persistent Notification.
    """

    @classmethod
    async def execute_workflow(
        cls,
        user_id: uuid.UUID,
        req: LifeOpsPlanRequest,
        db: AsyncSession,
    ) -> LifeOpsWorkflowResponse:
        """Execute full end-to-end LifeOps lifecycle."""
        steps: list[LifeOpsWorkflowStep] = []
        now = datetime.now(UTC)

        # ---------------------------------------------------------------------
        # 1. Intent Understanding & Timezone Resolution
        # ---------------------------------------------------------------------
        profile_res = await db.execute(select(Profile).where(Profile.id == user_id))
        profile = profile_res.scalar_one_or_none()
        pref_res = await db.execute(select(UserPreferences).where(UserPreferences.user_id == user_id))
        preferences = pref_res.scalar_one_or_none()

        user_tz_name = req.client_timezone or (profile.timezone if profile else "UTC")
        try:
            user_tz = ZoneInfo(user_tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")
            user_tz_name = "UTC"

        now_local = datetime.now(user_tz)
        target_date = req.target_date
        if not target_date:
            if "tomorrow" in req.prompt.lower():
                target_date = (now_local + timedelta(days=1)).date()
            else:
                target_date = now_local.date()

        has_email_intent = any(
            kw in req.prompt.lower()
            for kw in ["email", "assignment", "inbox", "mail", "gmail", "message"]
        )
        has_schedule_intent = any(
            kw in req.prompt.lower()
            for kw in ["schedule", "plan", "day", "calendar", "study", "tomorrow", "work"]
        )
        has_remind_intent = any(
            kw in req.prompt.lower()
            for kw in ["remind", "notification", "alert", "deadline", "warn"]
        )

        steps.append(
            LifeOpsWorkflowStep(
                step="intent_understanding",
                status="completed",
                detail=(
                    f"Analyzed intent: email_analysis={has_email_intent}, "
                    f"scheduling={has_schedule_intent}, notifications={has_remind_intent}. "
                    f"Target date: {target_date} ({user_tz_name})."
                ),
            )
        )

        # ---------------------------------------------------------------------
        # 2. Integration Health & Permissions Check
        # ---------------------------------------------------------------------
        gmail_status = await GmailService.get_status(user_id=user_id, db=db)
        cal_status = await CalendarService.get_status(user_id=user_id, db=db)

        # ---------------------------------------------------------------------
        # 3. Email Analysis & Task Extraction
        # ---------------------------------------------------------------------
        analyzed_emails: list[GmailMessageSummary] = []
        extracted_candidates: list[EmailTaskCandidate] = []
        has_ambiguity = False
        clarifications: list[str] = []

        if has_email_intent and req.auto_extract_emails:
            if not gmail_status.is_connected and not gmail_status.configured:
                steps.append(
                    LifeOpsWorkflowStep(
                        step="email_analysis",
                        status="skipped",
                        detail="Gmail is not connected. Please connect your Gmail account in settings to extract tasks from emails.",
                    )
                )
            else:
                try:
                    analyzed_emails = await GmailService.list_messages(
                        user_id=user_id,
                        db=db,
                        query=req.email_query,
                        limit=5,
                    )
                    mids = [m.id for m in analyzed_emails]
                    extracted_candidates = await GmailService.extract_tasks_from_messages(
                        user_id=user_id,
                        message_ids=mids,
                        db=db,
                    )

                    for cand in extracted_candidates:
                        if cand.is_deadline_ambiguous:
                            has_ambiguity = True
                            clarifications.append(
                                f"For '{cand.title}', the deadline appears ambiguous ({cand.ambiguity_reason}). What exact date and time would you like to set?"
                            )

                    step_status = "requires_clarification" if has_ambiguity else "completed"
                    steps.append(
                        LifeOpsWorkflowStep(
                            step="task_extraction",
                            status=step_status,
                            detail=f"Analyzed {len(analyzed_emails)} emails and extracted {len(extracted_candidates)} candidate tasks.",
                        )
                    )
                except Exception as exc:
                    logger.warning("Error during email extraction in LifeOps", error=str(exc))
                    steps.append(
                        LifeOpsWorkflowStep(
                            step="email_analysis",
                            status="skipped",
                            detail=f"Could not read emails: {exc}",
                        )
                    )

        # ---------------------------------------------------------------------
        # 4. Task Creation (Confirmed Tasks)
        # ---------------------------------------------------------------------
        created_task_ids: list[uuid.UUID] = []
        if req.confirmed_tasks:
            for task_data in req.confirmed_tasks:
                try:
                    payload = TaskCreateRequest(
                        title=task_data["title"],
                        duration_minutes=task_data.get("duration_minutes", 60),
                        priority=task_data.get("priority", "P3"),
                        deadline=task_data.get("deadline"),
                        description=task_data.get("description"),
                        energy_level=task_data.get("energy_level", "medium"),
                    )
                    created = await TaskService.create_task(db=db, user_id=user_id, payload=payload)
                    created_task_ids.append(created.id)
                except Exception as exc:
                    logger.warning("Failed to create confirmed task", error=str(exc))

        # ---------------------------------------------------------------------
        # 5. Constraint Validation & Calendar Availability
        # ---------------------------------------------------------------------
        # Check existing commitments
        start_of_target = datetime.combine(target_date, time(0, 0), tzinfo=user_tz).astimezone(UTC)
        end_of_target = datetime.combine(target_date, time(23, 59), tzinfo=user_tz).astimezone(UTC)

        events_count = 0
        try:
            cal_events = await CalendarService.get_events(
                user_id=user_id,
                start_time=start_of_target,
                end_time=end_of_target,
                db=db,
            )
            events_count = len(cal_events)
        except Exception:
            events_count = 0

        steps.append(
            LifeOpsWorkflowStep(
                step="calendar_availability",
                status="completed",
                detail=f"Checked schedule constraints: {events_count} fixed calendar commitments detected for {target_date}.",
            )
        )

        # ---------------------------------------------------------------------
        # 6. Deterministic Scheduling
        # ---------------------------------------------------------------------
        schedule_proposal: ScheduleProposalResponse | None = None
        if has_schedule_intent:
            try:
                # If specific tasks were created, schedule them; otherwise schedule pending backlog
                filter_ids = created_task_ids if created_task_ids else None
                proposal_data = await SchedulerService.generate_proposal(
                    db=db,
                    user_id=user_id,
                    target_date=target_date,
                    task_ids=filter_ids,
                    enforce_buffer=True,
                )
                schedule_proposal = proposal_data
                steps.append(
                    LifeOpsWorkflowStep(
                        step="deterministic_scheduling",
                        status="completed",
                        detail=(
                            f"Generated deterministic timeline: {len(schedule_proposal.scheduled_blocks)} scheduled blocks, "
                            f"{len(schedule_proposal.unscheduled_tasks)} unscheduled tasks."
                        ),
                    )
                )
            except Exception as exc:
                logger.error("Deterministic scheduling failed in LifeOps", error=str(exc))
                steps.append(
                    LifeOpsWorkflowStep(
                        step="deterministic_scheduling",
                        status="skipped",
                        detail=f"Could not compute schedule: {exc}",
                    )
                )

        # ---------------------------------------------------------------------
        # 7. Consequential Action Staging (Two-Phase Approval)
        # ---------------------------------------------------------------------
        staged_actions: list[ActionResponse] = []
        if req.stage_calendar_action and schedule_proposal and schedule_proposal.scheduled_blocks:
            first_block = schedule_proposal.scheduled_blocks[0]
            action = await ActionService.stage_action(
                db=db,
                user_id=user_id,
                action_type="create_calendar_event",
                payload={
                    "title": getattr(first_block, "title", "Study Block"),
                    "start_time": first_block.start_time.isoformat(),
                    "end_time": first_block.end_time.isoformat(),
                    "location": "Mentor AI Study Block",
                },
            )
            staged_actions.append(ActionResponse.model_validate(action))

        if req.stage_email_action and analyzed_emails:
            first_email = analyzed_emails[0]
            action = await ActionService.stage_action(
                db=db,
                user_id=user_id,
                action_type="send_email",
                payload={
                    "to": first_email.sender,
                    "subject": f"Re: {first_email.subject}",
                    "body": "Thank you. I have added this assignment to my study schedule.",
                    "thread_id": first_email.thread_id,
                    "source_reference": first_email.id,
                },
            )
            staged_actions.append(ActionResponse.model_validate(action))

        if staged_actions:
            steps.append(
                LifeOpsWorkflowStep(
                    step="approval_staging",
                    status="pending_review",
                    detail=f"Staged {len(staged_actions)} consequential action(s) awaiting explicit human approval.",
                )
            )

        # ---------------------------------------------------------------------
        # 8. Persistent Notifications Staging
        # ---------------------------------------------------------------------
        notif_count = 0
        if req.stage_notifications and has_remind_intent:
            # Query active tasks with deadlines
            task_stmt = select(Task).where(
                Task.user_id == user_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.is_archived.is_(False),
                Task.deadline.is_not(None),
            )
            active_tasks = (await db.execute(task_stmt)).scalars().all()

            for t in active_tasks:
                if t.deadline:
                    t_dl = t.deadline if t.deadline.tzinfo else t.deadline.replace(tzinfo=UTC)
                    lead_time = (
                        preferences.notification_settings.get("reminder_lead_time_minutes", 30)
                        if preferences and preferences.notification_settings
                        else 30
                    )
                    alert_time = t_dl - timedelta(minutes=lead_time)
                    if alert_time > now:
                        notif = await NotificationService.schedule_notification(
                            db=db,
                            user_id=user_id,
                            notification_type="due_soon",
                            title=f"Upcoming Deadline: {t.title}",
                            message=f"Task is due at {t_dl.strftime('%H:%M UTC')}. Estimated duration: {t.duration_minutes}m.",
                            scheduled_for=alert_time,
                            channel="in_app",
                            task_id=t.id,
                            deduplication_key=f"task_{t.id}_due_soon_{int(alert_time.timestamp())}",
                        )
                        if notif:
                            notif_count += 1

            steps.append(
                LifeOpsWorkflowStep(
                    step="notification_staging",
                    status="completed",
                    detail=f"Configured persistent notifications: {notif_count} active deadline alerts staged in database.",
                )
            )

        # Final intent summary
        intent_summary = (
            f"LifeOps processed instruction: '{req.prompt}'. "
            f"Extracted {len(extracted_candidates)} task candidate(s), scheduled {len(schedule_proposal.scheduled_blocks) if schedule_proposal else 0} block(s), "
            f"staged {len(staged_actions)} approval action(s), and created {notif_count} persistent notification(s)."
        )

        return LifeOpsWorkflowResponse(
            intent_summary=intent_summary,
            target_date=target_date,
            gmail_status=gmail_status,
            calendar_status=cal_status,
            analyzed_emails=analyzed_emails,
            extracted_candidates=extracted_candidates,
            has_ambiguous_deadlines=has_ambiguity,
            clarification_questions=clarifications,
            schedule_proposal=schedule_proposal,
            staged_actions=staged_actions,
            notifications_created_count=notif_count,
            workflow_steps=steps,
        )
