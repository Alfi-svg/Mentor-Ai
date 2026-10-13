"""Comprehensive automated tests for the deterministic scheduling engine,

mathematical validator, conflict detection, timezones, and schedule persistence.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.services.scheduler.engine import DeterministicSchedulerEngine
from app.services.scheduler.models import (
    FixedEvent,
    SchedulableTask,
    ScheduleBlockProposal,
    TimeInterval,
)
from app.services.scheduler.service import resolve_working_interval
from app.services.scheduler.validator import validate_schedule


def test_deterministic_solver_repeatability() -> None:
    """Verify that identical inputs produce 100% identical schedule block allocations."""
    target_date = date(2026, 10, 15)
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, tzinfo=UTC),
    )

    t1 = SchedulableTask(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        title="Algorithms Assignment",
        duration_minutes=90,
        priority="P1",
    )
    t2 = SchedulableTask(
        id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        title="Physics Lab Writeup",
        duration_minutes=60,
        priority="P2",
    )

    fe = FixedEvent(
        id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        title="CS301 Lecture",
        start_time=datetime(2026, 10, 15, 11, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 30, tzinfo=UTC),
    )

    # Run solver twice
    engine1 = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[fe],
        tasks=[t1, t2],
        target_date=target_date,
    )
    res1 = engine1.generate_schedule()

    engine2 = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[fe],
        tasks=[t1, t2],
        target_date=target_date,
    )
    res2 = engine2.generate_schedule()

    assert res1.status == "feasible"
    assert res2.status == "feasible"
    assert len(res1.blocks) == len(res2.blocks)

    for b1, b2 in zip(res1.blocks, res2.blocks, strict=True):
        assert b1.title == b2.title
        assert b1.start_time == b2.start_time
        assert b1.end_time == b2.end_time
        assert b1.block_type == b2.block_type


def test_fixed_event_masking_and_buffer_isolation() -> None:
    """Verify fixed commitments are never moved, buffers are respected, and tasks do not overlap."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, tzinfo=UTC),
    )

    meeting_start = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
    meeting_end = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    fixed_event = FixedEvent(
        title="Sprint Planning",
        start_time=meeting_start,
        end_time=meeting_end,
    )

    task = SchedulableTask(
        id=uuid.uuid4(),
        title="Focus Task 1",
        duration_minutes=60,
        priority="P1",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[fixed_event],
        tasks=[task],
        target_date=date(2026, 10, 15),
        buffer_minutes=15,
        enforce_buffer=True,
    )
    proposal = engine.generate_schedule()

    assert proposal.status == "feasible"
    assert proposal.validation.is_valid is True

    # 1. Fixed event is strictly at 11:00 - 12:00
    fe_blocks = [b for b in proposal.blocks if b.block_type == "fixed_event"]
    assert len(fe_blocks) == 1
    assert fe_blocks[0].start_time == meeting_start
    assert fe_blocks[0].end_time == meeting_end

    # 2. Pre and post buffers exist around meeting
    buffer_blocks = [b for b in proposal.blocks if b.block_type == "buffer"]
    assert len(buffer_blocks) == 2
    assert buffer_blocks[0].end_time == meeting_start
    assert buffer_blocks[0].start_time == meeting_start - timedelta(minutes=15)
    assert buffer_blocks[1].start_time == meeting_end
    assert buffer_blocks[1].end_time == meeting_end + timedelta(minutes=15)

    # 3. Task is scheduled safely before the buffer (9:00 - 10:00)
    task_blocks = [b for b in proposal.blocks if b.block_type == "task"]
    assert len(task_blocks) == 1
    assert task_blocks[0].end_time <= buffer_blocks[0].start_time


def test_break_injection_for_long_tasks() -> None:
    """Verify that tasks >= 90 minutes automatically have a break scheduled afterwards."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, tzinfo=UTC),
    )

    long_task = SchedulableTask(
        id=uuid.uuid4(),
        title="Comprehensive OS Lab 3",
        duration_minutes=120,  # >= 90 min threshold
        priority="P1",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[long_task],
        target_date=date(2026, 10, 15),
        auto_schedule_breaks=True,
        break_duration_minutes=10,
        break_threshold_minutes=90,
    )
    proposal = engine.generate_schedule()

    assert proposal.status == "feasible"
    break_blocks = [b for b in proposal.blocks if b.block_type == "break"]
    assert len(break_blocks) == 1
    assert break_blocks[0].duration_minutes == 10
    # Break immediately follows the long task
    task_block = next(b for b in proposal.blocks if b.block_type == "task")
    assert break_blocks[0].start_time == task_block.end_time


def test_priority_and_urgency_ordering() -> None:
    """Verify higher priority tasks (P1) and urgent deadlines are scheduled first."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),  # 3 hours = 180 min total
    )

    low_priority = SchedulableTask(
        id=uuid.uuid4(),
        title="Low Priority Read Docs",
        duration_minutes=60,
        priority="P4",
    )
    urgent_p1 = SchedulableTask(
        id=uuid.uuid4(),
        title="Urgent Security Hotfix",
        duration_minutes=60,
        priority="P1",
    )
    medium_p2 = SchedulableTask(
        id=uuid.uuid4(),
        title="Medium Feature Work",
        duration_minutes=60,
        priority="P2",
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[low_priority, urgent_p1, medium_p2],
        target_date=date(2026, 10, 15),
    )
    proposal = engine.generate_schedule()

    task_blocks = [b for b in proposal.blocks if b.block_type == "task"]
    assert len(task_blocks) == 3
    # P1 scheduled first (9:00 - 10:00)
    assert task_blocks[0].title == "Urgent Security Hotfix"
    assert task_blocks[0].start_time == datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    # P2 scheduled second (10:00 - 11:00)
    assert task_blocks[1].title == "Medium Feature Work"
    # P4 scheduled third (11:00 - 12:00)
    assert task_blocks[2].title == "Low Priority Read Docs"


def test_unscheduled_tasks_and_conflict_reporting_when_overcapacity() -> None:
    """Verify that tasks exceeding available capacity are reported with structured diagnostics."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(
            2026, 10, 15, 11, 0, tzinfo=UTC
        ),  # Only 2 hours = 120 minutes free
    )

    t1 = SchedulableTask(
        id=uuid.uuid4(), title="Task 1", duration_minutes=60, priority="P1"
    )
    t2 = SchedulableTask(
        id=uuid.uuid4(), title="Task 2", duration_minutes=60, priority="P1"
    )
    t3 = SchedulableTask(
        id=uuid.uuid4(), title="Task 3 Overflow", duration_minutes=60, priority="P2"
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[t1, t2, t3],
        target_date=date(2026, 10, 15),
    )
    proposal = engine.generate_schedule()

    assert proposal.status == "conflict_detected"
    assert len(proposal.unscheduled_tasks) == 1
    unscheduled = proposal.unscheduled_tasks[0]
    assert unscheduled.task_title == "Task 3 Overflow"
    assert unscheduled.required_minutes == 60
    assert "Insufficient total open time" in unscheduled.reason
    assert len(unscheduled.suggested_actions) > 0


def test_deadline_violation_triggers_unscheduled_conflict() -> None:
    """Verify that a task whose deadline precedes available open slots is flagged as conflict."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, tzinfo=UTC),
    )

    # Fixed event blocking morning (9:00 - 12:00)
    morning_block = FixedEvent(
        title="Morning Workshop",
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
    )

    # Task requiring 60 min but with early deadline at 10:30 UTC
    urgent_with_early_deadline = SchedulableTask(
        id=uuid.uuid4(),
        title="Mid-Morning Due Task",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 10, 30, tzinfo=UTC),
    )

    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[morning_block],
        tasks=[urgent_with_early_deadline],
        target_date=date(2026, 10, 15),
    )
    proposal = engine.generate_schedule()

    assert proposal.status == "conflict_detected"
    assert len(proposal.unscheduled_tasks) == 1
    assert "deadline" in proposal.unscheduled_tasks[0].reason.lower()


def test_validator_rejects_corrupted_or_overlapping_schedules() -> None:
    """Verify that validate_schedule catches overlaps, boundary breaches, and zero durations."""
    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 17, 0, tzinfo=UTC),
    )

    t_id = uuid.uuid4()
    tasks_by_id = {
        t_id: SchedulableTask(
            id=t_id,
            title="Valid Task",
            duration_minutes=60,
            deadline=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
        )
    }

    # 1. Overlapping blocks
    overlapping_blocks = [
        ScheduleBlockProposal(
            id=uuid.uuid4(),
            title="Block 1",
            start_time=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 10, 15, 10, 30, tzinfo=UTC),
            block_type="task",
        ),
        ScheduleBlockProposal(
            id=uuid.uuid4(),
            title="Block 2",
            start_time=datetime(
                2026, 10, 15, 10, 0, tzinfo=UTC
            ),  # Overlaps Block 1 by 30 min
            end_time=datetime(2026, 10, 15, 11, 0, tzinfo=UTC),
            block_type="task",
        ),
    ]
    res_overlap = validate_schedule(overlapping_blocks, working_interval)
    assert res_overlap.is_valid is False
    assert any("Overlap detected" in err for err in res_overlap.errors)

    # 2. Block starting before working interval
    before_window_blocks = [
        ScheduleBlockProposal(
            id=uuid.uuid4(),
            title="Early Bird Block",
            start_time=datetime(
                2026, 10, 15, 7, 0, tzinfo=UTC
            ),  # Window starts at 9:00
            end_time=datetime(2026, 10, 15, 8, 0, tzinfo=UTC),
            block_type="task",
        )
    ]
    res_before = validate_schedule(before_window_blocks, working_interval)
    assert res_before.is_valid is False
    assert any("Boundary violation" in err for err in res_before.errors)

    # 3. Block finishing after task deadline
    past_deadline_blocks = [
        ScheduleBlockProposal(
            id=uuid.uuid4(),
            task_id=t_id,
            title="Valid Task",
            start_time=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
            end_time=datetime(2026, 10, 15, 13, 0, tzinfo=UTC),  # Deadline was 12:00
            block_type="task",
        )
    ]
    res_deadline = validate_schedule(
        past_deadline_blocks, working_interval, tasks_by_id=tasks_by_id
    )
    assert res_deadline.is_valid is False
    assert any("Deadline violation" in err for err in res_deadline.errors)


def test_timezone_resolution_and_midnight_crossing() -> None:
    """Verify timezone offsets (America/New_York) and shifts crossing midnight."""
    target_date = date(2026, 10, 15)

    # 1. America/New_York (EDT = UTC-4 in October)
    ny_interval = resolve_working_interval(
        target_date=target_date,
        work_start_str="09:00:00",
        work_end_str="17:00:00",
        tz_name="America/New_York",
    )
    # 09:00 EDT = 13:00 UTC
    assert ny_interval.start_time.hour == 13
    # 17:00 EDT = 21:00 UTC
    assert ny_interval.end_time.hour == 21
    assert ny_interval.duration_minutes == 480

    # 2. Night shift crossing midnight (22:00 to 06:00 next day)
    night_interval = resolve_working_interval(
        target_date=target_date,
        work_start_str="22:00:00",
        work_end_str="06:00:00",
        tz_name="UTC",
    )
    assert night_interval.start_time == datetime(2026, 10, 15, 22, 0, tzinfo=UTC)
    assert night_interval.end_time == datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
    assert night_interval.duration_minutes == 480


def test_api_schedule_generate_approve_and_retrieve_lifecycle(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify the full API lifecycle: generate proposal, approve/persist, and retrieve accepted schedule."""
    # 1. Create a task for User A
    task_res = client.post(
        "/api/v1/tasks",
        json={
            "title": "Prepare Operating Systems Presentation",
            "duration_minutes": 60,
            "priority": "P1",
        },
        headers=user_a_headers,
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 2. Request schedule proposal generation for 2026-10-16
    gen_res = client.post(
        "/api/v1/schedule/generate",
        json={"target_date": "2026-10-16", "task_ids": [task_id]},
        headers=user_a_headers,
    )
    assert gen_res.status_code == 200
    proposal = gen_res.json()
    assert proposal["status"] == "feasible"
    assert proposal["validation"]["is_valid"] is True
    assert len(proposal["blocks"]) >= 1

    # 3. Approve and persist proposal
    appr_res = client.post(
        "/api/v1/schedule/approve",
        json=proposal,
        headers=user_a_headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "accepted"

    # 4. Retrieve persisted schedule for 2026-10-16
    get_res = client.get("/api/v1/schedule/2026-10-16", headers=user_a_headers)
    assert get_res.status_code == 200
    schedule_data = get_res.json()
    assert schedule_data["status"] == "accepted"
    assert schedule_data["target_date"] == "2026-10-16"
    assert len(schedule_data["blocks"]) >= 1


def test_direct_schedule_validation_endpoint(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify the POST /api/v1/schedule/validate endpoint directly executes mathematical checks."""
    payload = {
        "blocks": [
            {
                "id": str(uuid.uuid4()),
                "title": "Block A",
                "start_time": "2026-10-15T09:00:00Z",
                "end_time": "2026-10-15T10:00:00Z",
                "block_type": "task",
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Block B",
                "start_time": "2026-10-15T09:30:00Z",  # Overlaps Block A!
                "end_time": "2026-10-15T10:30:00Z",
                "block_type": "task",
            },
        ],
        "working_interval": {
            "start_time": "2026-10-15T09:00:00Z",
            "end_time": "2026-10-15T17:00:00Z",
        },
    }
    res = client.post("/api/v1/schedule/validate", json=payload, headers=user_a_headers)
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["is_valid"] is False
    assert any("Overlap detected" in err for err in val_data["errors"])
