"""Calendar endpoints for connection, OAuth callback, synchronization, and conflict checking."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.db.models.calendar import CalendarEvent
from app.db.session import get_db
from app.services.calendar.models import (
    CalendarConnectResponse,
    CalendarStatusResponse,
    CalendarSyncResponse,
    ConflictCheckResponse,
)
from app.services.calendar.service import CalendarService

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
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="Signed CSRF state parameter"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Exchange authorization code and activate external connection."""
    conn, email = await CalendarService.handle_callback(code=code, state=state, db=db)
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


@router.get(
    "/events",
    summary="List Calendar Events",
    description="Retrieves normalized calendar events for the user within a time window.",
)
async def list_calendar_events(
    start_time: datetime | None = Query(
        default=None, description="Start timestamp (default: start of today)"
    ),
    end_time: datetime | None = Query(default=None, description="End timestamp (default: +7 days)"),
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

    return [
        {
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
        }
        for e in events
    ]


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
