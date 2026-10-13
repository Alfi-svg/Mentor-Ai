"""Action approval, execution, and verification API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.action import (
    ActionConfirmRequest,
    ActionConfirmResponse,
    ActionResponse,
    ActionVerifyResponse,
)
from app.services.action_service import ActionService

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get(
    "/pending",
    response_model=list[ActionResponse],
    status_code=status.HTTP_200_OK,
    summary="List staged actions awaiting user confirmation",
)
async def list_pending_actions(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ActionResponse]:
    """Retrieve all actions staged in pending_approval status for the current user."""
    return await ActionService.list_pending_actions(db=db, user_id=current_user.id)


@router.get(
    "/history",
    response_model=list[ActionResponse],
    status_code=status.HTTP_200_OK,
    summary="List action history for current user",
)
async def list_action_history(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[ActionResponse]:
    """Retrieve action records across pending, completed, failed, and rejected states."""
    return await ActionService.list_action_history(
        db=db, user_id=current_user.id, limit=limit, offset=offset
    )


@router.post(
    "/{id}/confirm",
    response_model=ActionConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm or reject a staged consequential action",
)
async def confirm_action(
    id: uuid.UUID,
    payload: ActionConfirmRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActionConfirmResponse:
    """Explicit human approval decision. If confirmed, executes and verifies state changes."""
    client_ip = request.client.host if request.client else None
    return await ActionService.confirm_action(
        db=db,
        user_id=current_user.id,
        action_id=id,
        confirmed=payload.confirmed,
        rejection_reason=payload.rejection_reason,
        client_ip=client_ip,
    )


@router.get(
    "/{id}/verify",
    response_model=ActionVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify post-condition state of an executed action",
)
async def verify_action(
    id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActionVerifyResponse:
    """Check post-condition state in database or external calendar to guarantee truthfulness."""
    return await ActionService.verify_action(
        db=db,
        user_id=current_user.id,
        action_id=id,
    )
