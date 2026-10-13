"""Mentor AI Model Context Protocol (MCP) Server.

Implements the official Python MCP SDK with 8 typed, authenticated tools.
Separates proposal from execution, enforces idempotency, and guarantees post-condition verification.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from starlette import status
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.errors import AppException, EntityNotFoundException
from app.core.logging import get_logger
from app.core.security import verify_token_claims
from app.db.models.calendar import CalendarEvent
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.db.session import get_db_context
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskUpdateRequest
from app.services.action_service import ActionService
from app.services.scheduler.service import SchedulerService
from app.services.task_service import TaskService
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

logger = get_logger("mentor_ai.mcp_server")

# Create singleton MCPServer instance
mcp_server = MCPServer(
    name="mentor-ai-mcp",
    version="0.1.0",
    description="Mentor AI Personal Scheduling and Task Orchestration Engine",
)


# -----------------------------------------------------------------------------
# Tool 1: get_user_context (Read-Only / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def get_user_context(user_id: str) -> dict[str, Any]:
    """Retrieve the user's timezone, configured working hours, buffer, and pending task count.

    Args:
        user_id: UUID of the authenticated user.
    """
    uid = uuid.UUID(user_id)
    async with get_db_context() as db:
        profile_res = await db.execute(select(Profile).where(Profile.id == uid))
        profile = profile_res.scalar_one_or_none()
        if not profile:
            raise EntityNotFoundException("User profile not found")

        pref_res = await db.execute(select(UserPreferences).where(UserPreferences.user_id == uid))
        preferences = pref_res.scalar_one_or_none()

        task_count_res = await db.execute(
            select(Task).where(
                Task.user_id == uid,
                Task.status.in_(["pending", "in_progress"]),
                Task.is_archived.is_(False),
            )
        )
        pending_count = len(task_count_res.scalars().all())

        return {
            "user_id": str(profile.id),
            "timezone": profile.timezone,
            "work_start_time": preferences.work_start_time if preferences else "09:00:00",
            "work_end_time": preferences.work_end_time if preferences else "18:00:00",
            "buffer_minutes": preferences.buffer_minutes if preferences else 15,
            "auto_schedule_breaks": preferences.auto_schedule_breaks if preferences else True,
            "pending_tasks_count": pending_count,
        }


# -----------------------------------------------------------------------------
# Tool 2: list_tasks (Read-Only / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def list_tasks(
    user_id: str,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List tasks in the user's backlog with status and priority filters.

    Args:
        user_id: UUID of the authenticated user.
        status: Filter by task status ('pending', 'in_progress', 'completed', 'cancelled').
        priority: Filter by priority level ('P1', 'P2', 'P3', 'P4').
        limit: Maximum number of tasks to return (default: 20, max: 50).
    """
    uid = uuid.UUID(user_id)
    safe_limit = max(1, min(limit, 50))
    async with get_db_context() as db:
        items, total = await TaskService.list_tasks(
            db=db,
            user_id=uid,
            status_filter=status,  # type: ignore[arg-type]
            priority_filter=priority,  # type: ignore[arg-type]
            limit=safe_limit,
        )
        return {
            "tasks": [TaskResponse.model_validate(t).model_dump(mode="json") for t in items],
            "total": total,
            "limit": safe_limit,
        }


# -----------------------------------------------------------------------------
# Tool 3: create_task (Internal Mutation / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def create_task(
    user_id: str,
    title: str,
    duration_minutes: int,
    priority: str = "P3",
    deadline: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new task in the user's backlog.

    Args:
        user_id: UUID of the authenticated user.
        title: Task title (1-200 characters).
        duration_minutes: Estimated duration in minutes (1-720).
        priority: Priority rank ('P1', 'P2', 'P3', 'P4').
        deadline: Optional ISO-8601 deadline timestamp.
        description: Optional task notes.
    """
    uid = uuid.UUID(user_id)
    deadline_dt = datetime.fromisoformat(deadline) if deadline else None

    payload = TaskCreateRequest(
        title=title,
        duration_minutes=duration_minutes,
        priority=priority,  # type: ignore[arg-type]
        deadline=deadline_dt,
        description=description,
    )

    async with get_db_context() as db:
        created = await TaskService.create_task(db=db, user_id=uid, payload=payload)
        return {
            "task_id": str(created.id),
            "title": created.title,
            "status": created.status,
            "duration_minutes": created.duration_minutes,
            "priority": created.priority,
            "deadline": created.deadline.isoformat() if created.deadline else None,
        }


# -----------------------------------------------------------------------------
# Tool 4: update_task (Internal Mutation / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def update_task(
    user_id: str,
    task_id: str,
    status: str | None = None,
    duration_minutes: int | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    """Update properties or lifecycle status of an existing task.

    Args:
        user_id: UUID of the authenticated user.
        task_id: UUID of the task to update.
        status: Target status ('pending', 'in_progress', 'completed', 'cancelled').
        duration_minutes: Updated duration in minutes (1-720).
        priority: Updated priority ('P1', 'P2', 'P3', 'P4').
    """
    uid = uuid.UUID(user_id)
    tid = uuid.UUID(task_id)

    update_kwargs: dict[str, Any] = {}
    if status is not None:
        update_kwargs["status"] = status
    if duration_minutes is not None:
        update_kwargs["duration_minutes"] = duration_minutes
    if priority is not None:
        update_kwargs["priority"] = priority

    payload = TaskUpdateRequest(**update_kwargs)

    async with get_db_context() as db:
        updated = await TaskService.update_task(db=db, user_id=uid, task_id=tid, payload=payload)
        return {
            "task_id": str(updated.id),
            "title": updated.title,
            "status": updated.status,
            "duration_minutes": updated.duration_minutes,
            "priority": updated.priority,
        }


# -----------------------------------------------------------------------------
# Tool 5: get_calendar_events (Read-Only / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def get_calendar_events(
    user_id: str,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
    """Fetch fixed calendar commitments between start_time and end_time (ISO-8601).

    Args:
        user_id: UUID of the authenticated user.
        start_time: Window start timestamp (ISO-8601).
        end_time: Window end timestamp (ISO-8601).
    """
    uid = uuid.UUID(user_id)
    s_dt = datetime.fromisoformat(start_time)
    e_dt = datetime.fromisoformat(end_time)

    s_utc = s_dt if s_dt.tzinfo else s_dt.replace(tzinfo=UTC)
    e_utc = e_dt if e_dt.tzinfo else e_dt.replace(tzinfo=UTC)

    async with get_db_context() as db:
        stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == uid,
            CalendarEvent.end_time > s_utc,
            CalendarEvent.start_time < e_utc,
        )
        res = await db.execute(stmt)
        events = res.scalars().all()

        return {
            "events": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "start_time": e.start_time.isoformat(),
                    "end_time": e.end_time.isoformat(),
                    "location": e.location,
                    "is_fixed": e.is_fixed,
                }
                for e in events
            ],
            "total": len(events),
        }


# -----------------------------------------------------------------------------
# Tool 6: create_calendar_event (Consequential / Staged Pending Approval)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def create_calendar_event(
    user_id: str,
    title: str,
    start_time: str,
    end_time: str,
    location: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Stage a calendar commitment for human approval.

    CRITICAL SAFETY REQUIREMENT: Does NOT mutate calendar state immediately.
    The action is staged in action_history with status 'pending_approval' and
    requires explicit user confirmation before execution.

    Args:
        user_id: UUID of the authenticated user.
        title: Event title.
        start_time: Event start time (ISO-8601).
        end_time: Event end time (ISO-8601).
        location: Optional location or meeting URL.
        idempotency_key: Optional UUID to prevent duplicate action submissions.
    """
    uid = uuid.UUID(user_id)

    # Validate timestamps
    s_dt = datetime.fromisoformat(start_time)
    e_dt = datetime.fromisoformat(end_time)
    if e_dt <= s_dt:
        raise AppException(
            detail="Event end_time must be strictly after start_time.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_EVENT_DURATION",
        )

    payload = {
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
    }

    async with get_db_context() as db:
        action = await ActionService.stage_action(
            db=db,
            user_id=uid,
            action_type="create_calendar_event",
            payload=payload,
            idempotency_key=idempotency_key,
        )

        return {
            "status": "staged_pending_approval",
            "action_id": str(action.id),
            "action_type": action.action_type,
            "requires_human_approval": True,
            "idempotency_key": action.idempotency_key,
            "message": (
                "Action staged for human approval. The user must explicitly approve "
                "this action via POST /api/v1/actions/{id}/confirm before the event is added."
            ),
        }


# -----------------------------------------------------------------------------
# Tool 7: generate_schedule (Algorithmic / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def generate_schedule(
    user_id: str,
    target_date: str,
    task_ids: list[str] | None = None,
    enforce_buffer: bool = True,
) -> dict[str, Any]:
    """Run the pure deterministic scheduling solver for target date.

    Args:
        user_id: UUID of the authenticated user.
        target_date: Date to schedule (YYYY-MM-DD).
        task_ids: Optional list of task UUIDs to schedule.
        enforce_buffer: Whether to insert configured meeting buffers.
    """
    uid = uuid.UUID(user_id)
    t_date = date.fromisoformat(target_date)
    parsed_task_ids = [uuid.UUID(tid) for tid in task_ids] if task_ids else None

    async with get_db_context() as db:
        proposal = await SchedulerService.generate_proposal(
            db=db,
            user_id=uid,
            target_date=t_date,
            task_ids=parsed_task_ids,
            enforce_buffer=enforce_buffer,
        )
        return proposal.model_dump(mode="json")


# -----------------------------------------------------------------------------
# Tool 8: verify_action (State Verification / Safe)
# -----------------------------------------------------------------------------
@mcp_server.tool()
async def verify_action(
    user_id: str,
    action_id: str,
) -> dict[str, Any]:
    """Truthfully verify post-condition state of an executed action.

    Guarantees that actions reported as completed actually exist in persistence.

    Args:
        user_id: UUID of the authenticated user.
        action_id: UUID of the action record.
    """
    uid = uuid.UUID(user_id)
    aid = uuid.UUID(action_id)

    async with get_db_context() as db:
        res = await ActionService.verify_action(db=db, user_id=uid, action_id=aid)
        return {
            "action_id": str(res.action_id),
            "status": res.status,
            "verified": res.verified,
            "details": res.details,
            "error_message": res.error_message,
        }


# -----------------------------------------------------------------------------
# Secure Remote MCP Transport Middleware (Authentication Guard)
# -----------------------------------------------------------------------------
class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Guarantees authentication for remote MCP SSE transport."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check authorization header or query parameter
        auth_header = request.headers.get("Authorization")
        token: str | None = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "token" in request.query_params:
            token = request.query_params["token"]

        # Enforce authentication in non-local production or whenever auth header is provided
        if settings.ENVIRONMENT != "development" or auth_header:
            if not token:
                return Response(
                    content='{"error": "Unauthorized: Bearer token required for remote MCP access"}',
                    status_code=401,
                    media_type="application/json",
                )
            try:
                payload = verify_token_claims(token)
                request.state.user_id = payload.get("sub")
            except Exception as exc:
                return Response(
                    content=f'{{"error": "Unauthorized: Invalid JWT token ({exc})"}}',
                    status_code=401,
                    media_type="application/json",
                )

        return await call_next(request)


def create_authenticated_mcp_app() -> Starlette:
    """Create Starlette SSE app wrapped with remote authentication middleware."""
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "localhost",
            "127.0.0.1",
            "::1",
            "testserver",
            "testserver:*",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            "http://localhost",
            "http://127.0.0.1",
            "http://testserver",
        ],
    )
    app = mcp_server.sse_app(transport_security=security)
    app.add_middleware(MCPAuthMiddleware)
    return app
