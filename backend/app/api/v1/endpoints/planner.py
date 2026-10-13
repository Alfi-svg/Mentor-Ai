"""Planner API endpoints for draft generation and explicit confirmation."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.rate_limit import rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.planner import (
    PlanConfirmRequest,
    PlanConfirmResponse,
    PlanGenerateRequest,
    PlanProposalResponse,
)
from app.services.planner_service import PlannerService

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post(
    "/draft",
    response_model=PlanProposalResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate structured plan proposal from natural language",
)
async def generate_draft_plan(
    payload: PlanGenerateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: None = Depends(
        rate_limit(max_requests=30, window_seconds=60, key_prefix="planner")
    ),
) -> PlanProposalResponse:
    """Accept natural language instruction, extract structured draft, detect missing info, and preview schedule.

    This endpoint NEVER mutates the database or executes actions without prior confirmation.
    """
    return await PlannerService.generate_draft_plan(
        db=db,
        user_id=current_user.id,
        req=payload,
    )


@router.post(
    "/confirm",
    response_model=PlanConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm proposed plan, persist tasks, and run deterministic scheduler",
)
async def confirm_plan(
    payload: PlanConfirmRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanConfirmResponse:
    """Persist confirmed tasks and fixed events, then allocate schedule blocks via Day 5 solver."""
    client_ip = request.client.host if request.client else None
    return await PlannerService.confirm_plan(
        db=db,
        user_id=current_user.id,
        req=payload,
        client_ip=client_ip,
    )
