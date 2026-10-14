"""Phase 2 comprehensive automated test suite for Mentor AI.

Covers all 12 core requirements for the AI Agent Core & Smart Scheduler:
1. Earlier deadline vs later deadline (EDF ordering).
2. Multiple tasks with same deadline (Priority tie-breaker P1 > P2).
3. Insufficient available time (Honest infeasibility diagnostics).
4. Fixed-event overlap prevention (with buffer enforcement).
5. Task dependency ordering (Prerequisites scheduled before dependent tasks).
6. Working-hour restrictions (Tasks strictly bounded within working interval).
7. Timezone-aware deadlines (UTC normalization across timezones).
8. Missing or invalid task durations (Clarification question triggered).
9. Completed and cancelled task exclusion (Only pending/in_progress scheduled).
10. Empty task lists (Clean feasible proposal, zero task minutes).
11. Repeated plan confirmation and idempotency (No duplicate DB records).
12. Correct schedule summary calculations (Working, task, fixed, free, utilization).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.schemas.planner import PlanConfirmRequest
from app.schemas.task import TaskCreateRequest
from app.services.ai.models import UserPlanContext
from app.services.ai.offline import DeterministicOfflineAdapter
from app.services.planner_service import PlannerService
from app.services.scheduler.engine import DeterministicSchedulerEngine
from app.services.scheduler.models import FixedEvent, SchedulableTask, TimeInterval
from app.services.scheduler.service import SchedulerService


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
# Scenario 1: Earlier Deadline vs Later Deadline
# -----------------------------------------------------------------------------
def test_scenario_01_earlier_vs_later_deadline():
    """Verify that a task with an earlier deadline is scheduled before a later deadline."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
    )

    task_late = SchedulableTask(
        id=uuid.uuid4(),
        title="Project Beta Report",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 16, 0, 0, tzinfo=UTC),  # 4:00 PM
        priority="P2",
    )
    task_early = SchedulableTask(
        id=uuid.uuid4(),
        title="Project Alpha Spec",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 14, 0, 0, tzinfo=UTC),  # 2:00 PM
        priority="P2",
    )

    # Supply tasks in reverse order
    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task_late, task_early],
        target_date=target_date,
        timezone_name="UTC",
        enforce_buffer=False,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    task_blocks = [b for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert len(task_blocks) == 2
    assert task_blocks[0].title == "Project Alpha Spec"
    assert task_blocks[1].title == "Project Beta Report"
    assert task_blocks[0].start_time < task_blocks[1].start_time
    assert "earlier deadline" in proposal.scheduling_explanation


# -----------------------------------------------------------------------------
# Scenario 2: Multiple Tasks with Same Deadline (Priority Tie-Breaker)
# -----------------------------------------------------------------------------
def test_scenario_02_same_deadline_priority_tie_breaker():
    """Verify that tasks sharing the exact same deadline are ordered by priority (P1 before P2)."""
    target_date = date(2026, 10, 15)
    shared_deadline = datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 18, 0, 0, tzinfo=UTC),
    )

    task_p2 = SchedulableTask(
        id=uuid.uuid4(),
        title="Routine Documentation",
        duration_minutes=60,
        deadline=shared_deadline,
        priority="P2",
    )
    task_p1 = SchedulableTask(
        id=uuid.uuid4(),
        title="Critical Security Hotfix",
        duration_minutes=60,
        deadline=shared_deadline,
        priority="P1",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task_p2, task_p1],
        target_date=target_date,
        timezone_name="UTC",
        enforce_buffer=False,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    task_blocks = [b for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert len(task_blocks) == 2
    assert task_blocks[0].title == "Critical Security Hotfix"
    assert task_blocks[1].title == "Routine Documentation"
    assert "same deadline" in proposal.scheduling_explanation
    assert "higher priority" in proposal.scheduling_explanation


# -----------------------------------------------------------------------------
# Scenario 3: Insufficient Available Time (Honest Infeasibility)
# -----------------------------------------------------------------------------
def test_scenario_03_insufficient_time_honest_infeasibility():
    """Verify that scheduling 8 hours of tasks in a 4-hour window reports infeasible honestly."""
    target_date = date(2026, 10, 15)
    # 4-hour working window (240 minutes)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 13, 0, 0, tzinfo=UTC),
    )

    task_1 = SchedulableTask(
        id=uuid.uuid4(),
        title="Task Part 1",
        duration_minutes=180,  # 3 hours
        priority="P1",
    )
    task_2 = SchedulableTask(
        id=uuid.uuid4(),
        title="Task Part 2",
        duration_minutes=180,  # 3 hours (total = 360m > 240m)
        priority="P2",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task_1, task_2],
        target_date=target_date,
        timezone_name="UTC",
        enforce_buffer=False,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "infeasible"
    assert proposal.is_feasible is False
    assert len(proposal.unscheduled_tasks) == 1
    unscheduled = proposal.unscheduled_tasks[0]
    assert "insufficient" in unscheduled.reason.lower() and "remaining" in unscheduled.reason.lower()
    assert len(unscheduled.suggested_actions) > 0


# -----------------------------------------------------------------------------
# Scenario 4: Fixed-Event Overlap Prevention
# -----------------------------------------------------------------------------
def test_scenario_04_fixed_event_overlap_prevention_with_buffer():
    """Verify tasks never overlap fixed calendar events and respect the buffer interval."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
    )

    # Fixed meeting 11:00 AM to 12:30 PM (90 mins)
    meeting = FixedEvent(
        id=uuid.uuid4(),
        title="Sprint Planning Meeting",
        start_time=datetime(2026, 10, 15, 11, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 30, 0, tzinfo=UTC),
    )

    task_1 = SchedulableTask(
        id=uuid.uuid4(),
        title="Pre-meeting Review",
        duration_minutes=60,
        priority="P1",
    )
    task_2 = SchedulableTask(
        id=uuid.uuid4(),
        title="Post-meeting Execution",
        duration_minutes=120,
        priority="P1",
    )

    buffer_mins = 15
    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[meeting],
        tasks=[task_1, task_2],
        target_date=target_date,
        timezone_name="UTC",
        buffer_minutes=buffer_mins,
        enforce_buffer=True,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    task_blocks = [b for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert len(task_blocks) == 2

    # Check that no task overlaps with the meeting or buffer
    buffered_meeting_start = meeting.start_time - timedelta(minutes=buffer_mins)
    buffered_meeting_end = meeting.end_time + timedelta(minutes=buffer_mins)

    for block in task_blocks:
        assert block.end_time <= buffered_meeting_start or block.start_time >= buffered_meeting_end


# -----------------------------------------------------------------------------
# Scenario 5: Task Dependency Ordering
# -----------------------------------------------------------------------------
def test_scenario_05_task_dependency_ordering():
    """Verify that prerequisite task A is scheduled before dependent task B, regardless of deadline."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 18, 0, 0, tzinfo=UTC),
    )

    task_prereq_id = uuid.uuid4()
    task_dependent_id = uuid.uuid4()

    # Prerequisite: P3, later deadline (5:00 PM)
    task_prereq = SchedulableTask(
        id=task_prereq_id,
        title="Research and Architecture Design",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
        priority="P3",
    )

    # Dependent: P1, earlier deadline (2:00 PM)
    task_dependent = SchedulableTask(
        id=task_dependent_id,
        title="Implementation and Deployment",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 14, 0, 0, tzinfo=UTC),
        priority="P1",
        dependencies=[task_prereq_id],
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task_dependent, task_prereq],
        target_date=target_date,
        timezone_name="UTC",
        enforce_buffer=False,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    task_blocks = [b for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert len(task_blocks) == 2

    first_block = task_blocks[0]
    second_block = task_blocks[1]

    assert first_block.task_id == task_prereq_id
    assert second_block.task_id == task_dependent_id
    assert first_block.end_time <= second_block.start_time
    assert "prerequisite dependency" in proposal.scheduling_explanation


# -----------------------------------------------------------------------------
# Scenario 6: Working-Hour Restrictions
# -----------------------------------------------------------------------------
def test_scenario_06_working_hour_restrictions():
    """Verify tasks are never scheduled outside user working hours."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC),  # 3-hour window
    )

    # Task requiring 4 hours
    oversized_task = SchedulableTask(
        id=uuid.uuid4(),
        title="Oversized Task",
        duration_minutes=240,
        priority="P1",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[oversized_task],
        target_date=target_date,
        timezone_name="UTC",
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "infeasible"
    assert len(proposal.scheduled_blocks) == 0
    assert len(proposal.unscheduled_tasks) == 1
    assert "insufficient" in proposal.unscheduled_tasks[0].reason.lower() and "remaining" in proposal.unscheduled_tasks[0].reason.lower()


# -----------------------------------------------------------------------------
# Scenario 7: Timezone-Aware Deadlines
# -----------------------------------------------------------------------------
def test_scenario_07_timezone_aware_deadlines():
    """Verify deadlines in local timezone are converted to UTC and scheduled accurately."""
    tz_ny = ZoneInfo("America/New_York")
    target_date = date(2026, 10, 15)

    # 9:00 AM to 5:00 PM EDT -> 13:00 to 21:00 UTC
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=tz_ny),
        end_time=datetime(2026, 10, 15, 17, 0, 0, tzinfo=tz_ny),
    )

    # Task due at 11:00 AM EDT (15:00 UTC)
    deadline_local = datetime(2026, 10, 15, 11, 0, 0, tzinfo=tz_ny)
    task = SchedulableTask(
        id=uuid.uuid4(),
        title="Timezone Specific Submission",
        duration_minutes=60,
        deadline=deadline_local,
        priority="P1",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task],
        target_date=target_date,
        timezone_name="America/New_York",
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    block = proposal.scheduled_blocks[0]
    assert block.end_time <= deadline_local.astimezone(UTC)
    assert block.start_time >= working_interval.start_time


# -----------------------------------------------------------------------------
# Scenario 8: Missing or Invalid Task Durations
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_08_missing_task_durations_triggers_clarification():
    """Verify that inputs without durations trigger clarification_needed intent."""
    adapter = DeterministicOfflineAdapter()
    context = UserPlanContext(
        current_date=date(2026, 10, 15),
        timezone="UTC",
        work_start_time="09:00",
        work_end_time="17:00",
        buffer_minutes=10,
        existing_events=[],
        existing_tasks=[],
    )

    prompt = "Plan my day tomorrow: study for physics exam and finish lab writeup"
    res = await adapter.parse_instruction(prompt, context)

    assert res.draft_plan.intent == "clarification_needed"
    assert res.draft_plan.clarification_question is not None
    assert "estimate" in res.draft_plan.clarification_question.lower()
    assert len(res.draft_plan.tasks) >= 1
    assert any(t.duration_minutes is None for t in res.draft_plan.tasks)


# -----------------------------------------------------------------------------
# Scenario 9: Completed and Cancelled Task Exclusion
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_09_completed_and_cancelled_task_exclusion(test_db):
    """Verify that completed and cancelled tasks are strictly excluded from scheduling."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email="test_excl@mentor.ai",
        timezone="UTC",
    )
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="17:00:00",
    )
    test_db.add_all([profile, prefs])

    now = datetime(2026, 10, 15, 10, 0, 0, tzinfo=UTC)

    # 1. Pending task (should be scheduled)
    t_pending = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Pending Assignment",
        duration_minutes=60,
        status="pending",
        deadline=now + timedelta(hours=3),
    )
    # 2. In-progress task (should be scheduled)
    t_progress = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="In-Progress Coding",
        duration_minutes=60,
        status="in_progress",
        deadline=now + timedelta(hours=4),
    )
    # 3. Completed task (MUST be excluded)
    t_completed = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Finished Essay",
        duration_minutes=60,
        status="completed",
        deadline=now + timedelta(hours=1),
    )
    # 4. Cancelled task (MUST be excluded)
    t_cancelled = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Cancelled Meeting Prep",
        duration_minutes=60,
        status="cancelled",
        deadline=now + timedelta(hours=2),
    )

    test_db.add_all([t_pending, t_progress, t_completed, t_cancelled])
    await test_db.commit()

    proposal = await SchedulerService.generate_proposal(
        db=test_db,
        user_id=user_id,
        target_date=date(2026, 10, 15),
    )

    scheduled_titles = [b.title for b in proposal.scheduled_blocks if b.block_type == "task"]
    assert "Pending Assignment" in scheduled_titles
    assert "In-Progress Coding" in scheduled_titles
    assert "Finished Essay" not in scheduled_titles
    assert "Cancelled Meeting Prep" not in scheduled_titles
    assert len(scheduled_titles) == 2


# -----------------------------------------------------------------------------
# Scenario 10: Empty Task Lists
# -----------------------------------------------------------------------------
def test_scenario_10_empty_task_lists():
    """Verify clean handling of empty task lists with zero task minutes."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[],
        target_date=target_date,
        timezone_name="UTC",
    )

    proposal = engine.generate_schedule()
    assert proposal.status == "feasible"
    assert proposal.is_feasible is True
    assert len(proposal.scheduled_blocks) == 0
    assert proposal.summary.total_scheduled_task_minutes == 0
    assert proposal.summary.total_working_minutes == 480
    assert proposal.summary.total_free_minutes == 480
    assert proposal.summary.utilization_percentage == 0.0
    assert "No tasks to schedule" in proposal.scheduling_explanation


# -----------------------------------------------------------------------------
# Scenario 11: Repeated Plan Confirmation and Idempotency
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_11_repeated_confirmation_idempotency(test_db):
    """Verify that confirming the same proposal_id twice creates zero duplicate tasks."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email="test_idem@mentor.ai",
        timezone="UTC",
    )
    prefs = UserPreferences(
        user_id=user_id,
        work_start_time="09:00:00",
        work_end_time="17:00:00",
    )
    test_db.add_all([profile, prefs])
    await test_db.commit()

    proposal_id = str(uuid.uuid4())
    req = PlanConfirmRequest(
        proposal_id=proposal_id,
        target_date=date(2026, 10, 15),
        tasks=[
            TaskCreateRequest(title="Task Alpha", duration_minutes=45, priority="P2"),
            TaskCreateRequest(title="Task Beta", duration_minutes=60, priority="P3"),
        ],
        fixed_events=[],
        persist_tasks=True,
        generate_schedule=True,
    )

    # First confirmation
    res_1 = await PlannerService.confirm_plan(db=test_db, user_id=user_id, req=req)
    assert res_1.status == "confirmed"
    assert len(res_1.created_tasks) == 2

    # Check database count
    tasks_stmt = select(Task).where(Task.user_id == user_id, Task.is_archived.is_(False))
    tasks_res_1 = await test_db.execute(tasks_stmt)
    initial_tasks = tasks_res_1.scalars().all()
    assert len(initial_tasks) == 2

    # Second confirmation with the exact same proposal_id
    res_2 = await PlannerService.confirm_plan(db=test_db, user_id=user_id, req=req)
    assert res_2.status == "confirmed"

    # Verify no additional tasks were created
    tasks_res_2 = await test_db.execute(tasks_stmt)
    final_tasks = tasks_res_2.scalars().all()
    assert len(final_tasks) == 2
    assert {t.title for t in final_tasks} == {"Task Alpha", "Task Beta"}


# -----------------------------------------------------------------------------
# Scenario 12: Correct Schedule Summary Calculations
# -----------------------------------------------------------------------------
def test_scenario_12_schedule_summary_calculations():
    """Verify total_working, total_task, total_fixed, total_free, and utilization calculation."""
    target_date = date(2026, 10, 15)
    # 8-hour window = 480 mins
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
    )

    # 1 hour fixed meeting = 60 mins
    fixed = FixedEvent(
        id=uuid.uuid4(),
        title="Team Standup",
        start_time=datetime(2026, 10, 15, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 11, 0, 0, tzinfo=UTC),
    )

    # 2 tasks of 60 mins each = 120 mins
    t1 = SchedulableTask(
        id=uuid.uuid4(),
        title="Task One",
        duration_minutes=60,
        priority="P2",
    )
    t2 = SchedulableTask(
        id=uuid.uuid4(),
        title="Task Two",
        duration_minutes=60,
        priority="P3",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[fixed],
        tasks=[t1, t2],
        target_date=target_date,
        timezone_name="UTC",
        enforce_buffer=False,
        auto_schedule_breaks=False,
    )

    proposal = engine.generate_schedule()
    summary = proposal.summary
    assert summary is not None

    assert summary.total_working_minutes == 480
    assert summary.total_fixed_minutes == 60
    assert summary.total_scheduled_task_minutes == 120
    assert summary.total_free_minutes == 300  # 480 - 60 - 120 = 300

    # Task Utilization = total_scheduled_task_minutes / total_working_minutes
    # 120 / 480 = 0.25 -> 25.0%
    assert abs(summary.utilization_percentage - 25.0) < 0.01
