"""Notification management, preference configuration, and secured persistent dispatch endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user, get_optional_current_user
from app.db.session import get_db
from app.schemas.notification import (
    NotificationDispatchResponse,
    NotificationEvaluationResult,
    NotificationResponse,
    NotificationSettingsSchema,
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
    channel: str | None = Query(default=None, description="Filter by delivery channel (in_app, email, browser_push)"),
    limit: int = Query(default=50, ge=1, le=100, description="Max notifications to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> list[NotificationResponse]:
    """List current user notifications."""
    notifs = await NotificationService.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        channel=channel,
        limit=limit,
        offset=offset,
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


@router.get(
    "/preferences",
    response_model=NotificationSettingsSchema,
    summary="Get notification preferences",
    description="Returns notification preferences, reminder lead time, and quiet hours.",
)
async def get_notification_preferences(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsSchema:
    """Get user notification preferences."""
    return await NotificationService.get_user_notification_settings(
        db=db, user_id=current_user.id
    )


@router.put(
    "/preferences",
    response_model=NotificationSettingsSchema,
    summary="Update notification preferences",
    description="Updates notification preferences, reminder lead time, and quiet hours.",
)
async def update_notification_preferences(
    settings_update: NotificationSettingsSchema,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsSchema:
    """Update user notification preferences."""
    return await NotificationService.update_user_notification_settings(
        db=db, user_id=current_user.id, settings_update=settings_update
    )


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


@router.post(
    "/dispatch",
    response_model=NotificationDispatchResponse,
    summary="Execute persistent notification dispatch",
    description=(
        "Processes due notifications across all users via PostgreSQL batch claiming with skip locked. "
        "Secured via X-Dispatch-Secret header with constant-time verification."
    ),
)
async def dispatch_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_dispatch_secret: Annotated[str | None, Header(alias="X-Dispatch-Secret")] = None,
    authorization: Annotated[str | None, Header()] = None,
    batch_size: int = Query(default=50, ge=1, le=200, description="Max notifications to claim and process"),
) -> NotificationDispatchResponse:
    """Secured background dispatcher entry point."""
    token: str | None = None
    if x_dispatch_secret:
        token = x_dispatch_secret
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    is_authorized = NotificationService.verify_dispatch_secret(token)
    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-Dispatch-Secret header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return await NotificationService.dispatch_due_notifications(db=db, batch_size=batch_size)
