"""Phase 3 comprehensive automated test suite for Mentor AI.

Covers all Phase 3 requirements:
1. Complete Task CRUD lifecycle and schema validation (positive & negative cases).
2. Status state transitions and rejection of invalid state transitions.
3. Task archiving and restoration (with filtering).
4. Overdue and upcoming task filtering.
5. User preferences retrieval, persistence, and audit logging.
6. User preferences validation rules (identical working hours, invalid IANA timezones, invalid days).
7. Schedule block completion synchronization on task completion/reopening/cancellation.
8. Exclusion of completed, cancelled, and archived tasks from scheduling.
9. Database transaction atomicity and rollback on error.
10. Cross-user isolation and authorization boundaries.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.auth import (
    PreferencesUpdateRequest,
    get_preferences,
    update_preferences,
)
from app.core.errors import AppException, EntityNotFoundException
from app.db.base import Base
from app.db.models.action import AuditLog
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.services.scheduler.service import SchedulerService
from app.services.task_service import TaskService


@pytest.fixture
async def test_db():
    """Create an isolated in-memory async SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# -----------------------------------------------------------------------------
# Scenario 1: Complete Task CRUD Lifecycle & Validation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_01_task_crud_lifecycle_and_validation(test_db):
    """Test full task CRUD lifecycle, attribute management, and schema validation."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="crud_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    # 1. Create task with full rich parameters
    create_req = TaskCreateRequest(
        title="Implement Phase 3 Tests",
        description="Write comprehensive pytest cases for task management & consistency",
        duration_minutes=45,
        priority="P1",
        energy_level="high",
        deadline=datetime.now(UTC) + timedelta(days=2),
        tags=["backend", "testing", "phase3"],
        constraints={"can_split": False, "preferred_time_of_day": "morning"},
    )
    task = await TaskService.create_task(test_db, user_id, create_req)
    assert task.id is not None
    assert task.title == "Implement Phase 3 Tests"
    assert task.priority == "P1"
    assert task.energy_level == "high"
    assert task.duration_minutes == 45
    assert task.status == "pending"
    assert task.tags == ["backend", "testing", "phase3"]
    assert task.is_archived is False

    # 2. Retrieve task by ID
    fetched = await TaskService.get_task_by_id(test_db, user_id, task.id)
    assert fetched.id == task.id
    assert fetched.title == task.title

    # 3. Update task fields
    update_req = TaskUpdateRequest(
        title="Implement Phase 3 Tests (Updated)",
        priority="P2",
        duration_minutes=60,
        tags=["backend", "verified"],
    )
    updated = await TaskService.update_task(test_db, user_id, task.id, update_req)
    assert updated.title == "Implement Phase 3 Tests (Updated)"
    assert updated.priority == "P2"
    assert updated.duration_minutes == 60
    assert updated.tags == ["backend", "verified"]

    # 4. Schema validation rejections (negative cases)
    with pytest.raises(ValidationError):
        TaskCreateRequest(title="")

    with pytest.raises(ValidationError):
        TaskCreateRequest(title="   ")

    with pytest.raises(ValidationError):
        TaskCreateRequest(title="Invalid zero duration", duration_minutes=0)

    with pytest.raises(ValidationError):
        TaskCreateRequest(title="Invalid negative duration", duration_minutes=-30)

    with pytest.raises(ValidationError):
        TaskCreateRequest(title="Invalid excessive duration", duration_minutes=721)

    # 5. Delete task & verify AuditLog
    task_id = task.id
    await TaskService.delete_task(test_db, user_id, task_id)

    with pytest.raises(EntityNotFoundException):
        await TaskService.get_task_by_id(test_db, user_id, task_id)

    audit_stmt = select(AuditLog).where(
        AuditLog.user_id == user_id,
        AuditLog.action == "task_deleted",
        AuditLog.resource_id == str(task_id),
    )
    audit_res = await test_db.execute(audit_stmt)
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.resource_type == "task"


# -----------------------------------------------------------------------------
# Scenario 2: Status State Transitions & Transition Enforcement
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_02_status_state_transitions_and_rejection(test_db):
    """Verify lifecycle state transitions (pending -> in_progress -> completed) and rejection of invalid jumps."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="status_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    # Valid lifecycle: pending -> in_progress -> completed -> pending
    task = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="State Machine Test Task")
    )
    assert task.status == "pending"

    # pending -> in_progress
    task = await TaskService.update_task(
        test_db, user_id, task.id, TaskUpdateRequest(status="in_progress")
    )
    assert task.status == "in_progress"

    # in_progress -> completed
    task = await TaskService.complete_task(test_db, user_id, task.id)
    assert task.status == "completed"

    # completed -> pending (reopen)
    task = await TaskService.reopen_task(test_db, user_id, task.id)
    assert task.status == "pending"

    # pending -> cancelled
    task = await TaskService.update_task(
        test_db, user_id, task.id, TaskUpdateRequest(status="cancelled")
    )
    assert task.status == "cancelled"

    # Rejection: cancelled -> completed is forbidden (must reopen/pending first)
    with pytest.raises(AppException) as exc_info:
        await TaskService.update_task(
            test_db, user_id, task.id, TaskUpdateRequest(status="completed")
        )
    assert exc_info.value.error_code == "INVALID_STATUS_TRANSITION"
    assert exc_info.value.status_code == 400

    # Cancelled -> pending is allowed
    task = await TaskService.update_task(
        test_db, user_id, task.id, TaskUpdateRequest(status="pending")
    )
    assert task.status == "pending"

    # Mark completed, then verify completed -> cancelled is rejected
    task = await TaskService.complete_task(test_db, user_id, task.id)
    assert task.status == "completed"

    with pytest.raises(AppException) as exc_info:
        await TaskService.update_task(
            test_db, user_id, task.id, TaskUpdateRequest(status="cancelled")
        )
    assert exc_info.value.error_code == "INVALID_STATUS_TRANSITION"


# -----------------------------------------------------------------------------
# Scenario 3: Task Archiving & Restoration
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_03_task_archiving_and_restoration(test_db):
    """Test soft-archiving tasks, filtering by archive state, and unarchiving."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="archive_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    task = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Archivable Task")
    )
    assert task.is_archived is False

    # Default list_tasks excludes archived tasks
    active_tasks, count = await TaskService.list_tasks(test_db, user_id, is_archived=False)
    assert count == 1
    assert active_tasks[0].id == task.id

    # Archive task
    archived = await TaskService.archive_task(test_db, user_id, task.id)
    assert archived.is_archived is True

    # Active list now returns 0
    active_tasks, count = await TaskService.list_tasks(test_db, user_id, is_archived=False)
    assert count == 0

    # Archived list returns 1
    archived_tasks, count = await TaskService.list_tasks(test_db, user_id, is_archived=True)
    assert count == 1
    assert archived_tasks[0].id == task.id

    # Restore / unarchive task
    restored = await TaskService.unarchive_task(test_db, user_id, task.id)
    assert restored.is_archived is False

    # Active list returns 1 again
    active_tasks, count = await TaskService.list_tasks(test_db, user_id, is_archived=False)
    assert count == 1


# -----------------------------------------------------------------------------
# Scenario 4: Overdue vs Upcoming Task Filtering
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_04_overdue_and_upcoming_filtering(test_db):
    """Verify that is_overdue=True only matches active tasks with deadlines strictly in the past."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="overdue_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    now = datetime.now(UTC)

    # 1. Overdue pending task
    t_overdue_pending = await TaskService.create_task(
        test_db,
        user_id,
        TaskCreateRequest(
            title="Overdue Pending Task",
            deadline=now - timedelta(days=2),
        ),
    )

    # 2. Overdue in_progress task
    t_overdue_progress = await TaskService.create_task(
        test_db,
        user_id,
        TaskCreateRequest(
            title="Overdue In-Progress Task",
            deadline=now - timedelta(hours=5),
        ),
    )
    await TaskService.update_task(
        test_db, user_id, t_overdue_progress.id, TaskUpdateRequest(status="in_progress")
    )

    # 3. Overdue deadline but COMPLETED (must NOT be counted as overdue)
    t_overdue_completed = await TaskService.create_task(
        test_db,
        user_id,
        TaskCreateRequest(
            title="Past Completed Task",
            deadline=now - timedelta(days=1),
        ),
    )
    await TaskService.complete_task(test_db, user_id, t_overdue_completed.id)

    # 4. Upcoming future task
    t_upcoming = await TaskService.create_task(
        test_db,
        user_id,
        TaskCreateRequest(
            title="Future Upcoming Task",
            deadline=now + timedelta(days=3),
        ),
    )

    # 5. Task without deadline
    t_no_deadline = await TaskService.create_task(
        test_db,
        user_id,
        TaskCreateRequest(title="No Deadline Backlog Task"),
    )

    # Filter is_overdue=True
    overdue_list, overdue_count = await TaskService.list_tasks(
        test_db, user_id, is_overdue=True
    )
    overdue_ids = {t.id for t in overdue_list}
    assert overdue_count == 2
    assert t_overdue_pending.id in overdue_ids
    assert t_overdue_progress.id in overdue_ids
    assert t_overdue_completed.id not in overdue_ids
    assert t_upcoming.id not in overdue_ids
    assert t_no_deadline.id not in overdue_ids

    # Filter is_overdue=False
    upcoming_list, upcoming_count = await TaskService.list_tasks(
        test_db, user_id, is_overdue=False
    )
    upcoming_ids = {t.id for t in upcoming_list}
    assert t_upcoming.id in upcoming_ids
    assert t_no_deadline.id in upcoming_ids
    assert t_overdue_pending.id not in upcoming_ids


# -----------------------------------------------------------------------------
# Scenario 5: User Preferences Retrieval & Persistence
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_05_preferences_retrieval_and_persistence(test_db):
    """Test preferences endpoint retrieval defaults, updates, timezone sync, and audit logging."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email="prefs_user@mentor.ai",
        timezone="UTC",
    )
    test_db.add(profile)
    await test_db.commit()

    # 1. Fetch defaults via get_preferences
    default_prefs = await get_preferences(profile=profile, db=test_db)
    assert default_prefs.work_start_time == "09:00:00"
    assert default_prefs.work_end_time == "18:00:00"
    assert default_prefs.buffer_minutes == 15
    assert default_prefs.default_task_duration == 45
    assert default_prefs.timezone == "UTC"
    assert default_prefs.available_days == [1, 2, 3, 4, 5]

    # 2. Update preferences
    update_req = PreferencesUpdateRequest(
        work_start_time="08:30:00",
        work_end_time="17:00:00",
        buffer_minutes=20,
        default_task_duration=50,
        max_focus_hours_per_day=7,
        available_days=[1, 2, 3, 4],
        auto_schedule_breaks=False,
        timezone="America/New_York",
    )
    updated_prefs = await update_preferences(
        request=update_req, profile=profile, db=test_db
    )
    assert updated_prefs.work_start_time == "08:30:00"
    assert updated_prefs.work_end_time == "17:00:00"
    assert updated_prefs.buffer_minutes == 20
    assert updated_prefs.default_task_duration == 50
    assert updated_prefs.max_focus_hours_per_day == 7
    assert updated_prefs.available_days == [1, 2, 3, 4]
    assert updated_prefs.auto_schedule_breaks is False
    assert updated_prefs.timezone == "America/New_York"

    # Verify Profile.timezone was updated in DB
    refreshed_profile = await test_db.scalar(select(Profile).where(Profile.id == user_id))
    assert refreshed_profile.timezone == "America/New_York"

    # Verify AuditLog created
    audit_stmt = select(AuditLog).where(
        AuditLog.user_id == user_id, AuditLog.action == "preferences_updated"
    )
    audit = await test_db.scalar(audit_stmt)
    assert audit is not None
    assert audit.resource_type == "user_preferences"


# -----------------------------------------------------------------------------
# Scenario 6: User Preferences Validation Rules
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_06_preferences_validation_rules(test_db):
    """Verify validation: identical work hours, invalid timezones, and day bounds."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="pref_val_user@mentor.ai", timezone="UTC")
    prefs = UserPreferences(user_id=user_id, work_start_time="09:00:00", work_end_time="17:00:00")
    test_db.add_all([profile, prefs])
    await test_db.commit()

    # 1. Identical work_start_time and work_end_time rejected
    identical_req = PreferencesUpdateRequest(
        work_start_time="10:00:00",
        work_end_time="10:00:00",
    )
    with pytest.raises(AppException) as exc_info:
        await update_preferences(request=identical_req, profile=profile, db=test_db)
    assert exc_info.value.error_code == "INVALID_WORKING_HOURS"
    assert exc_info.value.status_code == 400

    # 2. Invalid IANA timezone rejected by schema validator
    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(timezone="Mars/Olympus_Mons")

    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(timezone="GMT+500")

    # 3. Invalid available_days rejected (< 1 or > 7)
    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(available_days=[0, 1, 2])

    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(available_days=[1, 2, 8])

    # 4. Out of bounds buffer minutes
    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(buffer_minutes=-5)

    with pytest.raises(ValidationError):
        PreferencesUpdateRequest(buffer_minutes=65)


# -----------------------------------------------------------------------------
# Scenario 7: Schedule Block Completion Synchronization
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_07_schedule_block_completion_sync(test_db):
    """Verify that completing, reopening, or cancelling a task updates ScheduleBlock.is_completed."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="sync_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    task = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Sync Task With Schedule", duration_minutes=60)
    )

    # Create a schedule and schedule block referencing this task
    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=date(2026, 10, 15),
        status="accepted",
    )
    test_db.add(schedule)
    await test_db.flush()

    block = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        user_id=user_id,
        task_id=task.id,
        title="Sync Task With Schedule",
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 10, 0, 0, tzinfo=UTC),
        block_type="task",
        is_completed=False,
    )
    test_db.add(block)
    await test_db.commit()

    # Initial state
    refreshed_block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.id == block.id))
    assert refreshed_block.is_completed is False

    # 1. Complete task -> schedule block becomes completed
    await TaskService.complete_task(test_db, user_id, task.id)
    refreshed_block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.id == block.id))
    assert refreshed_block.is_completed is True

    # 2. Reopen task -> schedule block reverts to not completed
    await TaskService.reopen_task(test_db, user_id, task.id)
    refreshed_block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.id == block.id))
    assert refreshed_block.is_completed is False

    # 3. Update task to cancelled -> schedule block remains not completed
    await TaskService.update_task(
        test_db, user_id, task.id, TaskUpdateRequest(status="cancelled")
    )
    refreshed_block = await test_db.scalar(select(ScheduleBlock).where(ScheduleBlock.id == block.id))
    assert refreshed_block.is_completed is False


# -----------------------------------------------------------------------------
# Scenario 8: Exclusion of Completed, Cancelled, and Archived Tasks
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_08_exclusion_of_completed_cancelled_archived_tasks(test_db):
    """Verify SchedulerService strictly excludes completed, cancelled, and archived tasks."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="scheduler_excl_user@mentor.ai", timezone="UTC")
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="17:00:00",
    )
    test_db.add_all([profile, prefs])
    await test_db.commit()

    # Active task
    t_active = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Active Task", duration_minutes=60)
    )
    # Completed task
    t_completed = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Completed Task", duration_minutes=60)
    )
    await TaskService.complete_task(test_db, user_id, t_completed.id)

    # Cancelled task
    t_cancelled = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Cancelled Task", duration_minutes=60)
    )
    await TaskService.update_task(
        test_db, user_id, t_cancelled.id, TaskUpdateRequest(status="cancelled")
    )

    # Archived task
    t_archived = await TaskService.create_task(
        test_db, user_id, TaskCreateRequest(title="Archived Task", duration_minutes=60)
    )
    await TaskService.archive_task(test_db, user_id, t_archived.id)

    # Generate schedule
    proposal = await SchedulerService.generate_proposal(
        db=test_db,
        user_id=user_id,
        target_date=date(2026, 10, 15),
    )

    scheduled_titles = [b.title for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert "Active Task" in scheduled_titles
    assert "Completed Task" not in scheduled_titles
    assert "Cancelled Task" not in scheduled_titles
    assert "Archived Task" not in scheduled_titles
    assert len(scheduled_titles) == 1


# -----------------------------------------------------------------------------
# Scenario 9: Database Transaction Atomicity & Rollback
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_09_database_transaction_atomicity(test_db):
    """Verify that failed multi-table transactions roll back cleanly without partial persistence."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="atomic_user@mentor.ai", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    task_id = uuid.uuid4()
    try:
        async with test_db.begin_nested():
            # Step 1: Add a task
            t = Task(
                id=task_id,
                user_id=user_id,
                title="Staged Task",
                duration_minutes=45,
                status="pending",
            )
            test_db.add(t)
            await test_db.flush()

            # Step 2: Trigger intentional exception
            raise RuntimeError("Simulated transaction failure!")
    except RuntimeError:
        pass

    # Verify task was NOT persisted
    persisted = await test_db.scalar(select(Task).where(Task.id == task_id))
    assert persisted is None


# -----------------------------------------------------------------------------
# Scenario 10: Cross-User Isolation & Authorization Boundaries
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_10_cross_user_isolation(test_db):
    """Verify User B cannot view, modify, archive, or delete User A's tasks or preferences."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    profile_a = Profile(id=user_a, email="user_a@mentor.ai", timezone="UTC")
    profile_b = Profile(id=user_b, email="user_b@mentor.ai", timezone="America/Los_Angeles")
    test_db.add_all([profile_a, profile_b])
    await test_db.commit()

    task_a = await TaskService.create_task(
        test_db, user_a, TaskCreateRequest(title="User A Private Task")
    )

    # 1. User B cannot get User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.get_task_by_id(test_db, user_b, task_a.id)

    # 2. User B cannot update User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.update_task(
            test_db, user_b, task_a.id, TaskUpdateRequest(title="Hacked Title")
        )

    # 3. User B cannot complete User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.complete_task(test_db, user_b, task_a.id)

    # 4. User B cannot archive User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.archive_task(test_db, user_b, task_a.id)

    # 5. User B cannot unarchive User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.unarchive_task(test_db, user_b, task_a.id)

    # 6. User B cannot delete User A's task
    with pytest.raises(EntityNotFoundException):
        await TaskService.delete_task(test_db, user_b, task_a.id)

    # 7. User B listing tasks sees empty list
    user_b_tasks, count_b = await TaskService.list_tasks(test_db, user_b)
    assert count_b == 0
    assert len(user_b_tasks) == 0

    # User A's task remains untouched
    task_a_fresh = await TaskService.get_task_by_id(test_db, user_a, task_a.id)
    assert task_a_fresh.title == "User A Private Task"
