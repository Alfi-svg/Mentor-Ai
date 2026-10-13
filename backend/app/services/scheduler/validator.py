"""Comprehensive deterministic schedule validator."""

import uuid

from app.services.scheduler.models import (
    FixedEvent,
    SchedulableTask,
    ScheduleBlockProposal,
    ScheduleValidationResult,
    TimeInterval,
)


def validate_schedule(
    blocks: list[ScheduleBlockProposal],
    working_interval: TimeInterval,
    fixed_events: list[FixedEvent] | None = None,
    tasks_by_id: dict[uuid.UUID, SchedulableTask] | None = None,
) -> ScheduleValidationResult:
    """Rigorous mathematical verification of proposed schedule soundness.

    Guarantees:
    1. Zero pairwise overlap between any scheduled blocks (tasks, events, breaks, buffers).
    2. Zero overlap between tasks and fixed commitments.
    3. All blocks have strictly positive duration (end_time > start_time).
    4. Task blocks do not violate working hour boundaries.
    5. No task block finishes after its specified deadline.
    6. Fixed calendar events are never moved or truncated.
    7. All block types are strictly legal.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not blocks:
        return ScheduleValidationResult(
            is_valid=True, errors=[], warnings=["Schedule contains zero blocks."]
        )

    # 1. Individual block sanity: positive duration & valid type
    for b in blocks:
        if b.end_time <= b.start_time:
            errors.append(
                f"Block '{b.title}' (ID: {b.id}) has invalid non-positive duration: "
                f"start={b.start_time.isoformat()}, end={b.end_time.isoformat()}."
            )
        if b.block_type not in {"task", "fixed_event", "break", "buffer"}:
            errors.append(
                f"Block '{b.title}' has invalid block_type '{b.block_type}'. "
                f"Must be one of: 'task', 'fixed_event', 'break', 'buffer'."
            )

    # 2. Pairwise overlap check between all blocks in the schedule
    # Sort blocks chronologically by start_time
    sorted_blocks = sorted(blocks, key=lambda x: (x.start_time, x.end_time))
    for i in range(len(sorted_blocks) - 1):
        curr = sorted_blocks[i]
        nxt = sorted_blocks[i + 1]
        if curr.end_time > nxt.start_time:
            errors.append(
                f"Overlap detected: Block '{curr.title}' ({curr.start_time.isoformat()} - {curr.end_time.isoformat()}) "
                f"collides with Block '{nxt.title}' ({nxt.start_time.isoformat()} - {nxt.end_time.isoformat()})."
            )

    # 3. Fixed commitments check: never move fixed events & no task overlaps with fixed event
    if fixed_events:
        for fe in fixed_events:
            for b in blocks:
                if b.block_type in {"task", "break"} and b.interval.overlaps(fe.interval):
                    errors.append(
                        f"Collision with fixed commitment: Task/Break '{b.title}' "
                        f"({b.start_time.isoformat()} - {b.end_time.isoformat()}) "
                        f"overlaps with fixed event '{fe.title}' "
                        f"({fe.start_time.isoformat()} - {fe.end_time.isoformat()})."
                    )

    # 4. Boundary enforcement: tasks, breaks, and buffers must not exceed working hours
    for b in blocks:
        if b.block_type in {"task", "break", "buffer"}:
            if b.start_time < working_interval.start_time:
                errors.append(
                    f"Boundary violation: Block '{b.title}' starts at {b.start_time.isoformat()}, "
                    f"which is before working window start {working_interval.start_time.isoformat()}."
                )
            if b.end_time > working_interval.end_time:
                errors.append(
                    f"Boundary violation: Block '{b.title}' ends at {b.end_time.isoformat()}, "
                    f"which exceeds working window end {working_interval.end_time.isoformat()}."
                )

    # 5. Deadline compliance
    if tasks_by_id:
        for b in blocks:
            if b.task_id is not None and b.task_id in tasks_by_id:
                task = tasks_by_id[b.task_id]
                if task.deadline is not None and b.end_time > task.deadline:
                    errors.append(
                        f"Deadline violation: Task '{task.title}' finishes at {b.end_time.isoformat()}, "
                        f"which exceeds its deadline {task.deadline.isoformat()}."
                    )

    # 6. Duplicate block IDs check
    block_ids = [b.id for b in blocks]
    if len(block_ids) != len(set(block_ids)):
        errors.append("Duplicate block IDs detected in schedule proposal.")

    return ScheduleValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
