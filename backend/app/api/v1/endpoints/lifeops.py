"""LifeOps API endpoint orchestrating text and voice instructions into end-to-end workflows."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.lifeops import LifeOpsPlanRequest, LifeOpsWorkflowResponse
from app.services.lifeops_service import LifeOpsService

router = APIRouter(prefix="/lifeops", tags=["lifeops"])


@router.post(
    "/workflow",
    response_model=LifeOpsWorkflowResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Unified LifeOps Workflow",
    description=(
        "Executes end-to-end LifeOps pipeline: Intent Understanding -> Task Extraction -> "
        "Constraint Validation -> Calendar Availability -> Deterministic Scheduling -> "
        "User Review -> Explicit Approval Staging -> Persistent Notification."
    ),
)
async def execute_lifeops_workflow(
    req: LifeOpsPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LifeOpsWorkflowResponse:
    """Execute full LifeOps lifecycle for the authenticated user."""
    return await LifeOpsService.execute_workflow(
        user_id=current_user.id,
        req=req,
        db=db,
    )
