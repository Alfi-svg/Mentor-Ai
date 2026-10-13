"""Tests for the Earliest Deadline First (EDF) scheduler engine and natural language explanations."""

import uuid
from datetime import UTC, date, datetime

from app.services.scheduler.engine import DeterministicSchedulerEngine
from app.services.scheduler.models import SchedulableTask, TimeInterval


def test_edf_scheduling_order_and_explanation():
    """Verify that a task with an earlier deadline (5:00 PM) is scheduled before a task with a later deadline (6:00 PM)."""
    target_date = date(2026, 10, 15)

    task_b_id = uuid.uuid4()
    task_a_id = uuid.uuid4()

    # Project B: Due at 6:00 PM (18:00 UTC)
    task_b = SchedulableTask(
        id=task_b_id,
        title="Project B",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 18, 0, 0, tzinfo=UTC),
        priority="P2",
    )

    # Project A: Due at 5:00 PM (17:00 UTC)
    task_a = SchedulableTask(
        id=task_a_id,
        title="Project A",
        duration_minutes=60,
        deadline=datetime(2026, 10, 15, 17, 0, 0, tzinfo=UTC),
        priority="P2",
    )

    working_interval = TimeInterval(
        start_time=datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 15, 18, 0, 0, tzinfo=UTC),
    )

    # Pass in [Project B, Project A] deliberately out-of-order
    engine = DeterministicSchedulerEngine(
        working_interval=working_interval,
        fixed_events=[],
        tasks=[task_b, task_a],
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

    # Verify Project A is scheduled first
    assert first_block.title == "Project A"
    assert first_block.task_id == task_a_id

    # Verify Project B is scheduled second
    assert second_block.title == "Project B"
    assert second_block.task_id == task_b_id

    # Verify chronological block times
    assert first_block.start_time < second_block.start_time

    # Verify Summary metrics
    assert proposal.summary is not None
    assert proposal.summary.total_scheduled_task_minutes == 120
    assert proposal.summary.total_working_minutes == 540  # 9 hours = 540 minutes
    assert proposal.summary.utilization_percentage > 0

    # Verify Natural-Language Explanation
    assert proposal.scheduling_explanation is not None
    assert "Project A" in proposal.scheduling_explanation
    assert "Project B" in proposal.scheduling_explanation
    assert "earlier deadline" in proposal.scheduling_explanation
    print("EDF Test passed! Explanation:", proposal.scheduling_explanation)
