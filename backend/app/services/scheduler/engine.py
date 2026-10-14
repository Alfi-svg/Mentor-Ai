"""Pure deterministic scheduling engine implementing interval algebra constraint satisfaction."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.services.scheduler.models import (
    FixedEvent,
    SchedulableTask,
    ScheduleBlockProposal,
    ScheduleProposal,
    ScheduleSummary,
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
        # Step 4: Deterministic Multi-Key Sorting with Dependency Resolution
        # -----------------------------------------------------------------
        sorted_tasks, cyclic_unscheduled = self._sort_tasks(self.tasks)

        # -----------------------------------------------------------------
        # Step 5: First-Fit Task Allocation & Break Injection
        # -----------------------------------------------------------------
        scheduled_task_blocks: list[ScheduleBlockProposal] = []
        break_blocks: list[ScheduleBlockProposal] = []
        unscheduled_tasks: list[UnscheduledTaskInfo] = list(cyclic_unscheduled)
        completed_task_end_times: dict[uuid.UUID, datetime] = {}

        # Mutable tracking of remaining free intervals
        mutable_free: list[list[datetime]] = [
            [interval.start_time, interval.end_time] for interval in free_intervals
        ]

        for task in sorted_tasks:
            duration = timedelta(minutes=task.duration_minutes)
            placed = False

            # Check prerequisite task constraints
            min_permissible_start = self.working_interval.start_time
            unmet_prereq_title: str | None = None
            for dep_id in getattr(task, "dependencies", []):
                if dep_id in tasks_by_id:
                    if dep_id not in completed_task_end_times:
                        unmet_prereq_title = tasks_by_id[dep_id].title
                        break
                    else:
                        dep_end = completed_task_end_times[dep_id]
                        if dep_end > min_permissible_start:
                            min_permissible_start = dep_end

            if unmet_prereq_title:
                unscheduled_tasks.append(
                    UnscheduledTaskInfo(
                        task_id=task.id,
                        task_title=task.title,
                        required_minutes=task.duration_minutes,
                        priority=task.priority,
                        deadline=task.deadline,
                        reason=f"Prerequisite task '{unmet_prereq_title}' was not scheduled.",
                        max_available_gap_minutes=0,
                        suggested_actions=[
                            f"Ensure prerequisite task '{unmet_prereq_title}' has sufficient capacity to complete first"
                        ],
                    )
                )
                continue

            for slot_idx, slot in enumerate(mutable_free):
                slot_start, slot_end = slot[0], slot[1]
                candidate_start = max(slot_start, min_permissible_start)
                candidate_end = candidate_start + duration

                if candidate_end > slot_end:
                    continue

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
                            candidate_start = max(dt_limit, min_permissible_start)
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
                completed_task_end_times[task.id] = candidate_end
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

                # Update the remaining slot capacity in mutable_free (preserve pre-gap and post-gap)
                new_openings: list[list[datetime]] = []
                if (
                    candidate_start > slot_start
                    and (candidate_start - slot_start).total_seconds() / 60 >= self.minimum_gap_minutes
                ):
                    new_openings.append([slot_start, candidate_start])

                if (
                    next_free_start < slot_end
                    and (slot_end - next_free_start).total_seconds() / 60 >= self.minimum_gap_minutes
                ):
                    new_openings.append([next_free_start, slot_end])

                mutable_free.pop(slot_idx)
                for opening in new_openings:
                    mutable_free.append(opening)
                mutable_free.sort(key=lambda s: s[0])
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
                if min_permissible_start > self.working_interval.start_time:
                    if total_free < task.duration_minutes:
                        reason = (
                            f"Insufficient total open time ({total_free} min remaining, "
                            f"task requires {task.duration_minutes} min)."
                        )
                    elif max_gap < task.duration_minutes:
                        reason = (
                            f"No contiguous slot large enough after prerequisite completion "
                            f"(largest available slot is {max_gap} min, task requires {task.duration_minutes} min)."
                        )
                    elif task.deadline is not None:
                        reason = (
                            f"Task deadline ({task.deadline.strftime('%I:%M %p UTC')}) occurs before "
                            f"an available slot can be scheduled after prerequisite completion."
                        )
                    else:
                        reason = f"Prerequisite finished too late to accommodate a {task.duration_minutes} min slot."
                elif total_free < task.duration_minutes:
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
                        f"Task deadline ({task.deadline.strftime('%I:%M %p UTC')}) occurs before "
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

        total_working_mins = self.working_interval.duration_minutes
        task_minutes = sum(b.duration_minutes for b in all_blocks if b.block_type == "task")
        fixed_minutes = sum(b.duration_minutes for b in all_blocks if b.block_type == "fixed_event")
        remaining_free_minutes = sum(int((s[1] - s[0]).total_seconds() / 60) for s in mutable_free)
        total_scheduled = sum(
            b.duration_minutes for b in all_blocks if b.block_type in {"task", "fixed_event"}
        )
        utilization = round((task_minutes / total_working_mins * 100), 1) if total_working_mins > 0 else 0.0

        summary = ScheduleSummary(
            total_working_minutes=total_working_mins,
            total_scheduled_task_minutes=task_minutes,
            total_fixed_minutes=fixed_minutes,
            total_free_minutes=remaining_free_minutes,
            utilization_percentage=utilization,
        )

        conflicts: list[str] = [u.reason for u in unscheduled_tasks]
        if not validation.is_valid:
            conflicts.extend(validation.errors)

        status_result: Literal["feasible", "conflict_detected", "partial", "infeasible"] = (
            "feasible"
            if len(unscheduled_tasks) == 0 and validation.is_valid
            else "infeasible"
            if len(unscheduled_tasks) > 0
            else "conflict_detected"
        )

        explanation = self._generate_explanation(
            scheduled_tasks=scheduled_task_blocks,
            unscheduled_tasks=unscheduled_tasks,
            tasks_by_id=tasks_by_id,
        )

        return ScheduleProposal(
            schedule_id=schedule_id,
            target_date=self.target_date,
            timezone=self.timezone_name,
            status=status_result,
            total_scheduled_minutes=total_scheduled,
            total_free_minutes=remaining_free_minutes,
            summary=summary,
            scheduling_explanation=explanation,
            blocks=all_blocks,
            scheduled_blocks=all_blocks,
            conflicts=conflicts,
            unscheduled_tasks=unscheduled_tasks,
            validation=validation,
        )

    def _generate_explanation(
        self,
        scheduled_tasks: list[ScheduleBlockProposal],
        unscheduled_tasks: list[UnscheduledTaskInfo],
        tasks_by_id: dict[uuid.UUID, SchedulableTask],
    ) -> str:
        """Formulate a transparent, human-readable explanation of the scheduling decisions."""
        if not scheduled_tasks and not unscheduled_tasks:
            return "No tasks to schedule for this date."

        explanations: list[str] = []

        ordered_tasks = [b for b in scheduled_tasks if b.block_type == "task" and b.task_id]
        if len(ordered_tasks) >= 2:
            first_b = ordered_tasks[0]
            second_b = ordered_tasks[1]
            t1 = tasks_by_id.get(first_b.task_id) if first_b.task_id else None
            t2 = tasks_by_id.get(second_b.task_id) if second_b.task_id else None
            if t1 and t2 and t1.id in getattr(t2, "dependencies", []):
                explanations.append(
                    f"'{t1.title}' was scheduled before '{t2.title}' to satisfy the required prerequisite dependency."
                )
            elif t1 and t2 and t1.deadline and t2.deadline:
                t1_d = t1.deadline.strftime("%I:%M %p").lstrip("0")
                t2_d = t2.deadline.strftime("%I:%M %p").lstrip("0")
                if t1.deadline < t2.deadline:
                    explanations.append(
                        f"'{t1.title}' has the earlier deadline at {t1_d}, so I recommend completing it before '{t2.title}', which is due at {t2_d}."
                    )
                elif t1.deadline == t2.deadline:
                    explanations.append(
                        f"Both '{t1.title}' and '{t2.title}' have the same deadline at {t1_d}. '{t1.title}' was scheduled first based on higher priority ({t1.priority} vs {t2.priority})."
                    )
            elif t1 and t2 and t1.deadline and not t2.deadline:
                t1_d = t1.deadline.strftime("%I:%M %p").lstrip("0")
                explanations.append(
                    f"'{t1.title}' has a deadline at {t1_d}, so it was prioritized before '{t2.title}', which has no specific deadline."
                )
            elif t1 and t2:
                explanations.append(
                    f"'{t1.title}' ({t1.priority}) was scheduled before '{t2.title}' ({t2.priority}) based on priority and duration fit."
                )
        elif len(ordered_tasks) == 1:
            t = tasks_by_id.get(ordered_tasks[0].task_id) if ordered_tasks[0].task_id else None
            st_time = ordered_tasks[0].start_time.strftime("%I:%M %p").lstrip("0")
            if t and t.deadline:
                dl_time = t.deadline.strftime("%I:%M %p").lstrip("0")
                explanations.append(
                    f"'{t.title}' is scheduled at {st_time} to complete safely before its deadline at {dl_time}."
                )
            elif t:
                explanations.append(
                    f"'{t.title}' is scheduled at {st_time} within your configured working window."
                )

        if unscheduled_tasks:
            for u in unscheduled_tasks:
                explanations.append(f"Notice: '{u.task_title}' cannot fit before its deadline ({u.reason}).")

        if not explanations:
            explanations.append("Deterministic schedule generated respecting deadlines and working hours.")

        return " ".join(explanations)

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

    def _sort_tasks(
        self, tasks: list[SchedulableTask]
    ) -> tuple[list[SchedulableTask], list[UnscheduledTaskInfo]]:
        """Deterministic Earliest-Deadline-First (EDF) comparator with dependency ordering.

        1. Explicit task dependencies: prerequisites precede dependent tasks (topological depth).
        2. Deadline-bound tasks precede open-ended tasks (has_deadline: 0 for deadline, 1 for None).
        3. Earliest deadline timestamp first.
        4. Priority rank tie-breaker (P1=1, P2=2, P3=3, P4=4).
        5. Duration LPT tie-breaker (Longest Processing Time first, -duration).
        6. Deterministic tie-breaker: Task ID UUID string.
        """
        if not tasks:
            return [], []

        tasks_by_id = {t.id: t for t in tasks}
        priority_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}

        def tie_breaker_key(t: SchedulableTask) -> tuple[int, datetime, int, int, str]:
            has_deadline = 0 if t.deadline is not None else 1
            d_time = t.deadline if t.deadline is not None else datetime.max.replace(tzinfo=UTC)
            p_rank = priority_order.get(t.priority, 3)
            duration_lpt = -t.duration_minutes
            return (has_deadline, d_time, p_rank, duration_lpt, str(t.id))

        # Check if any dependencies exist within the task set
        has_internal_deps = any(
            any(dep_id in tasks_by_id and dep_id != t.id for dep_id in getattr(t, "dependencies", []))
            for t in tasks
        )

        if not has_internal_deps:
            # Pure EDF fast path when no dependency graph constraints exist
            return sorted(tasks, key=tie_breaker_key), []

        # Build adjacency graph and in-degrees for Kahn's topological sort
        adj: dict[uuid.UUID, list[uuid.UUID]] = {t.id: [] for t in tasks}
        in_degree: dict[uuid.UUID, int] = {t.id: 0 for t in tasks}

        for t in tasks:
            for dep_id in getattr(t, "dependencies", []):
                if dep_id in tasks_by_id and dep_id != t.id:
                    adj[dep_id].append(t.id)
                    in_degree[t.id] += 1

        ready: list[SchedulableTask] = [
            tasks_by_id[tid] for tid, deg in in_degree.items() if deg == 0
        ]
        ready.sort(key=tie_breaker_key)

        sorted_tasks: list[SchedulableTask] = []
        while ready:
            curr = ready.pop(0)
            sorted_tasks.append(curr)
            for dependent_id in adj[curr.id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    ready.append(tasks_by_id[dependent_id])
                    ready.sort(key=tie_breaker_key)

        cyclic_unscheduled: list[UnscheduledTaskInfo] = []
        if len(sorted_tasks) < len(tasks):
            visited_ids = {t.id for t in sorted_tasks}
            for t in tasks:
                if t.id not in visited_ids:
                    cyclic_unscheduled.append(
                        UnscheduledTaskInfo(
                            task_id=t.id,
                            task_title=t.title,
                            required_minutes=t.duration_minutes,
                            priority=t.priority,
                            deadline=t.deadline,
                            reason=f"Cyclic dependency detected: task '{t.title}' is part of a circular dependency loop.",
                            max_available_gap_minutes=0,
                            suggested_actions=["Remove circular dependencies between tasks"],
                        )
                    )

        return sorted_tasks, cyclic_unscheduled
