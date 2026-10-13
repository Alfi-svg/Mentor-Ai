"""Notification management and evaluation endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.notification import (
    NotificationEvaluationResult,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=list[NotificationResponse],
    summary="List notifications",
    description="Returns notifications for the current authenticated user.",
)
async def list_notifications(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = Query(default=False, description="Filter for unread notifications only"),
    limit: int = Query(default=50, ge=1, le=100, description="Max notifications to return"),
) -> list[NotificationResponse]:
    """List current user notifications."""
    notifs = await NotificationService.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
    )
    return [NotificationResponse.model_validate(n) for n in notifs]


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="Get unread notification count",
    description="Returns count of unread notifications for the user.",
)
async def get_unread_count(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationUnreadCountResponse:
    """Get unread notifications count."""
    count = await NotificationService.get_unread_count(db=db, user_id=current_user.id)
    return NotificationUnreadCountResponse(unread_count=count)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
    description="Marks a specific notification as read.",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Mark a notification as read."""
    notif = await NotificationService.mark_as_read(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return NotificationResponse.model_validate(notif)


@router.post(
    "/read-all",
    summary="Mark all notifications as read",
    description="Marks all unread notifications as read for current user.",
)
async def mark_all_read(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Mark all notifications as read."""
    count = await NotificationService.mark_all_as_read(db=db, user_id=current_user.id)
    return {"marked_as_read": count}


@router.post(
    "/evaluate",
    response_model=NotificationEvaluationResult,
    summary="Evaluate task deadlines",
    description="Evaluates all active tasks with deadlines and generates due_soon, due_now, and overdue alerts.",
)
async def evaluate_notifications(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationEvaluationResult:
    """Evaluate task deadlines and create notifications."""
    total_evaluated, new_notifs = await NotificationService.evaluate_user_notifications(
        db=db,
        user_id=current_user.id,
    )
    return NotificationEvaluationResult(
        evaluated_tasks_count=total_evaluated,
        new_notifications_count=len(new_notifs),
        notifications=[NotificationResponse.model_validate(n) for n in new_notifs],
    )
