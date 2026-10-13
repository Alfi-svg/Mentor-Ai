"""Chat API endpoint matching docs/API_CONTRACT.md section 2.6."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.planner import PlanGenerateRequest, PlanProposalResponse
from app.services.planner_service import PlannerService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/message",
    response_model=PlanProposalResponse,
    status_code=status.HTTP_200_OK,
    summary="Natural language chat message to generate or inspect plan proposals",
)
async def chat_message(
    payload: PlanGenerateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanProposalResponse:
    """Submit natural-language instruction and receive a structured plan proposal with preview schedule."""
    return await PlannerService.generate_draft_plan(
        db=db,
        user_id=current_user.id,
        req=payload,
    )
