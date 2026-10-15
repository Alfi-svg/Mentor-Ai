"""Task service handling business logic, status transitions, and audit records."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppException, EntityNotFoundException
from app.core.logging import get_logger
from app.db.models.action import AuditLog
from app.db.models.task import Task
from app.schemas.task import (
    SortOrder,
    TaskCreateRequest,
    TaskPriority,
    TaskSortBy,
    TaskStatus,
    TaskUpdateRequest,
)
from app.services.notification_service import NotificationService

logger = get_logger("mentor_ai.task_service")

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"pending", "in_progress", "completed", "cancelled"},
    "in_progress": {"in_progress", "pending", "completed", "cancelled"},
    "completed": {"completed", "pending", "in_progress"},
    "cancelled": {"cancelled", "pending"},
}


def validate_status_transition(current_status: str, target_status: str) -> None:
    """Validate lifecycle status transitions according to state machine rules."""
    allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise AppException(
            detail=(
                f"Invalid status transition from '{current_status}' to '{target_status}'. "
                f"Permitted transitions from '{current_status}': {sorted(allowed)}."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_STATUS_TRANSITION",
        )


class TaskService:
    """Task domain service managing persistence, authorization, and audit logging."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: TaskCreateRequest,
        client_ip: str | None = None,
    ) -> Task:
        """Create a new task and record an audit log entry in an atomic transaction."""
        task = Task(
            id=uuid.uuid4(),
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            duration_minutes=payload.duration_minutes,
            deadline=payload.deadline,
            energy_level=payload.energy_level,
            tags=payload.tags,
            constraints=payload.constraints,
            is_archived=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="task_created",
            resource_type="task",
            resource_id=str(task.id),
            details={
                "title": task.title,
                "priority": task.priority,
                "duration_minutes": task.duration_minutes,
                "status": task.status,
            },
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        db.add(task)
        db.add(audit_entry)
        await db.commit()
        await db.refresh(task)

        if task.deadline:
            await NotificationService.reconcile_task_lifecycle(
                db=db, user_id=user_id, task=task, event="task_deadline_changed"
            )

        logger.info(
            "Task created",
            task_id=str(task.id),
            user_id=str(user_id),
            title=task.title,
            priority=task.priority,
        )
        return task

    @staticmethod
    async def get_task_by_id(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> Task:
        """Retrieve a single task strictly scoped to the requesting user."""
        stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if task is None:
            raise EntityNotFoundException(detail=f"Task '{task_id}' was not found.")
        return task

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        user_id: uuid.UUID,
        status_filter: TaskStatus | None = None,
        priority_filter: TaskPriority | None = None,
        energy_level_filter: str | None = None,
        search_query: str | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        is_archived: bool = False,
        is_overdue: bool | None = None,
        sort_by: TaskSortBy = "created_at",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """List and filter tasks owned by the requesting user with pagination."""
        base_query = select(Task).where(Task.user_id == user_id)

        # Filters
        if not is_archived:
            base_query = base_query.where(Task.is_archived.is_(False))
        else:
            base_query = base_query.where(Task.is_archived.is_(True))

        if status_filter:
            base_query = base_query.where(Task.status == status_filter)

        if priority_filter:
            base_query = base_query.where(Task.priority == priority_filter)

        if energy_level_filter:
            base_query = base_query.where(Task.energy_level == energy_level_filter)

        if search_query:
            term = f"%{search_query.strip()}%"
            base_query = base_query.where(
                or_(
                    Task.title.ilike(term),
                    Task.description.ilike(term),
                )
            )

        if due_before:
            base_query = base_query.where(Task.deadline <= due_before)

        if due_after:
            base_query = base_query.where(Task.deadline >= due_after)

        if is_overdue is True:
            base_query = base_query.where(
                Task.deadline.isnot(None),
                Task.deadline < datetime.now(UTC),
                Task.status.in_(["pending", "in_progress"]),
            )
        elif is_overdue is False:
            base_query = base_query.where(
                or_(Task.deadline.is_(None), Task.deadline >= datetime.now(UTC))
            )

        # 1. Total matching count
        count_stmt = select(func.count()).select_from(base_query.subquery())
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar_one()

        # 2. Sorting
        sort_column: Any
        if sort_by == "deadline":
            sort_column = (
                Task.deadline.asc().nullslast()
                if sort_order == "asc"
                else Task.deadline.desc().nullslast()
            )
        elif sort_by == "priority":
            sort_column = Task.priority.asc() if sort_order == "asc" else Task.priority.desc()
        elif sort_by == "duration_minutes":
            sort_column = (
                Task.duration_minutes.asc() if sort_order == "asc" else Task.duration_minutes.desc()
            )
        elif sort_by == "updated_at":
            sort_column = Task.updated_at.asc() if sort_order == "asc" else Task.updated_at.desc()
        else:  # created_at
            sort_column = Task.created_at.asc() if sort_order == "asc" else Task.created_at.desc()

        items_stmt = base_query.order_by(sort_column).offset(offset).limit(limit)
        items_result = await db.execute(items_stmt)
        tasks = list(items_result.scalars().all())

        return tasks, total_count

    @staticmethod
    async def update_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        payload: TaskUpdateRequest,
        client_ip: str | None = None,
    ) -> Task:
        """Update task fields partially, enforcing status state transitions and audit logging."""
        task = await TaskService.get_task_by_id(db, user_id, task_id)
        updates = payload.model_dump(exclude_unset=True)

        if not updates:
            return task

        # Check status transition if status is being updated
        if "status" in updates and updates["status"] is not None:
            new_status = updates["status"]
            if new_status != task.status:
                validate_status_transition(task.status, new_status)
                task.status = new_status
                # Synchronize schedule block completion status
                from sqlalchemy import update as sa_update
                from app.db.models.schedule import ScheduleBlock
                await db.execute(
                    sa_update(ScheduleBlock)
                    .where(ScheduleBlock.task_id == task.id, ScheduleBlock.user_id == user_id)
                    .values(is_completed=(new_status == "completed"))
                )

        # Apply other fields
        for field, value in updates.items():
            if field != "status":
                setattr(task, field, value)

        task.updated_at = datetime.now(UTC)

        action_name = "task_cancelled" if task.status == "cancelled" else "task_updated"
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action_name,
            resource_type="task",
            resource_id=str(task.id),
            details={"updated_fields": list(updates.keys()), "status": task.status},
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        db.add(audit_entry)
        await db.commit()
        await db.refresh(task)

        if "status" in updates and updates["status"] in ("completed", "cancelled"):
            await NotificationService.reconcile_task_lifecycle(
                db=db, user_id=user_id, task=task, event=f"task_{updates['status']}"
            )
        elif "deadline" in updates:
            await NotificationService.reconcile_task_lifecycle(
                db=db, user_id=user_id, task=task, event="task_deadline_changed"
            )

        logger.info(
            "Task updated", task_id=str(task.id), user_id=str(user_id), fields=list(updates.keys())
        )
        return task

    @staticmethod
    async def delete_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        client_ip: str | None = None,
    ) -> None:
        """Hard delete a task and record an audit log in a single transaction."""
        task = await TaskService.get_task_by_id(db, user_id, task_id)

        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="task_deleted",
            resource_type="task",
            resource_id=str(task_id),
            details={"title": task.title, "status": task.status},
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        await db.delete(task)
        db.add(audit_entry)
        await db.commit()

        logger.info("Task deleted", task_id=str(task_id), user_id=str(user_id))

    @staticmethod
    async def complete_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        client_ip: str | None = None,
    ) -> Task:
        """Convenience action to mark a task as completed."""
        task = await TaskService.get_task_by_id(db, user_id, task_id)
        if task.status == "completed":
            return task

        validate_status_transition(task.status, "completed")
        previous_status = task.status
        task.status = "completed"
        task.updated_at = datetime.now(UTC)

        from sqlalchemy import update as sa_update
        from app.db.models.schedule import ScheduleBlock
        await db.execute(
            sa_update(ScheduleBlock)
            .where(ScheduleBlock.task_id == task.id, ScheduleBlock.user_id == user_id)
            .values(is_completed=True)
        )

        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="task_completed",
            resource_type="task",
            resource_id=str(task.id),
            details={"previous_status": previous_status},
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        db.add(audit_entry)
        await db.commit()
        await db.refresh(task)

        await NotificationService.reconcile_task_lifecycle(
            db=db, user_id=user_id, task=task, event="task_completed"
        )

        logger.info("Task marked completed", task_id=str(task.id), user_id=str(user_id))
        return task

    @staticmethod
    async def reopen_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        client_ip: str | None = None,
    ) -> Task:
        """Convenience action to reopen a completed or cancelled task back to pending."""
        task = await TaskService.get_task_by_id(db, user_id, task_id)
        if task.status == "pending":
            return task

        validate_status_transition(task.status, "pending")
        previous_status = task.status
        task.status = "pending"
        task.updated_at = datetime.now(UTC)

        from sqlalchemy import update as sa_update
        from app.db.models.schedule import ScheduleBlock
        await db.execute(
            sa_update(ScheduleBlock)
            .where(ScheduleBlock.task_id == task.id, ScheduleBlock.user_id == user_id)
            .values(is_completed=False)
        )

        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="task_reopened",
            resource_type="task",
            resource_id=str(task.id),
            details={"previous_status": previous_status},
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        db.add(audit_entry)
        await db.commit()
        await db.refresh(task)

        await NotificationService.reconcile_task_lifecycle(
            db=db, user_id=user_id, task=task, event="task_reopened"
        )

        logger.info(
            "Task reopened", task_id=str(task.id), user_id=str(user_id), from_status=previous_status
        )
        return task

    @staticmethod
    async def set_archive_status(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        is_archived: bool,
        client_ip: str | None = None,
    ) -> Task:
        """Archive or restore an existing task."""
        task = await TaskService.get_task_by_id(db, user_id, task_id)
        task.is_archived = is_archived
        task.updated_at = datetime.now(UTC)

        action_name = "task_archived" if is_archived else "task_unarchived"
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action_name,
            resource_type="task",
            resource_id=str(task.id),
            details={"is_archived": is_archived},
            ip_address=client_ip,
            created_at=datetime.now(UTC),
        )

        db.add(audit_entry)
        await db.commit()
        await db.refresh(task)

        event_name = "task_archived" if is_archived else "task_reopened"
        await NotificationService.reconcile_task_lifecycle(
            db=db, user_id=user_id, task=task, event=event_name
        )

        logger.info(action_name, task_id=str(task.id), user_id=str(user_id))
        return task

    @staticmethod
    async def archive_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        client_ip: str | None = None,
    ) -> Task:
        """Convenience method to archive a task."""
        return await TaskService.set_archive_status(
            db=db, user_id=user_id, task_id=task_id, is_archived=True, client_ip=client_ip
        )

    @staticmethod
    async def unarchive_task(
        db: AsyncSession,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        client_ip: str | None = None,
    ) -> Task:
        """Convenience method to unarchive a task."""
        return await TaskService.set_archive_status(
            db=db, user_id=user_id, task_id=task_id, is_archived=False, client_ip=client_ip
        )

