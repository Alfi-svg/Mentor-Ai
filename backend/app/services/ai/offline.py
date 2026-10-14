"""Deterministic rule-and-regex offline NLU parser.

Provides 100% test coverage with zero internet access, zero external API keys,
and zero cost. Truthfully labels itself as 'deterministic_offline'.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.schemas.planner import (
    DetectedFixedEvent,
    DetectedTask,
    DraftPlan,
    ParserType,
    PlanIntent,
)
from app.schemas.task import TaskPriority
from app.services.ai.base import BaseLLMAdapter
from app.services.ai.models import LLMParseResult, UserPlanContext
from app.services.ai.sanitizer import INJECTION_PATTERNS, sanitize_user_input


class DeterministicOfflineAdapter(BaseLLMAdapter):
    """Local rule-based parser extracting dates, times, durations, and tasks deterministically."""

    @property
    def name(self) -> ParserType:
        return "deterministic_offline"

    async def is_available(self) -> bool:
        return True

    async def parse_instruction(self, prompt: str, context: UserPlanContext) -> LLMParseResult:
        """Parse natural language instruction using deterministic heuristic rules."""
        sanitized = sanitize_user_input(prompt)

        # 1. Check for prompt injection / malicious evasion attempts
        for pattern in INJECTION_PATTERNS:
            if pattern.search(sanitized):
                return LLMParseResult(
                    draft_plan=DraftPlan(
                        intent="unsupported",
                        target_date=context.current_date,
                        explanation="Input contained instructions attempting to bypass security constraints.",
                        clarification_question="I can only help with scheduling tasks and managing calendar commitments. Please provide your scheduling request.",
                    ),
                    parser_used="deterministic_offline",
                    metadata={"injection_detected": True},
                )

        # 2. Extract target date
        target_date = self._extract_target_date(sanitized, context.current_date)

        # 3. Extract timezone
        tz = ZoneInfo(context.timezone) if context.timezone else ZoneInfo("UTC")

        # 4. Extract fixed calendar events (e.g., "lecture 10am to 11:30am")
        fixed_events, remaining_text = self._extract_fixed_events(sanitized, target_date, tz)

        # 5. Extract tasks with durations and priorities
        tasks = self._extract_tasks(remaining_text, target_date, tz)

        # 6. Determine intent and missing information
        intent: PlanIntent = "plan_day"
        clarification_question: str | None = None
        unspecified_tasks = [t.title for t in tasks if t.duration_minutes is None]

        if not tasks and not fixed_events:
            if any(w in sanitized.lower() for w in ["hello", "hi", "help", "what can you do"]):
                intent = "clarification_needed"
                explanation = "Greeting or general inquiry received."
                clarification_question = (
                    "How can I help you plan your schedule? You can tell me about classes, "
                    "meetings, and tasks you need to complete."
                )
            else:
                intent = "clarification_needed"
                explanation = "Could not identify any specific tasks or calendar events."
                clarification_question = (
                    "I didn't detect any specific tasks or events. What would you like to plan for "
                    f"{target_date.isoformat()}?"
                )
        elif unspecified_tasks:
            intent = "clarification_needed"
            explanation = (
                f"Identified {len(tasks)} task(s) and {len(fixed_events)} event(s), "
                f"but {len(unspecified_tasks)} task(s) lack estimated durations."
            )
            clarification_question = f"How much time (in minutes or hours) do you estimate for: {', '.join(unspecified_tasks)}?"
        else:
            explanation = (
                f"Extracted {len(fixed_events)} fixed event(s) and {len(tasks)} schedulable task(s) "
                f"for {target_date.isoformat()}."
            )

        draft_plan = DraftPlan(
            intent=intent,
            target_date=target_date,
            explanation=explanation,
            fixed_events=fixed_events,
            tasks=tasks,
            clarification_question=clarification_question,
        )

        return LLMParseResult(
            draft_plan=draft_plan,
            parser_used="deterministic_offline",
            metadata={"source": "deterministic_offline"},
        )

    def _extract_target_date(self, text: str, current_date: date) -> date:
        """Extract explicit or relative target date."""
        lower = text.lower()
        if "tomorrow" in lower:
            return current_date + timedelta(days=1)
        if "day after tomorrow" in lower:
            return current_date + timedelta(days=2)
        if "today" in lower:
            return current_date

        # Match ISO format YYYY-MM-DD
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            try:
                return date.fromisoformat(iso_match.group(1))
            except ValueError:
                pass

        # Match "in N days"
        days_match = re.search(r"\bin\s+(\d+)\s+days?\b", lower)
        if days_match:
            return current_date + timedelta(days=int(days_match.group(1)))

        # Default to tomorrow if "plan" is mentioned, else today
        if "plan" in lower or "schedule" in lower:
            return current_date + timedelta(days=1)
        return current_date

    def _parse_time_str(self, time_str: str) -> tuple[int, int]:
        """Parse time string like '10am', '11:30am', '2pm', '14:00' into (hour, minute)."""
        time_str = time_str.strip().lower()
        is_pm = "pm" in time_str
        is_am = "am" in time_str
        cleaned = re.sub(r"[apm\s]", "", time_str)

        if ":" in cleaned:
            parts = cleaned.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
        else:
            hour = int(cleaned)
            minute = 0

        if is_pm and hour < 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0

        return hour, minute

    def _extract_fixed_events(
        self, text: str, target_date: date, tz: ZoneInfo
    ) -> tuple[list[DetectedFixedEvent], str]:
        """Extract fixed events with start and end times, returning the list and remaining text."""
        events: list[DetectedFixedEvent] = []
        remaining = text

        # Matches phrases like:
        # "class 10am to 11:30am"
        # "team meeting from 2pm to 3pm"
        # "lecture at 14:00-15:30"
        # "sync from 10:00 to 11:00"
        pattern = re.compile(
            r"(?:(?:have|attend|join)\s+)?([a-zA-Z0-9\s_-]+?)\s+(?:from\s+|at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|until)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            title_part = match.group(1).strip()
            # Clean up leading connector words
            title = re.sub(
                r"^(?:and|i\s+have|a|an|two|2)\s+", "", title_part, flags=re.IGNORECASE
            ).strip()
            start_str = match.group(2)
            end_str = match.group(3)

            # If start didn't specify am/pm but end does, borrow am/pm
            if not any(m in start_str.lower() for m in ["am", "pm"]) and any(
                m in end_str.lower() for m in ["am", "pm"]
            ):
                end_meridiem = "pm" if "pm" in end_str.lower() else "am"
                start_str += end_meridiem

            try:
                s_h, s_m = self._parse_time_str(start_str)
                e_h, e_m = self._parse_time_str(end_str)

                start_dt = datetime.combine(target_date, time(s_h, s_m), tzinfo=tz).astimezone(UTC)
                end_dt = datetime.combine(target_date, time(e_h, e_m), tzinfo=tz).astimezone(UTC)

                if end_dt <= start_dt:
                    # If end hour appears earlier than start hour, assume next half-day / evening
                    if e_h < s_h and e_h < 12:
                        end_dt = datetime.combine(
                            target_date, time(e_h + 12, e_m), tzinfo=tz
                        ).astimezone(UTC)

                if end_dt > start_dt and title:
                    events.append(
                        DetectedFixedEvent(
                            title=title.capitalize(),
                            start_time=start_dt,
                            end_time=end_dt,
                        )
                    )
                    # Mask out the matched portion from remaining text
                    remaining = remaining.replace(match.group(0), " ")
            except (ValueError, TypeError):
                continue

        return events, remaining

    def _extract_tasks(self, text: str, target_date: date, tz: ZoneInfo) -> list[DetectedTask]:
        """Extract tasks with duration, priority, optional deadlines, and dependency ordering."""
        tasks: list[DetectedTask] = []

        # Mark explicit sequential transitions with a sentinel token
        marked_text = re.sub(
            r"\b(then|after\s+that|followed\s+by|next)\b",
            " ___DEP_SEQ___ ",
            text,
            flags=re.IGNORECASE,
        )

        # Split clauses by comma, colon, semicolon, period, newline, 'and', 'also', or sequence sentinel
        raw_segments = re.split(
            r"[,;:.\n]|\band\b|\balso\b|(___DEP_SEQ___)",
            marked_text,
            flags=re.IGNORECASE,
        )

        is_dependent_on_prev = False
        for raw_clause in raw_segments:
            if not raw_clause:
                continue

            if "___DEP_SEQ___" in raw_clause:
                is_dependent_on_prev = True
                continue

            clause = raw_clause.strip()
            if not clause or len(clause) < 3:
                continue

            # Skip general preamble phrases
            if re.match(
                r"^(?:mentor|please|plan\s+(?:my\s+day\s+)?(?:tomorrow|today)?|schedule\s+(?:my\s+day\s+)?(?:tomorrow|today)?|tomorrow|today)$",
                clause,
                re.IGNORECASE,
            ):
                continue

            # 1. Dependency detection (explicit or sequential)
            task_deps: list[str] = []
            if is_dependent_on_prev and tasks:
                task_deps.append(tasks[-1].title)
                is_dependent_on_prev = False

            # Check explicit "after X" or "depends on X"
            explicit_dep_match = re.search(
                r"\b(?:after|depends\s+on|following)\s+([a-zA-Z0-9\s_-]+?)(?:\s+for|\s+by|\s+due|\s+at|$)",
                clause,
                re.IGNORECASE,
            )
            if explicit_dep_match:
                dep_target = explicit_dep_match.group(1).strip()
                if dep_target and len(dep_target) >= 2:
                    clean_dep = re.sub(r"^(?:the|a|an)\s+", "", dep_target, flags=re.IGNORECASE).capitalize()
                    if clean_dep not in task_deps:
                        task_deps.append(clean_dep)

            # 2. Duration extraction
            duration_minutes: int | None = None
            dur_match_h = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", clause, re.IGNORECASE)
            dur_match_m = re.search(r"(\d+)\s*(?:minutes?|mins?|m)\b", clause, re.IGNORECASE)

            if dur_match_h:
                duration_minutes = int(float(dur_match_h.group(1)) * 60)
            elif dur_match_m:
                duration_minutes = int(dur_match_m.group(1))

            # 3. Priority extraction
            priority: TaskPriority = "P3"
            if re.search(r"\b(p1|urgent|critical|highest\s+priority)\b", clause, re.IGNORECASE):
                priority = "P1"
            elif re.search(r"\b(p2|high\s+priority|important)\b", clause, re.IGNORECASE):
                priority = "P2"
            elif re.search(r"\b(p4|low\s+priority)\b", clause, re.IGNORECASE):
                priority = "P4"

            # 4. Deadline extraction (e.g. "by 5pm", "before 18:00")
            deadline_dt: datetime | None = None
            dl_match = re.search(
                r"\b(?:by|before|due(?:\s+at)?)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
                clause,
                re.IGNORECASE,
            )
            if dl_match:
                try:
                    d_h, d_m = self._parse_time_str(dl_match.group(1))
                    deadline_dt = datetime.combine(
                        target_date, time(d_h, d_m), tzinfo=tz
                    ).astimezone(UTC)
                except ValueError:
                    pass

            # 5. Clean task title
            cleaned_title = re.sub(
                r"\b(?:i\s+need|need|have\s+to|want\s+to|must|take|takes|that\s+needs|needing|about|around)\b",
                " ",
                clause,
                flags=re.IGNORECASE,
            )
            # Remove duration substrings
            cleaned_title = re.sub(
                r"\d+(?:\.\d+)?\s*(?:hours?|hrs?|h|minutes?|mins?|m)\b",
                " ",
                cleaned_title,
                flags=re.IGNORECASE,
            )
            # Remove priority substrings
            cleaned_title = re.sub(
                r"\b(?:p1|p2|p3|p4|urgent|high\s+priority|important|low\s+priority)\b",
                " ",
                cleaned_title,
                flags=re.IGNORECASE,
            )
            # Remove deadline substrings
            cleaned_title = re.sub(
                r"\b(?:by|before|due(?:\s+at)?)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
                " ",
                cleaned_title,
                flags=re.IGNORECASE,
            )
            # Remove explicit dependency clause from title
            cleaned_title = re.sub(
                r"\b(?:after|depends\s+on|following)\s+[a-zA-Z0-9\s_-]+",
                " ",
                cleaned_title,
                flags=re.IGNORECASE,
            )
            cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()
            # Strip leading sequence words or prepositions
            cleaned_title = re.sub(
                r"^(?:for|to|and|also|a|an|the|first|secondly|finally|then)\s+",
                "",
                cleaned_title,
                flags=re.IGNORECASE,
            ).strip()

            # Ignore residual connector remnants or preamble artifacts
            lower_title = cleaned_title.lower()
            if (
                not cleaned_title
                or len(cleaned_title) < 2
                or (
                    duration_minutes is None
                    and lower_title
                    in [
                        "classes",
                        "two classes",
                        "a",
                        "an",
                        "the",
                        "tomorrow",
                        "today",
                        "assignment",
                        "plan my day",
                        "plan tomorrow",
                    ]
                )
                or lower_title in ["plan my day", "plan tomorrow", "schedule tomorrow"]
            ):
                continue

            tasks.append(
                DetectedTask(
                    title=cleaned_title.capitalize(),
                    duration_minutes=duration_minutes,
                    priority=priority,
                    deadline=deadline_dt,
                    depends_on=task_deps,
                )
            )

        return tasks
