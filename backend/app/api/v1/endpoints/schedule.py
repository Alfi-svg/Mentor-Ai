"""Deterministic smart scheduler API endpoints."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import EntityNotFoundException
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.services.scheduler.models import (
    ScheduleBlockProposal,
    ScheduleProposal,
    ScheduleValidationResult,
    TimeInterval,
)
from app.services.scheduler.service import SchedulerService
from app.services.scheduler.validator import validate_schedule

router = APIRouter(prefix="/schedule", tags=["schedule"])


class GenerateScheduleRequest(BaseModel):
    """Payload to request deterministic schedule generation."""

    target_date: date = Field(
        description="Target calendar date to schedule (YYYY-MM-DD)",
        examples=["2026-10-15"],
    )
    task_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Explicit list of task IDs to schedule. If omitted, schedules active pending tasks.",
    )
    enforce_buffer: bool = Field(
        default=True,
        description="Whether to enforce transition buffers around fixed commitments.",
    )
    override_timezone: str | None = Field(
        default=None,
        description="Optional timezone override (e.g. 'America/New_York'). Defaults to user profile timezone.",
    )


class ValidateScheduleRequest(BaseModel):
    """Payload to test and validate arbitrary schedule blocks against constraints."""

    blocks: list[ScheduleBlockProposal]
    working_interval: TimeInterval


@router.post(
    "/generate",
    response_model=ScheduleProposal,
    status_code=status.HTTP_200_OK,
    summary="Generate deterministic schedule proposal",
    description="Calculates a conflict-free, mathematically verified schedule proposal using deterministic interval algebra.",
)
async def generate_schedule(
    payload: GenerateScheduleRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleProposal:
    """Generate deterministic schedule proposal."""
    return await SchedulerService.generate_proposal(
        db=db,
        user_id=current_user.id,
        target_date=payload.target_date,
        task_ids=payload.task_ids,
        enforce_buffer=payload.enforce_buffer,
        override_timezone=payload.override_timezone,
    )


@router.post(
    "/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve and persist schedule proposal",
    description="Validates and persists an approved schedule into database tables, superseding previous schedules for the target date.",
)
async def approve_schedule(
    proposal: ScheduleProposal,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Persist an approved schedule proposal to database."""
    client_ip = request.client.host if request.client else None
    schedule = await SchedulerService.persist_approved_schedule(
        db=db,
        user_id=current_user.id,
        proposal=proposal,
        client_ip=client_ip,
    )
    return {
        "schedule_id": str(schedule.id),
        "target_date": str(schedule.schedule_date),
        "status": schedule.status,
        "message": "Schedule approved, validated, and persisted successfully.",
    }


@router.get(
    "/{target_date}",
    status_code=status.HTTP_200_OK,
    summary="Get active schedule for date",
    description="Retrieve the active, accepted schedule and its blocks for a specific date.",
)
async def get_schedule_for_date(
    target_date: date,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Retrieve active schedule for the date."""
    schedule = await SchedulerService.get_schedule_for_date(
        db=db,
        user_id=current_user.id,
        target_date=target_date,
    )
    if not schedule:
        raise EntityNotFoundException(
            detail=f"No active accepted schedule found for {target_date}."
        )

    blocks = [
        {
            "id": str(b.id),
            "task_id": str(b.task_id) if b.task_id else None,
            "calendar_event_id": str(b.calendar_event_id) if b.calendar_event_id else None,
            "title": b.title,
            "start_time": b.start_time.isoformat(),
            "end_time": b.end_time.isoformat(),
            "block_type": b.block_type,
            "is_completed": b.is_completed,
        }
        for b in schedule.blocks
    ]

    return {
        "schedule_id": str(schedule.id),
        "target_date": str(schedule.schedule_date),
        "status": schedule.status,
        "metadata": schedule.metadata_json,
        "blocks": blocks,
    }


@router.post(
    "/validate",
    response_model=ScheduleValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Validate schedule blocks directly",
    description="Executes pure mathematical schedule validation on proposed blocks without database mutations.",
)
async def validate_schedule_blocks(
    payload: ValidateScheduleRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ScheduleValidationResult:
    """Validate schedule blocks against working window and non-overlap rules."""
    return validate_schedule(
        blocks=payload.blocks,
        working_interval=payload.working_interval,
    )
