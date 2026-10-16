import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppException
from app.core.security import AuthenticatedUser, get_current_user
from app.db.models.calendar import CalendarEvent
from app.db.models.task import Task
from app.db.session import get_db
from app.services.calendar.models import (
    CalendarConnectResponse,
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarStatusResponse,
    CalendarSyncResponse,
    ConflictCheckResponse,
)
from app.services.calendar.service import CalendarService
from app.services.calendar_sync_service import CalendarSyncService

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get(
    "/status",
    response_model=CalendarStatusResponse,
    summary="Calendar Connection Status",
    description="Returns whether the user has a connected external calendar provider truthfully.",
)
async def get_calendar_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarStatusResponse:
    """Check connection status for current user."""
    return await CalendarService.get_status(user_id=current_user.id, db=db)


@router.get(
    "/connect",
    response_model=CalendarConnectResponse,
    summary="Initiate Calendar Connection",
    description="Generates an OAuth authorization URL with signed CSRF state token.",
)
async def connect_calendar(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CalendarConnectResponse:
    """Generate signed OAuth authorization URL."""
    return await CalendarService.get_connect_url(user_id=current_user.id)


@router.get(
    "/callback",
    summary="OAuth Callback",
    description="Handles Google OAuth redirect, validates CSRF state, and stores encrypted tokens.",
)
async def oauth_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None, description="Authorization code from OAuth provider"),
    state: str | None = Query(default=None, description="Signed CSRF state parameter"),
    error: str | None = Query(default=None, description="Error code from OAuth provider"),
    error_description: str | None = Query(default=None, description="Error description from OAuth provider"),
) -> Any:
    """Exchange authorization code and activate external connection."""
    accept_header = request.headers.get("accept", "")
    is_browser_nav = "text/html" in accept_header and "application/json" not in accept_header

    # Handle provider denial or error (e.g. user clicked Cancel on Google consent screen)
    if error:
        err_msg = error_description or error or "OAuth authorization was denied or cancelled."
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/calendar?error={quote_plus(error)}&error_description={quote_plus(err_msg)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_ACCESS_DENIED",
            detail=f"Google Calendar authorization was denied: {err_msg}",
        )

    if not code or not state:
        err_msg = "Missing required OAuth authorization code or state token."
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/calendar?error=missing_parameters&error_description={quote_plus(err_msg)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_MISSING_PARAMETERS",
            detail=err_msg,
        )

    try:
        conn, email = await CalendarService.handle_callback(code=code, state=state, db=db)
    except AppException as exc:
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/calendar?error={quote_plus(exc.error_code)}&error_description={quote_plus(exc.detail)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise
    except Exception as exc:
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/calendar?error=callback_failed&error_description={quote_plus(str(exc))}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_CALLBACK_FAILED",
            detail=f"Failed to complete Google Calendar authentication: {exc}",
        )

    if is_browser_nav:
        email_param = f"&email={quote_plus(email)}" if email else ""
        dest = f"{settings.FRONTEND_URL}/settings/calendar?connected=true{email_param}"
        return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)

    return {
        "status": "connected",
        "provider": conn.provider,
        "account_email": email,
        "connected_at": conn.created_at.isoformat(),
    }


@router.post(
    "/disconnect",
    summary="Disconnect Calendar",
    description="Revokes access with provider and removes stored tokens.",
)
async def disconnect_calendar(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke tokens and disconnect calendar."""
    await CalendarService.disconnect(user_id=current_user.id, db=db)
    return {
        "status": "disconnected",
        "provider": "google_calendar",
        "message": "Calendar connection has been successfully disconnected.",
    }


class CreateEventRequest(BaseModel):
    """Payload to create an event on calendar."""

    title: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    is_all_day: bool = False


class UpdateEventRequest(BaseModel):
    """Payload to update an existing event on calendar."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_time: datetime | None = None
    end_time: datetime | None = None
    description: str | None = None
    location: str | None = None
    is_all_day: bool | None = None


@router.get(
    "/events",
    summary="List Calendar Events",
    description="Retrieves normalized calendar events and scheduled tasks for the user within a time window.",
)
async def list_calendar_events(
    start_time: datetime | None = Query(
        default=None, description="Start timestamp (default: start of today)"
    ),
    end_time: datetime | None = Query(default=None, description="End timestamp (default: +7 days)"),
    include_tasks: bool = Query(default=True, description="Whether to include scheduled tasks"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List calendar events in time window."""
    now = datetime.now(UTC)
    start_dt = (
        start_time.astimezone(UTC)
        if start_time
        else now.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    end_dt = end_time.astimezone(UTC) if end_time else start_dt + timedelta(days=7)

    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.start_time < end_dt,
            CalendarEvent.end_time > start_dt,
        )
        .order_by(CalendarEvent.start_time.asc())
    )

    res = await db.execute(stmt)
    events = list(res.scalars().all())

    # Map existing external_ids in CalendarEvent to avoid duplicate task items
    ext_id_to_event_idx: dict[str, int] = {}
    formatted_items: list[dict[str, Any]] = []

    for idx, e in enumerate(events):
        item = {
            "id": str(e.id),
            "external_id": e.external_id,
            "title": e.title,
            "description": e.description,
            "start_time": e.start_time.isoformat(),
            "end_time": e.end_time.isoformat(),
            "is_all_day": e.is_all_day,
            "is_fixed": e.is_fixed,
            "source": e.source,
            "location": e.location,
            "task_id": None,
            "priority": None,
            "task_status": None,
        }
        if e.external_id:
            ext_id_to_event_idx[e.external_id] = idx
        formatted_items.append(item)

    if include_tasks:
        task_stmt = (
            select(Task)
            .where(
                Task.user_id == current_user.id,
                Task.is_archived.is_(False),
                Task.scheduled_start.isnot(None),
                Task.scheduled_end.isnot(None),
                Task.scheduled_start < end_dt,
                Task.scheduled_end > start_dt,
            )
            .order_by(Task.scheduled_start.asc())
        )
        task_res = await db.execute(task_stmt)
        tasks = list(task_res.scalars().all())

        for t in tasks:
            if t.google_calendar_event_id and t.google_calendar_event_id in ext_id_to_event_idx:
                # Event already present from Google Calendar sync; enrich with task metadata
                ev_idx = ext_id_to_event_idx[t.google_calendar_event_id]
                formatted_items[ev_idx]["task_id"] = str(t.id)
                formatted_items[ev_idx]["priority"] = t.priority
                formatted_items[ev_idx]["task_status"] = t.status
            else:
                # Add scheduled task as a calendar item
                formatted_items.append(
                    {
                        "id": f"task_{t.id}",
                        "external_id": t.google_calendar_event_id,
                        "title": t.title,
                        "description": t.description,
                        "start_time": t.scheduled_start.isoformat(),  # type: ignore
                        "end_time": t.scheduled_end.isoformat(),      # type: ignore
                        "is_all_day": False,
                        "is_fixed": False,
                        "source": "task",
                        "location": None,
                        "task_id": str(t.id),
                        "priority": t.priority,
                        "task_status": t.status,
                        "calendar_sync_status": t.calendar_sync_status,
                    }
                )

    # Sort final combined list by start_time
    formatted_items.sort(key=lambda x: x["start_time"])
    return formatted_items


@router.post(
    "/events",
    status_code=status.HTTP_201_CREATED,
    summary="Create Calendar Event",
    description="Creates a new calendar event locally and on Google Calendar if connected.",
)
async def create_calendar_event(
    payload: CreateEventRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new calendar event."""
    if payload.end_time <= payload.start_time:
        raise AppException(
            detail="end_time must be strictly after start_time",
            status_code=400,
            error_code="INVALID_TIME_RANGE",
        )

    create_data = CalendarEventCreate(
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
        is_all_day=payload.is_all_day,
    )
    event, pushed = await CalendarService.create_calendar_event(
        user_id=current_user.id,
        event_data=create_data,
        db=db,
    )
    return {
        "id": str(event.id),
        "external_id": event.external_id,
        "title": event.title,
        "description": event.description,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "is_all_day": event.is_all_day,
        "is_fixed": event.is_fixed,
        "source": event.source,
        "location": event.location,
        "pushed_to_remote": pushed,
    }


@router.patch(
    "/events/{event_id}",
    summary="Update Calendar Event",
    description="Updates title, time, or notes for a calendar event locally and on Google Calendar.",
)
async def update_calendar_event(
    event_id: uuid.UUID,
    payload: UpdateEventRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update calendar event fields."""
    if payload.start_time and payload.end_time and payload.end_time <= payload.start_time:
        raise AppException(
            detail="end_time must be strictly after start_time",
            status_code=400,
            error_code="INVALID_TIME_RANGE",
        )

    update_data = CalendarEventUpdate(
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
        is_all_day=payload.is_all_day,
    )
    updated = await CalendarService.update_calendar_event(
        user_id=current_user.id,
        event_id=event_id,
        event_data=update_data,
        db=db,
    )
    return {
        "id": str(updated.id),
        "external_id": updated.external_id,
        "title": updated.title,
        "description": updated.description,
        "start_time": updated.start_time.isoformat(),
        "end_time": updated.end_time.isoformat(),
        "is_all_day": updated.is_all_day,
        "is_fixed": updated.is_fixed,
        "source": updated.source,
        "location": updated.location,
    }


@router.delete(
    "/events/{event_id}",
    summary="Delete Calendar Event",
    description="Deletes a calendar event locally and from Google Calendar.",
)
async def delete_calendar_event(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete a calendar event."""
    success = await CalendarService.delete_calendar_event(
        user_id=current_user.id,
        event_id=event_id,
        db=db,
    )
    return {"deleted": success, "id": str(event_id)}


@router.post(
    "/sync/tasks",
    summary="Synchronize Tasks with Google Calendar",
    description="Triggers synchronization and retries any failed or pending task calendar appointments.",
)
async def sync_tasks_to_calendar(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Sync unsynced/pending scheduled tasks to Google Calendar."""
    return await CalendarSyncService.sync_pending_tasks(db=db, user_id=current_user.id)


@router.get(
    "/sync/tasks",
    summary="Get Task Calendar Sync Status",
    description="Returns aggregate counts of synced, pending, failed, and unsynced scheduled tasks.",
)
async def get_task_sync_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve task sync metrics for current user."""
    stmt = (
        select(Task.calendar_sync_status, func.count(Task.id))
        .where(
            Task.user_id == current_user.id,
            Task.is_archived.is_(False),
            Task.scheduled_start.isnot(None),
        )
        .group_by(Task.calendar_sync_status)
    )
    res = await db.execute(stmt)
    counts = dict(res.all())
    return {
        "synced": counts.get("synced", 0),
        "pending": counts.get("pending", 0),
        "failed": counts.get("failed", 0),
        "unsynced": counts.get("unsynced", 0),
        "total_scheduled": sum(counts.values()),
    }


@router.post(
    "/sync",
    response_model=CalendarSyncResponse,
    summary="Synchronize Calendar Events",
    description="Pulls remote events from the connected provider and updates the database.",
)
async def sync_calendar(
    days_back: int = Query(default=7, ge=0, le=30),
    days_forward: int = Query(default=14, ge=1, le=90),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarSyncResponse:
    """Pull remote events and store normalized records."""
    now = datetime.now(UTC)
    start_dt = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = (now + timedelta(days=days_forward)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    return await CalendarService.sync_events(
        user_id=current_user.id,
        start_time=start_dt,
        end_time=end_dt,
        db=db,
    )


@router.get(
    "/conflicts",
    response_model=ConflictCheckResponse,
    summary="Detect Scheduling Conflicts",
    description="Identifies busy blocks and available free slots on a given date.",
)
async def check_conflicts(
    target_date: date = Query(..., description="Target date to analyze (YYYY-MM-DD)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConflictCheckResponse:
    """Identify conflicts and free slots for target date."""
    return await CalendarService.detect_conflicts(
        user_id=current_user.id,
        target_date=target_date,
        db=db,
    )
