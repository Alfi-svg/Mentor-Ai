"""Schemas for the unified LifeOps workflow orchestrator."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.action import ActionResponse
from app.services.calendar.models import CalendarStatusResponse
from app.services.gmail.models import EmailTaskCandidate, GmailMessageSummary, GmailStatusResponse
from app.services.scheduler.models import ScheduleProposal


class LifeOpsPlanRequest(BaseModel):
    """Payload to trigger the full multi-intent LifeOps pipeline."""

    prompt: str = Field(min_length=1, description="Natural-language lifeops instruction from text or voice")
    target_date: date | None = Field(default=None, description="Target planning date (YYYY-MM-DD)")
    client_timezone: str = Field(default="UTC", description="Client IANA timezone")
    auto_extract_emails: bool = Field(default=True, description="Whether to query and analyze emails")
    email_query: str | None = Field(default=None, description="Optional search query filter for Gmail")
    confirmed_tasks: list[dict[str, Any]] | None = Field(
        default=None, description="Optional pre-approved tasks to persist and schedule"
    )
    stage_calendar_action: bool = Field(default=False, description="Stage fixed commitments into action_history")
    stage_email_action: bool = Field(default=False, description="Stage reply or summary email into action_history")
    stage_notifications: bool = Field(default=True, description="Persist deadline reminders into notifications table")


class LifeOpsWorkflowStep(BaseModel):
    """Execution progress metric for each phase of the LifeOps pipeline."""

    step: str
    status: str  # completed, requires_clarification, pending_review, skipped
    detail: str


class LifeOpsWorkflowResponse(BaseModel):
    """Unified response consolidating all stages of the LifeOps pipeline."""

    intent_summary: str
    target_date: date
    gmail_status: GmailStatusResponse
    calendar_status: CalendarStatusResponse
    analyzed_emails: list[GmailMessageSummary] = Field(default_factory=list)
    extracted_candidates: list[EmailTaskCandidate] = Field(default_factory=list)
    has_ambiguous_deadlines: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    schedule_proposal: ScheduleProposal | None = None
    staged_actions: list[ActionResponse] = Field(default_factory=list)
    notifications_created_count: int = 0
    workflow_steps: list[LifeOpsWorkflowStep] = Field(default_factory=list)
