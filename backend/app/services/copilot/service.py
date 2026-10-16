"""Mentor AI Educational Copilot Orchestration Service."""

import re
import uuid
import zoneinfo
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.copilot import (
    CopilotMessageRequest,
    CopilotNavigationTarget,
    CopilotResponse,
    CopilotScheduleSummary,
    EducationalResource,
    EmailDraftPreview,
)
from app.services.copilot.accountability import StudentAccountabilityService
from app.services.copilot.email_copilot import CopilotEmailService
from app.services.copilot.learning import (
    enforce_code_line_limits,
    generate_educational_project_roadmap,
    is_complete_project_request,
)
from app.services.copilot.search import EducationalSearchService
from app.services.copilot.system_prompt import COPILOT_SYSTEM_PROMPT
from app.services.copilot.tools import (
    get_overdue_tasks,
    get_schedule_for_date,
    get_today_schedule,
    get_upcoming_deadlines,
    resolve_user_timezone,
)

logger = get_logger("mentor_ai.copilot.service")


class CopilotService:
    """Orchestrates natural language understanding, tools, educational guidance, and voice responses."""

    @classmethod
    async def process_message(
        cls, db: AsyncSession, user_id: uuid.UUID, req: CopilotMessageRequest
    ) -> CopilotResponse:
        """Process incoming user prompt (text or voice transcript) with strict security boundaries."""
        user_tz = await resolve_user_timezone(db, user_id, req.client_timezone)
        prompt = req.message.strip()
        lower = prompt.lower()

        # 1. Intent Classification
        intent = cls._classify_intent(lower)

        # 2. Intent-Specific Tool Execution & Data Retrieval
        schedule_summary: CopilotScheduleSummary | None = None
        resources: list[EducationalResource] | None = None
        email_draft: EmailDraftPreview | None = None
        navigation: CopilotNavigationTarget | None = None
        accountability_data = None
        reply = ""
        verification_status = "verified"

        # CASE 1: Schedule or Calendar Inquiry
        if intent == "schedule_inquiry":
            target_date_str = req.target_date
            if not target_date_str:
                if "tomorrow" in lower:
                    tz_obj = zoneinfo.ZoneInfo(user_tz)
                    tomorrow = datetime.now(UTC).astimezone(tz_obj).date() + timedelta(days=1)
                    target_date_str = tomorrow.isoformat()
                else:
                    tz_obj = zoneinfo.ZoneInfo(user_tz)
                    target_date_str = datetime.now(UTC).astimezone(tz_obj).date().isoformat()

            schedule_summary = await get_schedule_for_date(
                db=db, user_id=user_id, target_date_str=target_date_str, user_tz_str=user_tz
            )

            # Build natural response matching Section 2 specification
            reply = cls._format_schedule_reply(schedule_summary)
            navigation = CopilotNavigationTarget(
                route="/calendar",
                params={"date": target_date_str, "view": "day"},
                label=f"Open Schedule for {target_date_str}",
            )

        # CASE 2: Overdue Tasks Inquiry
        elif intent == "overdue_inquiry":
            overdue_list = await get_overdue_tasks(db=db, user_id=user_id, user_tz_str=user_tz)
            if overdue_list:
                lines = [f"You have {len(overdue_list)} overdue task{'s' if len(overdue_list) != 1 else ''}:"]
                for t in overdue_list:
                    lines.append(f"• **{t['title']}** (Due {t.get('deadline') or 'earlier'}, {t.get('priority', 'P3')})")
                lines.append("\nWould you like me to open your Task Backlog so we can reschedule them?")
                reply = "\n".join(lines)
            else:
                reply = "Great news! You have no overdue tasks right now. All your academic deadlines are on track."

            navigation = CopilotNavigationTarget(
                route="/tasks",
                params={"filter": "overdue"},
                label="View Overdue Tasks",
            )

        # CASE 3: Upcoming Deadlines Inquiry
        elif intent == "deadlines_inquiry":
            deadlines = await get_upcoming_deadlines(db=db, user_id=user_id, user_tz_str=user_tz, days=7)
            if deadlines:
                lines = [f"Here are your upcoming deadlines over the next 7 days:"]
                for d in deadlines:
                    lines.append(f"• **{d['title']}** — Due {d.get('deadline')} ({d.get('priority', 'P3')})")
                lines.append("\nStaying proactive with study sessions will help prevent last-minute stress.")
                reply = "\n".join(lines)
            else:
                reply = "You don't have any pending deadlines in the next 7 days. It's a great time to focus on deep learning or personal projects!"

            navigation = CopilotNavigationTarget(
                route="/tasks",
                params={"filter": "all"},
                label="Open Task Backlog",
            )

        # CASE 4: Educational Resource Discovery
        elif intent == "educational_search":
            found_resources, topic_label = EducationalSearchService.search_educational_resources(prompt)
            resources = found_resources
            lines = [
                f"I found {len(resources)} verified educational resources for **{topic_label}**:",
                "",
            ]
            for idx, res in enumerate(resources, 1):
                badge = f"[{res.platform} • {res.difficulty}]"
                lines.append(f"{idx}. **{res.title}** {badge}")
                lines.append(f"   {res.description}")
                lines.append(f"   *Why recommended*: {res.why_recommended}")
                lines.append(f"   [Open Resource]({res.url})\n")

            lines.append("Would you like to schedule a study session for this topic today?")
            reply = "\n".join(lines)

        # CASE 5: Email Copilot
        elif intent == "email_reply":
            email_draft = await CopilotEmailService.prepare_email_reply(
                db=db, user_id=user_id, prompt=prompt
            )

            if email_draft.status == "draft_ready":
                reply = (
                    f"I found the email thread regarding **{email_draft.subject}** from **{email_draft.recipient_name or email_draft.recipient_email}**.\n\n"
                    f"I have prepared a draft reply for you. Please inspect the preview card below. "
                    f"For your safety, **I will not send this message until you click 'Confirm & Send'**."
                )
                navigation = CopilotNavigationTarget(
                    route="/gmail",
                    params={"thread_id": email_draft.thread_id or ""},
                    label="Open Thread in Gmail",
                )
            elif email_draft.status == "ambiguous_recipient":
                reply = email_draft.clarification_question or "Multiple contacts matched your request. Please specify the recipient."
                verification_status = "clarification_needed"
            else:
                reply = email_draft.clarification_question or "I could not locate an email thread for that request."
                verification_status = "clarification_needed"

        # CASE 6: Programming Education & Tutoring
        elif intent == "programming_education":
            if is_complete_project_request(prompt):
                reply = generate_educational_project_roadmap("Your Project")
            else:
                reply = cls._generate_educational_programming_explanation(prompt)

        # CASE 7: Student Accountability & Consistency
        elif intent == "accountability_inquiry":
            # Run missed session check
            await StudentAccountabilityService.evaluate_missed_sessions(db=db, user_id=user_id)
            accountability_data = await StudentAccountabilityService.get_accountability_summary(
                db=db, user_id=user_id
            )
            reply = (
                f"### Academic Consistency & Progress Summary\n\n"
                f"• **Current Study Streak**: {accountability_data.streak_days} days\n"
                f"• **Completed Today**: {accountability_data.completed_today_count} tasks\n"
                f"• **Missed / Incomplete Sessions**: {accountability_data.missed_sessions_count}\n\n"
                f"{accountability_data.supportive_message}"
            )
            navigation = CopilotNavigationTarget(
                route="/schedule",
                params={},
                label="Open Schedule Timeline",
            )

        # CASE 8: General Guidance / Academic Assistance
        else:
            reply = (
                "Hello! I am Mentor, your educational copilot. "
                "I'm here to help you stay on top of today's schedule, master programming and academic subjects, "
                "find authoritative study resources, and organize your academic communications.\n\n"
                "You can ask me things like:\n"
                "• *'Give me today's schedule'*\n"
                "• *'Suggest a good Math 101 course'*\n"
                "• *'Find a video explaining DFA'*\n"
                "• *'Explain database normalization in Python'*\n"
                "• *'Reply to my course instructor that I will submit tomorrow'*\n"
                "• *'What are my upcoming deadlines?'*"
            )

        # 3. Enforce 100-Line Code Maximum on Output
        bounded_reply, max_lines = enforce_code_line_limits(reply)

        return CopilotResponse(
            reply=bounded_reply,
            intent=intent,
            schedule_summary=schedule_summary,
            resources=resources,
            email_draft=email_draft,
            navigation=navigation,
            accountability=accountability_data,
            code_line_count=max_lines,
            verification_status=verification_status,
        )

    @classmethod
    def _classify_intent(cls, lower: str) -> str:
        """Classify user natural language intent with educational prioritization."""
        # 1. Schedule inquiry
        if any(term in lower for term in ["today's schedule", "todays schedule", "my schedule", "what do i have today", "give me today", "schedule today", "daily schedule", "today plan", "plan today", "schedule for tomorrow"]):
            return "schedule_inquiry"

        # 2. Overdue inquiry
        if any(term in lower for term in ["overdue", "late tasks", "missed tasks"]):
            return "overdue_inquiry"

        # 3. Deadlines inquiry
        if any(term in lower for term in ["deadline", "due date", "upcoming deadlines", "due soon"]):
            return "deadlines_inquiry"

        # 4. Email / Gmail Copilot
        if any(term in lower for term in ["reply to my", "reply to instructor", "reply to professor", "email instructor", "email professor", "send email to", "draft email", "reply email"]):
            return "email_reply"

        # 5. Accountability / Streak
        if any(term in lower for term in ["streak", "missed session", "my progress", "accountability", "how am i doing"]):
            return "accountability_inquiry"

        # 6. Educational Search (Courses, Videos, Tutorials)
        if any(term in lower for term in ["course", "video", "tutorial", "recommend", "suggest", "lecture", "documentation", "docs", "dfa", "math 101", "math101", "bhalo course"]):
            return "educational_search"

        # 7. Programming education
        if any(term in lower for term in ["code", "python", "fastapi", "function", "algorithm", "build", "program", "debug", "error", "sql", "syntax"]):
            return "programming_education"

        return "general_guidance"

    @classmethod
    def _format_schedule_reply(cls, summary: CopilotScheduleSummary) -> str:
        """Format schedule summary into a warm, Siri/JARVIS-inspired response."""
        scheduled_count = len(summary.scheduled_items)
        deadline_count = len(summary.deadlines)

        lines = []
        if scheduled_count > 0 or deadline_count > 0:
            if scheduled_count > 0 and deadline_count > 0:
                lines.append(
                    f"Today you have **{scheduled_count} scheduled item{'s' if scheduled_count != 1 else ''}** "
                    f"and **{deadline_count} deadline{'s' if deadline_count != 1 else ''}**:\n"
                )
            elif scheduled_count > 0:
                lines.append(
                    f"Today you have **{scheduled_count} scheduled item{'s' if scheduled_count != 1 else ''}**:\n"
                )
            else:
                lines.append(
                    f"Today you have **{deadline_count} deadline{'s' if deadline_count != 1 else ''}**:\n"
                )

            # Scheduled items chronologically
            for item in summary.scheduled_items:
                status_icon = "✓ " if item.is_completed else ""
                lines.append(f"• **{item.start_time}** — {status_icon}{item.title} ({item.item_type.replace('_', ' ').capitalize()})")

            # Deadlines
            for dl in summary.deadlines:
                lines.append(f"• Due at **{dl.get('deadline_time') or 'End of Day'}** — {dl['title']} (Deadline)")

            if summary.next_action:
                lines.append(f"\nYour next scheduled focus is **{summary.next_action}**{f' at {summary.next_action_time}' if summary.next_action_time else ''}.")

            lines.append("\nWould you like me to open today's schedule in your Calendar?")
        else:
            lines.append("You have no scheduled tasks or calendar events for today.")
            if summary.unscheduled_tasks:
                lines.append(f"\nHowever, you have {len(summary.unscheduled_tasks)} unscheduled task(s) in your backlog ready to be scheduled.")
                lines.append("Would you like me to find a time for them?")

        return "\n".join(lines)

    @classmethod
    def _generate_educational_programming_explanation(cls, prompt: str) -> str:
        """Generate focused, step-by-step programming tutorial respecting the 100-line rule."""
        lower = prompt.lower()
        if "fastapi" in lower:
            topic = "FastAPI Asynchronous Endpoint"
            code = (
                "from fastapi import FastAPI, Depends, HTTPException, status\n"
                "from pydantic import BaseModel, Field\n\n"
                "app = FastAPI(title='Study Planner API')\n\n"
                "class StudySessionCreate(BaseModel):\n"
                "    subject: str = Field(..., min_length=2, example='Calculus')\n"
                "    duration_minutes: int = Field(default=45, ge=15, le=180)\n\n"
                "@app.post('/sessions', status_code=status.HTTP_201_CREATED)\n"
                "async def create_study_session(session: StudySessionCreate):\n"
                "    \"\"\"Register a new study session with automated validation.\"\"\"\n"
                "    return {'status': 'scheduled', 'data': session.model_dump()}\n"
            )
        elif "dfa" in lower:
            topic = "Deterministic Finite Automaton (DFA) Simulation"
            code = (
                "# DFA accepting binary strings ending in '01'\n"
                "states = {'q0', 'q1', 'q2'}\n"
                "alphabet = {'0', '1'}\n"
                "start_state = 'q0'\n"
                "accept_states = {'q2'}\n\n"
                "transitions = {\n"
                "    ('q0', '0'): 'q1', ('q0', '1'): 'q0',\n"
                "    ('q1', '0'): 'q1', ('q1', '1'): 'q2',\n"
                "    ('q2', '0'): 'q1', ('q2', '1'): 'q0',\n"
                "}\n\n"
                "def simulate_dfa(input_str: str) -> bool:\n"
                "    current_state = start_state\n"
                "    for char in input_str:\n"
                "        if char not in alphabet:\n"
                "            raise ValueError(f'Invalid character: {char}')\n"
                "        current_state = transitions[(current_state, char)]\n"
                "    return current_state in accept_states\n\n"
                "# Test cases\n"
                "assert simulate_dfa('101') is True\n"
                "assert simulate_dfa('100') is False\n"
            )
        else:
            topic = "Modular Python Algorithm"
            code = (
                "def binary_search(arr: list[int], target: int) -> int:\n"
                "    \"\"\"Perform logarithmic binary search on a sorted array.\n"
                "    \n"
                "    Time Complexity: O(log n)\n"
                "    Space Complexity: O(1)\n"
                "    \"\"\"\n"
                "    left, right = 0, len(arr) - 1\n"
                "    while left <= right:\n"
                "        mid = (left + right) // 2\n"
                "        if arr[mid] == target:\n"
                "            return mid\n"
                "        elif arr[mid] < target:\n"
                "            left = mid + 1\n"
                "        else:\n"
                "            right = mid - 1\n"
                "    return -1\n"
            )

        return (
            f"### Concept Explanation: {topic}\n\n"
            f"When learning this concept, focus on the fundamental invariant and data flow:\n"
            f"1. **Core Principle**: Clear division of responsibilities and predictable states.\n"
            f"2. **Algorithm & Complexity**: Optimized transitions avoiding redundant operations.\n"
            f"3. **Common Pitfalls**: Missing boundary conditions or unhandled input types.\n\n"
            f"Here is a self-contained, illustrative educational example:\n\n"
            f"```python\n{code}```\n\n"
            f"Try running this example with your own test inputs. Which part would you like to dive deeper into?"
        )
