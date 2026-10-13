"""Pure deterministic scheduling engine implementing interval algebra constraint satisfaction."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.services.scheduler.models import (
    FixedEvent,
    SchedulableTask,
    ScheduleBlockProposal,
    ScheduleProposal,
    TimeInterval,
    UnscheduledTaskInfo,
)
from app.services.scheduler.validator import validate_schedule


class DeterministicSchedulerEngine:
    """Mathematical constraint-satisfaction scheduling solver.

    Guarantees:
    - Pure, deterministic execution (identical inputs yield identical schedules).
    - Hard calendar commitments and fixed events are never moved, overlapped, or truncated.
    - Zero LLM inference or non-deterministic heuristics.
    - Explicit conflict detection when task requirements exceed available capacity.
    """

    def __init__(
        self,
        working_interval: TimeInterval,
        fixed_events: list[FixedEvent],
        tasks: list[SchedulableTask],
        target_date: date,
        timezone_name: str = "UTC",
        buffer_minutes: int = 15,
        enforce_buffer: bool = True,
        auto_schedule_breaks: bool = True,
        break_duration_minutes: int = 10,
        break_threshold_minutes: int = 90,
        minimum_gap_minutes: int = 5,
    ) -> None:
        self.working_interval = working_interval
        self.fixed_events = fixed_events
        self.tasks = tasks
        self.target_date = target_date
        self.timezone_name = timezone_name
        self.buffer_minutes = max(0, buffer_minutes)
        self.enforce_buffer = enforce_buffer
        self.auto_schedule_breaks = auto_schedule_breaks
        self.break_duration_minutes = max(1, break_duration_minutes)
        self.break_threshold_minutes = max(1, break_threshold_minutes)
        self.minimum_gap_minutes = max(1, minimum_gap_minutes)

    def generate_schedule(self) -> ScheduleProposal:
        """Execute deterministic interval allocation algorithm."""
        schedule_id = uuid.uuid4()
        tasks_by_id = {t.id: t for t in self.tasks}

        # -----------------------------------------------------------------
        # Step 1: Fixed Event Masking & Buffer Expansion
        # -----------------------------------------------------------------
        fixed_blocks: list[ScheduleBlockProposal] = []
        buffer_blocks: list[ScheduleBlockProposal] = []
        raw_occupied_intervals: list[TimeInterval] = []

        for fe in self.fixed_events:
            # Clamp fixed event to working window boundaries
            clamped_start = max(self.working_interval.start_time, fe.start_time)
            clamped_end = min(self.working_interval.end_time, fe.end_time)

            if clamped_start < clamped_end:
                fixed_blocks.append(
                    ScheduleBlockProposal(
                        id=uuid.uuid4(),
                        calendar_event_id=fe.id,
                        title=fe.title,
                        start_time=clamped_start,
                        end_time=clamped_end,
                        block_type="fixed_event",
                        is_fixed=True,
                    )
                )

            # Determine buffered occupied footprint
            if self.enforce_buffer and self.buffer_minutes > 0:
                buf_start = max(
                    self.working_interval.start_time,
                    fe.start_time - timedelta(minutes=self.buffer_minutes),
                )
                buf_end = min(
                    self.working_interval.end_time,
                    fe.end_time + timedelta(minutes=self.buffer_minutes),
                )

                # Pre-event buffer block
                if buf_start < clamped_start and clamped_start <= self.working_interval.end_time:
                    buffer_blocks.append(
                        ScheduleBlockProposal(
                            id=uuid.uuid4(),
                            title="Buffer",
                            start_time=buf_start,
                            end_time=clamped_start,
                            block_type="buffer",
                            is_fixed=False,
                        )
                    )

                # Post-event buffer block
                if buf_end > clamped_end and clamped_end >= self.working_interval.start_time:
                    buffer_blocks.append(
                        ScheduleBlockProposal(
                            id=uuid.uuid4(),
                            title="Buffer",
                            start_time=clamped_end,
                            end_time=buf_end,
                            block_type="buffer",
                            is_fixed=False,
                        )
                    )

                if buf_start < buf_end:
                    raw_occupied_intervals.append(
                        TimeInterval(start_time=buf_start, end_time=buf_end)
                    )
            else:
                if clamped_start < clamped_end:
                    raw_occupied_intervals.append(
                        TimeInterval(start_time=clamped_start, end_time=clamped_end)
                    )

        # -----------------------------------------------------------------
        # Step 2: Merge Overlapping Occupied Footprints
        # -----------------------------------------------------------------
        merged_occupied: list[TimeInterval] = self._merge_intervals(raw_occupied_intervals)

        # -----------------------------------------------------------------
        # Step 3: Compute Available Free Intervals (W \ O)
        # -----------------------------------------------------------------
        free_intervals: list[TimeInterval] = self._compute_free_intervals(merged_occupied)

        # -----------------------------------------------------------------
        # Step 4: Deterministic Multi-Key Sorting of Tasks
        # -----------------------------------------------------------------
        sorted_tasks = self._sort_tasks(self.tasks)

        # -----------------------------------------------------------------
        # Step 5: First-Fit Task Allocation & Break Injection
        # -----------------------------------------------------------------
        scheduled_task_blocks: list[ScheduleBlockProposal] = []
        break_blocks: list[ScheduleBlockProposal] = []
        unscheduled_tasks: list[UnscheduledTaskInfo] = []

        # Mutable tracking of remaining free intervals
        mutable_free: list[list[datetime]] = [
            [interval.start_time, interval.end_time] for interval in free_intervals
        ]

        for task in sorted_tasks:
            duration = timedelta(minutes=task.duration_minutes)
            placed = False

            for slot_idx, slot in enumerate(mutable_free):
                slot_start, slot_end = slot[0], slot[1]
                slot_capacity = (slot_end - slot_start).total_seconds() / 60

                if slot_capacity < task.duration_minutes:
                    continue

                candidate_start = slot_start
                candidate_end = candidate_start + duration

                # Check deadline constraint
                if task.deadline is not None and candidate_end > task.deadline:
                    continue

                # Check time-of-day availability constraints if specified
                earliest_constraint = task.constraints.get("earliest_start")
                if earliest_constraint and isinstance(earliest_constraint, str):
                    try:
                        h, m = map(int, earliest_constraint.split(":")[:2])
                        dt_limit = datetime(
                            self.target_date.year,
                            self.target_date.month,
                            self.target_date.day,
                            h,
                            m,
                            tzinfo=UTC,
                        )
                        if candidate_start < dt_limit:
                            candidate_start = dt_limit
                            candidate_end = candidate_start + duration
                            if candidate_end > slot_end:
                                continue
                    except (ValueError, TypeError):
                        pass

                # Successful placement in this free slot!
                task_block = ScheduleBlockProposal(
                    id=uuid.uuid4(),
                    task_id=task.id,
                    title=task.title,
                    start_time=candidate_start,
                    end_time=candidate_end,
                    block_type="task",
                    is_fixed=False,
                )
                scheduled_task_blocks.append(task_block)
                placed = True

                # Check break injection rule (task duration >= threshold)
                next_free_start = candidate_end
                if (
                    self.auto_schedule_breaks
                    and task.duration_minutes >= self.break_threshold_minutes
                ):
                    break_delta = timedelta(minutes=self.break_duration_minutes)
                    break_candidate_end = candidate_end + break_delta
                    if break_candidate_end <= slot_end:
                        break_block = ScheduleBlockProposal(
                            id=uuid.uuid4(),
                            title="Break",
                            start_time=candidate_end,
                            end_time=break_candidate_end,
                            block_type="break",
                            is_fixed=False,
                        )
                        break_blocks.append(break_block)
                        next_free_start = break_candidate_end

                # Update the remaining slot capacity in mutable_free
                if (
                    next_free_start < slot_end
                    and (slot_end - next_free_start).total_seconds() / 60
                    >= self.minimum_gap_minutes
                ):
                    mutable_free[slot_idx] = [next_free_start, slot_end]
                else:
                    mutable_free.pop(slot_idx)
                break

            if not placed:
                max_gap = 0
                total_free = 0
                for s_start, s_end in mutable_free:
                    gap_mins = int((s_end - s_start).total_seconds() / 60)
                    total_free += gap_mins
                    if gap_mins > max_gap:
                        max_gap = gap_mins

                # Formulate transparent conflict diagnostic
                if total_free < task.duration_minutes:
                    reason = (
                        f"Insufficient total open time ({total_free} min remaining, "
                        f"task requires {task.duration_minutes} min)."
                    )
                elif max_gap < task.duration_minutes:
                    reason = (
                        f"No contiguous slot large enough (largest available slot is {max_gap} min, "
                        f"task requires {task.duration_minutes} min)."
                    )
                elif task.deadline is not None:
                    reason = (
                        f"Task deadline ({task.deadline.strftime('%H:%M UTC')}) occurs before "
                        f"an available {task.duration_minutes} min slot can be scheduled."
                    )
                else:
                    reason = "Task availability constraints could not be satisfied within available openings."

                unscheduled_tasks.append(
                    UnscheduledTaskInfo(
                        task_id=task.id,
                        task_title=task.title,
                        required_minutes=task.duration_minutes,
                        priority=task.priority,
                        deadline=task.deadline,
                        reason=reason,
                        max_available_gap_minutes=max_gap,
                        suggested_actions=[
                            "Reduce task duration",
                            "Move to the following day with more free capacity",
                            "Adjust buffer or fixed event commitments",
                        ],
                    )
                )

        # -----------------------------------------------------------------
        # Step 6: Assemble Complete Schedule & Validate Rigorously
        # -----------------------------------------------------------------
        all_blocks = fixed_blocks + buffer_blocks + scheduled_task_blocks + break_blocks
        all_blocks.sort(key=lambda b: (b.start_time, b.end_time))

        validation = validate_schedule(
            blocks=all_blocks,
            working_interval=self.working_interval,
            fixed_events=self.fixed_events,
            tasks_by_id=tasks_by_id,
        )

        total_scheduled = sum(
            b.duration_minutes for b in all_blocks if b.block_type in {"task", "fixed_event"}
        )
        remaining_free_minutes = sum(int((s[1] - s[0]).total_seconds() / 60) for s in mutable_free)

        conflicts: list[str] = [u.reason for u in unscheduled_tasks]
        if not validation.is_valid:
            conflicts.extend(validation.errors)

        status_result: Literal["feasible", "conflict_detected"] = (
            "feasible"
            if len(unscheduled_tasks) == 0 and validation.is_valid
            else "conflict_detected"
        )

        return ScheduleProposal(
            schedule_id=schedule_id,
            target_date=self.target_date,
            timezone=self.timezone_name,
            status=status_result,
            total_scheduled_minutes=total_scheduled,
            total_free_minutes=remaining_free_minutes,
            blocks=all_blocks,
            conflicts=conflicts,
            unscheduled_tasks=unscheduled_tasks,
            validation=validation,
        )

    def _merge_intervals(self, intervals: list[TimeInterval]) -> list[TimeInterval]:
        """Merge overlapping or contiguous intervals into disjoint intervals."""
        if not intervals:
            return []

        sorted_intervals = sorted(intervals, key=lambda x: x.start_time)
        merged: list[TimeInterval] = [sorted_intervals[0]]

        for current in sorted_intervals[1:]:
            previous = merged[-1]
            if current.start_time <= previous.end_time:
                # Merge
                new_end = max(previous.end_time, current.end_time)
                merged[-1] = TimeInterval(start_time=previous.start_time, end_time=new_end)
            else:
                merged.append(current)
        return merged

    def _compute_free_intervals(self, occupied: list[TimeInterval]) -> list[TimeInterval]:
        """Compute free intervals W \\ O within working interval."""
        free: list[TimeInterval] = []
        cursor = self.working_interval.start_time

        for occ in occupied:
            if occ.start_time > cursor:
                gap = TimeInterval(start_time=cursor, end_time=occ.start_time)
                if gap.duration_minutes >= self.minimum_gap_minutes:
                    free.append(gap)
            cursor = max(cursor, occ.end_time)

        if cursor < self.working_interval.end_time:
            final_gap = TimeInterval(start_time=cursor, end_time=self.working_interval.end_time)
            if final_gap.duration_minutes >= self.minimum_gap_minutes:
                free.append(final_gap)

        return free

    def _sort_tasks(self, tasks: list[SchedulableTask]) -> list[SchedulableTask]:
        """Deterministic multi-key sorting comparator:

        1. Priority Rank (P1=1, P2=2, P3=3, P4=4)
        2. Deadline Urgency (Earliest deadline first; None placed last)
        3. Duration LPT (Longest Processing Time first, -duration)
        4. Tie-breaker: Task ID UUID string.
        """
        priority_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}

        def sort_key(t: SchedulableTask) -> tuple[int, datetime, int, str]:
            p_rank = priority_order.get(t.priority, 3)
            d_time = t.deadline if t.deadline is not None else datetime.max.replace(tzinfo=UTC)
            duration_lpt = -t.duration_minutes
            return (p_rank, d_time, duration_lpt, str(t.id))

        return sorted(tasks, key=sort_key)
