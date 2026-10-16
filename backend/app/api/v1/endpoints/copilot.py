"""Copilot API endpoints for conversational educational guidance, schedule intelligence, and voice assistant."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.copilot import (
    CopilotActionConfirmRequest,
    CopilotActionConfirmResponse,
    CopilotMessageRequest,
    CopilotResponse,
    CopilotScheduleSummary,
    StudentAccountabilitySummary,
)
from app.services.copilot.accountability import StudentAccountabilityService
from app.services.copilot.email_copilot import CopilotEmailService
from app.services.copilot.service import CopilotService
from app.services.copilot.tools import get_today_schedule, resolve_user_timezone

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post(
    "/message",
    response_model=CopilotResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit natural language or voice transcript to Mentor Educational Copilot",
)
async def process_copilot_message(
    payload: CopilotMessageRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotResponse:
    """Orchestrate schedule intelligence, educational resource search, email drafting, or programming tutoring."""
    return await CopilotService.process_message(
        db=db,
        user_id=current_user.id,
        req=payload,
    )


@router.post(
    "/action/confirm",
    response_model=CopilotActionConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an explicitly confirmed consequential Copilot action (e.g. send approved email)",
)
async def confirm_copilot_action(
    payload: CopilotActionConfirmRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotActionConfirmResponse:
    """Execute action only after user has reviewed and explicitly approved the preview."""
    if payload.action_type == "send_email":
        data = payload.email_payload or {}
        recipient = data.get("recipient_email") or data.get("to")
        subject = data.get("subject", "")
        body = data.get("body", "")
        thread_id = data.get("thread_id")

        if not recipient or not body:
            return CopilotActionConfirmResponse(
                success=False,
                action_type="send_email",
                result_message="Missing recipient email address or message body.",
            )

        success, message, details = await CopilotEmailService.send_confirmed_email(
            db=db,
            user_id=current_user.id,
            recipient_email=recipient,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )
        return CopilotActionConfirmResponse(
            success=success,
            action_type="send_email",
            result_message=message,
            details=details,
        )

    return CopilotActionConfirmResponse(
        success=False,
        action_type=payload.action_type,
        result_message=f"Unsupported action type: {payload.action_type}",
    )


@router.get(
    "/schedule/today",
    response_model=CopilotScheduleSummary,
    status_code=status.HTTP_200_OK,
    summary="Direct deterministic today schedule intelligence lookup",
)
async def get_copilot_today_schedule(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    timezone: Annotated[str | None, Query(description="Client IANA timezone")] = None,
) -> CopilotScheduleSummary:
    """Retrieve today's schedule, deadlines, and next action in user timezone without LLM dependency."""
    user_tz = await resolve_user_timezone(db, current_user.id, timezone or "Asia/Dhaka")
    return await get_today_schedule(db=db, user_id=current_user.id, user_tz_str=user_tz)


@router.get(
    "/accountability",
    response_model=StudentAccountabilitySummary,
    status_code=status.HTTP_200_OK,
    summary="Retrieve student consistency metrics, streak days, and recovery recommendations",
)
async def get_copilot_accountability(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentAccountabilitySummary:
    """Calculate streak and supportive recovery guidance."""
    return await StudentAccountabilityService.get_accountability_summary(
        db=db, user_id=current_user.id
    )


@router.post(
    "/accountability/evaluate",
    status_code=status.HTTP_200_OK,
    summary="Trigger evaluation of ended scheduled sessions for supportive notifications",
)
async def evaluate_missed_sessions(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Check for ended schedule blocks with incomplete tasks and queue non-punitive notifications."""
    created = await StudentAccountabilityService.evaluate_missed_sessions(
        db=db, user_id=current_user.id
    )
    return {
        "status": "evaluated",
        "new_notifications_count": len(created),
    }
