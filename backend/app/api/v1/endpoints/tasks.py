"""Task management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.task import (
    EnergyLevel,
    SortOrder,
    TaskAutoScheduleResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskPriority,
    TaskResponse,
    TaskSortBy,
    TaskStatus,
    TaskUpdateRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Creates a new task for the authenticated user with validated constraints and atomic audit record.",
)
async def create_task(
    payload: TaskCreateRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Create a task owned by the authenticated user."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.create_task(
        db=db,
        user_id=current_user.id,
        payload=payload,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.get(
    "",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter tasks",
    description="Retrieve paginated and filtered tasks owned strictly by the authenticated user.",
)
async def list_tasks(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[
        TaskStatus | None,
        Query(
            alias="status",
            description="Filter by status (pending, in_progress, completed, cancelled)",
        ),
    ] = None,
    priority_filter: Annotated[
        TaskPriority | None,
        Query(alias="priority", description="Filter by priority (P1, P2, P3, P4)"),
    ] = None,
    energy_level_filter: Annotated[
        EnergyLevel | None,
        Query(alias="energy_level", description="Filter by energy level (high, medium, low)"),
    ] = None,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Search term matching title or description"),
    ] = None,
    due_before: Annotated[
        datetime | None,
        Query(description="Filter tasks with deadline on or before this timestamp"),
    ] = None,
    due_after: Annotated[
        datetime | None,
        Query(description="Filter tasks with deadline on or after this timestamp"),
    ] = None,
    is_archived: Annotated[
        bool,
        Query(description="Whether to list archived tasks (defaults to false for active tasks)"),
    ] = False,
    is_overdue: Annotated[
        bool | None,
        Query(description="Filter tasks that are overdue (true) or upcoming (false)"),
    ] = None,
    sort_by: Annotated[
        TaskSortBy,
        Query(description="Field to sort by"),
    ] = "created_at",
    sort_order: Annotated[
        SortOrder,
        Query(description="Sort direction (asc or desc)"),
    ] = "desc",
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of items to return"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Offset for pagination"),
    ] = 0,
) -> TaskListResponse:
    """List filtered tasks with pagination."""
    tasks, total = await TaskService.list_tasks(
        db=db,
        user_id=current_user.id,
        status_filter=status_filter,
        priority_filter=priority_filter,
        energy_level_filter=energy_level_filter,
        search_query=search,
        due_before=due_before,
        due_after=due_after,
        is_archived=is_archived,
        is_overdue=is_overdue,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    items = [TaskResponse.model_validate(t) for t in tasks]
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve one task",
    description="Retrieve a single task by ID. Returns 404 if not found or owned by another user.",
)
async def get_task(
    task_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Retrieve a single task owned by the authenticated user."""
    task = await TaskService.get_task_by_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskResponse.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task partially",
    description="Update task fields including status transitions, duration, priority, and availability constraints.",
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Update task fields with lifecycle status transition validation."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.update_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        payload=payload,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Permanently remove a task and record an audit log entry. Returns 404 if not found or unauthorized.",
)
async def delete_task(
    task_id: uuid.UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a task owned by the authenticated user."""
    client_ip = request.client.host if request.client else None
    await TaskService.delete_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        client_ip=client_ip,
    )


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark task as completed",
    description="Convenience action to mark a task completed, validating permitted transition.",
)
async def complete_task(
    task_id: uuid.UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Mark task as completed."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.complete_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/reopen",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Reopen task",
    description="Convenience action to reopen a completed or cancelled task back to pending.",
)
async def reopen_task(
    task_id: uuid.UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Reopen a task."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.reopen_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/archive",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive task",
    description="Archive a task without deleting its historical records.",
)
async def archive_task(
    task_id: uuid.UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Archive a task."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.set_archive_status(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        is_archived=True,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/unarchive",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Unarchive task",
    description="Restore an archived task back to active list.",
)
async def unarchive_task(
    task_id: uuid.UUID,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Restore an archived task."""
    client_ip = request.client.host if request.client else None
    task = await TaskService.set_archive_status(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        is_archived=False,
        client_ip=client_ip,
    )
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/auto-schedule",
    response_model=TaskAutoScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="Auto-schedule a task",
    description="Deterministically allocates a working slot within available working hours before the deadline.",
)
async def auto_schedule_task_endpoint(
    task_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskAutoScheduleResponse:
    """Find and allocate an open working slot for the specified task."""
    task, success, message = await TaskService.auto_schedule_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskAutoScheduleResponse(
        task=TaskResponse.model_validate(task),
        scheduled=success,
        message=message,
    )


@router.post(
    "/{task_id}/sync-calendar",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync task to calendar",
    description="Synchronizes or retries synchronization of a scheduled task to Google Calendar.",
)
async def sync_task_calendar_endpoint(
    task_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Synchronize a scheduled task to Google Calendar."""
    task = await TaskService.sync_task_calendar(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskResponse.model_validate(task)
