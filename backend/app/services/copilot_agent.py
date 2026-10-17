"""OpenAI-powered personal educational copilot agent for Mentor AI.

Orchestrates multi-lingual NLU (Bangla/Banglish/English), OpenAI function calling,
secure task/calendar/Gmail access with strict user isolation, 100-line code enforcement,
safe email draft confirmation gates, Whisper STT, and TTS audio synthesis.
"""

import base64
import hashlib
import io
import json
import re
import uuid
import zoneinfo
from datetime import UTC, datetime
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.copilot import (
    CopilotMessageRequest,
    CopilotNavigationTarget,
    CopilotPreferences,
    CopilotResponse,
    CopilotScheduleItem,
    CopilotScheduleSummary,
    CopilotTranscribeResponse,
    CopilotVoiceOption,
    EducationalResource,
    EmailDraftPreview,
    StudentAccountabilitySummary,
)
from app.services.copilot.approval import generate_action_approval
from app.services.copilot.learning import (
    enforce_code_line_limits,
    generate_educational_project_roadmap,
    is_complete_project_request,
)
from app.services.copilot.search import EducationalSearchService
from app.services.copilot.tools import (
    confirm_and_send_gmail_reply_tool,
    get_calendar_event_details,
    get_calendar_events_for_date,
    get_completed_tasks,
    get_gmail_message,
    get_gmail_thread,
    get_overdue_tasks,
    get_student_accountability_tool,
    get_task_details,
    get_task_summary,
    get_today_calendar_events,
    get_today_schedule,
    get_today_tasks,
    get_upcoming_calendar_events,
    get_upcoming_deadlines,
    prepare_gmail_reply_tool,
    resolve_user_timezone,
    search_educational_resources_tool,
    search_gmail_messages,
    summarize_gmail_message,
)

logger = get_logger("mentor_ai.copilot.agent")

# Maximum tool calling turns to prevent infinite execution loops
MAX_TOOL_ROUNDS = 5

SUPPORTED_VOICE_OPTIONS: list[CopilotVoiceOption] = [
    CopilotVoiceOption(
        id="nova",
        name="Nova",
        perceived_sound="feminine",
        description="Warm, upbeat, and natural tone.",
        sample_text="Hello! I am Mentor, your educational assistant. How can I help with your studies today?",
    ),
    CopilotVoiceOption(
        id="shimmer",
        name="Shimmer",
        perceived_sound="feminine",
        description="Clear, expressive, and friendly tone.",
        sample_text="Good morning! You have scheduled focus blocks and two academic deadlines today.",
    ),
    CopilotVoiceOption(
        id="echo",
        name="Echo",
        perceived_sound="masculine",
        description="Resonant, deep, and conversational tone.",
        sample_text="Hello! I am ready to review your schedule, master concepts, or draft email replies.",
    ),
    CopilotVoiceOption(
        id="onyx",
        name="Onyx",
        perceived_sound="masculine",
        description="Calm, authoritative, and focused tone.",
        sample_text="Welcome back. Let us review your tasks and keep your study streak strong.",
    ),
]


OPENAI_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_today_tasks",
            "description": "Retrieves the user's scheduled tasks, unscheduled tasks in the backlog, today's deadlines, and next focus action.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_details",
            "description": "Retrieves full details for a specific task using its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The UUID of the task"}
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_deadlines",
            "description": "Retrieves academic deadlines occurring within the next N days (default 7 days).",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days ahead to search (default 7)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_overdue_tasks",
            "description": "Retrieves incomplete tasks whose deadlines have elapsed.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_completed_tasks",
            "description": "Retrieves recently completed tasks to review academic progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of completed tasks (default 10)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_summary",
            "description": "Retrieves student consistency metrics, current study streak days, completed tasks today, and overdue count.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_calendar_events",
            "description": "Retrieves fixed external Google Calendar events for today in user's timezone.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events_for_date",
            "description": "Retrieves external Google Calendar events for a specific date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Target date in YYYY-MM-DD format"}
                },
                "required": ["date_str"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_calendar_events",
            "description": "Retrieves upcoming external calendar events for the next N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to inspect (default 7)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_event_details",
            "description": "Retrieves full details for a specific calendar event by its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Event UUID"}
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_gmail_messages",
            "description": "Searches or lists recent Gmail messages in the user's connected account. Use to check new or unread emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search term, sender, or query (e.g. 'is:unread', 'instructor', 'exam')"},
                    "limit": {"type": "integer", "description": "Max messages to return (default 10, max 25)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gmail_message",
            "description": "Retrieves the full body, sender, subject, date, and details of a specific Gmail message by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The Gmail message ID"}
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gmail_thread",
            "description": "Retrieves all messages in a specific email thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "The Gmail thread ID"}
                },
                "required": ["thread_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_gmail_message",
            "description": "Produces a concise summary of an email message, highlighting verified dates, deadlines, and action items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The Gmail message ID"}
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_gmail_reply",
            "description": "Drafts a safe, context-aware reply to an email thread. Previews the recipient, subject, and draft body. NEVER sends the email directly; requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_query_or_recipient": {"type": "string", "description": "Recipient name, email address, or search keyword (e.g. 'instructor', 'professor', 'Dr. Smith')"},
                    "reply_intent": {"type": "string", "description": "The intended message (e.g. 'I will submit assignment tomorrow', 'asking for meeting')"}
                },
                "required": ["target_query_or_recipient", "reply_intent"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_educational_resources",
            "description": "Searches verified educational courses, lectures, video tutorials, and documentation (MIT OCW, Khan Academy, 3Blue1Brown, Stanford, official docs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Academic topic, course name, or concept (e.g. 'DFA', 'Math 101', 'FastAPI')"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_accountability",
            "description": "Retrieves student consistency metrics, current streak days, missed sessions, and recovery suggestions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]


class CopilotAgent:
    """Production OpenAI-powered Personal Educational Copilot Agent."""

    @classmethod
    def get_openai_client(cls) -> AsyncOpenAI | None:
        """Initialize AsyncOpenAI client if API key is configured."""
        if not settings.has_openai_credentials:
            return None
        return AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES,
        )

    @classmethod
    def build_system_prompt(cls, user_tz_str: str, current_time_str: str) -> str:
        """Construct authoritative system instructions bounding agent to educational life orchestration."""
        return f"""You are Mentor, a personal AI educational copilot inspired by Siri and JARVIS, built to help students stay organized, master academic concepts, and achieve their educational goals.

CURRENT USER CONTEXT:
- Timezone: {user_tz_str}
- Current Local Date & Time: {current_time_str}

CORE CAPABILITIES & TOOLS:
1. Schedule & Tasks: Check today's schedule, deadlines, overdue tasks, and task details using authorized tools. Distinguish scheduled task blocks from fixed external Google Calendar events.
2. Google Calendar: Inspect real Google Calendar events. If disconnected or expired, honestly explain without disguising the error.
3. Gmail: Check new or unread emails, read email details, summarize messages, and draft contextual replies.
4. Educational Discovery: Search verified courses, video tutorials, and documentation from authoritative platforms (MIT OCW, Khan Academy, 3Blue1Brown, Stanford, official docs).
5. Student Growth: Track study streaks, review missed sessions, and provide constructive recovery plans.

STRICT OPERATIONAL SAFETY & EXECUTION BOUNDARIES:
- DO NOT execute arbitrary shell commands, SQL queries, or unrestricted web scraping.
- DO NOT generate complete monolithic software projects. If a user asks to build an entire application or project, explain that you are an educational tutor, break the problem into an architectural roadmap with modular steps, and provide focused code examples.
- MAXIMUM 100 LINES PER CODE BLOCK: Every code example MUST NOT exceed 100 lines. Focus on educational clarity and fundamental invariants.
- GMAIL CONFIRMATION GATE: When drafting an email reply, ALWAYS use `prepare_gmail_reply`. NEVER claim an email has been sent. Explain that the draft is ready and that you are waiting for their explicit confirmation before sending.
- REAL DATA ONLY: Never fabricate task items, calendar events, or email messages. If a tool returns no items or an error, state that truthfully.
- MULTI-LINGUAL SUPPORT: You are completely fluent in Bangla (বাংলা), Banglish (e.g. "amar ajker task ki ki?", "notun mail ashche?"), and English. Reply naturally in the language or dialect used by the user. Keep spoken responses warm, concise, and helpful. Avoid reading raw IDs, JSON, or markdown asterisks in spoken output.
"""

    @classmethod
    async def process_message(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        req: CopilotMessageRequest,
        preferred_voice: str = "nova",
    ) -> CopilotResponse:
        """Execute single agent orchestration cycle for text or voice interactions."""
        user_tz = await resolve_user_timezone(db, user_id, req.client_timezone)
        try:
            tz_obj = zoneinfo.ZoneInfo(user_tz)
        except Exception:
            tz_obj = zoneinfo.ZoneInfo("Asia/Dhaka")
            user_tz = "Asia/Dhaka"

        now_loc = datetime.now(UTC).astimezone(tz_obj)
        current_time_str = now_loc.strftime("%A, %B %d, %Y at %I:%M %p")

        client = cls.get_openai_client()

        # If OpenAI is not configured, preserve deterministic fallback without crashing
        if not client:
            logger.info("OpenAI API key not configured; using deterministic Phase 8 fallback", user_id=str(user_id))
            from app.services.copilot.service import CopilotService
            fallback_res = await CopilotService.process_message(db=db, user_id=user_id, req=req)
            # Add honest setup message while preserving data
            setup_note = (
                "> [!NOTE]\n"
                "> **OpenAI Agent Setup**: `OPENAI_API_KEY` is not yet configured on the backend. "
                "Mentor is currently running in deterministic schedule mode. Set `OPENAI_API_KEY` in Render environment to enable full conversational agent intelligence.\n\n"
            )
            return CopilotResponse(
                reply=setup_note + fallback_res.reply,
                spoken_reply=fallback_res.reply,
                input_mode=req.input_mode,
                intent=fallback_res.intent,
                schedule_summary=fallback_res.schedule_summary,
                resources=fallback_res.resources,
                email_draft=fallback_res.email_draft,
                approval_id=fallback_res.email_draft.approval_id if fallback_res.email_draft else None,
                navigation=fallback_res.navigation,
                accountability=fallback_res.accountability,
                code_line_count=fallback_res.code_line_count,
                verification_status="unconfigured",
            )

        # Build message history for OpenAI
        system_content = cls.build_system_prompt(user_tz, current_time_str)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

        # Include recent conversation context (last 6 messages)
        for msg in req.conversation_history[-6:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": req.message.strip()})

        # Structured state collected from tools
        tools_invoked: list[str] = []
        tool_results_list: list[dict[str, Any]] = []
        schedule_summary: CopilotScheduleSummary | None = None
        resources: list[EducationalResource] | None = None
        email_draft: EmailDraftPreview | None = None
        navigation: CopilotNavigationTarget | None = None
        accountability_data: StudentAccountabilitySummary | None = None
        approval_id: str | None = None

        executed_signatures: set[str] = set()

        # Function calling loop
        model_name = settings.OPENAI_MODEL or "gpt-4o-mini"
        final_reply = ""

        for round_idx in range(MAX_TOOL_ROUNDS):
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=OPENAI_AGENT_TOOLS,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except Exception as api_err:
                logger.error("OpenAI chat completion failed", error=str(api_err))
                # Fall back to deterministic response on API failure
                from app.services.copilot.service import CopilotService
                fallback_res = await CopilotService.process_message(db=db, user_id=user_id, req=req)
                return CopilotResponse(
                    reply=f"I experienced an issue communicating with the AI intelligence layer ({api_err}). Here is your deterministic schedule intelligence:\n\n" + fallback_res.reply,
                    spoken_reply="I experienced an issue reaching the AI service, but I have retrieved your schedule.",
                    input_mode=req.input_mode,
                    intent=fallback_res.intent,
                    schedule_summary=fallback_res.schedule_summary,
                    resources=fallback_res.resources,
                    navigation=fallback_res.navigation,
                    accountability=fallback_res.accountability,
                    verification_status="error",
                )

            choice = response.choices[0]
            msg = choice.message
            tool_calls = msg.tool_calls or []

            # If no tool calls, model gave final answer
            if not tool_calls:
                final_reply = msg.content or ""
                break

            # Append assistant message with tool calls to history
            messages.append(msg.model_dump())

            # Execute tool calls
            for tc in tool_calls:
                fn_name = tc.function.name
                fn_args_raw = tc.function.arguments or "{}"
                try:
                    fn_args = json.loads(fn_args_raw)
                except Exception:
                    fn_args = {}

                # Loop prevention signature check
                call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                if call_sig in executed_signatures:
                    logger.warning("Duplicate tool invocation prevented", signature=call_sig)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"error": f"Tool '{fn_name}' was already invoked with identical arguments in this turn."}),
                        }
                    )
                    continue

                executed_signatures.add(call_sig)
                tools_invoked.append(fn_name)

                # Tool execution dispatcher with strict user isolation
                tool_output: dict[str, Any] = {}
                try:
                    if fn_name == "get_today_tasks":
                        tool_output = await get_today_tasks(db=db, user_id=user_id, user_tz_str=user_tz)
                        schedule_summary = await get_today_schedule(db=db, user_id=user_id, user_tz_str=user_tz)
                        navigation = CopilotNavigationTarget(
                            route="/tasks",
                            params={"filter": "today"},
                            label="View Today's Tasks",
                        )

                    elif fn_name == "get_task_details":
                        task_id = str(fn_args.get("task_id", ""))
                        tool_output = await get_task_details(db=db, user_id=user_id, task_id=task_id)

                    elif fn_name == "get_upcoming_deadlines":
                        days = int(fn_args.get("days", 7))
                        deadlines_list = await get_upcoming_deadlines(db=db, user_id=user_id, user_tz_str=user_tz, days=days)
                        tool_output = {"upcoming_deadlines": deadlines_list, "days": days}
                        navigation = CopilotNavigationTarget(
                            route="/tasks",
                            params={"filter": "all"},
                            label="Open Task Backlog",
                        )

                    elif fn_name == "get_overdue_tasks":
                        overdue_list = await get_overdue_tasks(db=db, user_id=user_id, user_tz_str=user_tz)
                        tool_output = {"overdue_tasks": overdue_list, "count": len(overdue_list)}
                        navigation = CopilotNavigationTarget(
                            route="/tasks",
                            params={"filter": "overdue"},
                            label="View Overdue Tasks",
                        )

                    elif fn_name == "get_completed_tasks":
                        limit = int(fn_args.get("limit", 10))
                        comp_list = await get_completed_tasks(db=db, user_id=user_id, limit=limit)
                        tool_output = {"completed_tasks": comp_list, "count": len(comp_list)}

                    elif fn_name == "get_task_summary":
                        tool_output = await get_task_summary(db=db, user_id=user_id, user_tz_str=user_tz)
                        from app.services.copilot.accountability import StudentAccountabilityService
                        accountability_data = await StudentAccountabilityService.get_accountability_summary(
                            db=db, user_id=user_id
                        )

                    elif fn_name == "get_today_calendar_events":
                        tool_output = await get_today_calendar_events(db=db, user_id=user_id, user_tz_str=user_tz)
                        target_d = tool_output.get("date", now_loc.date().isoformat())
                        navigation = CopilotNavigationTarget(
                            route="/calendar",
                            params={"date": target_d, "view": "day"},
                            label=f"Open Calendar for {target_d}",
                        )

                    elif fn_name == "get_calendar_events_for_date":
                        date_str = str(fn_args.get("date_str", now_loc.date().isoformat()))
                        tool_output = await get_calendar_events_for_date(db=db, user_id=user_id, date_str=date_str, user_tz_str=user_tz)
                        navigation = CopilotNavigationTarget(
                            route="/calendar",
                            params={"date": date_str, "view": "day"},
                            label=f"Open Calendar for {date_str}",
                        )

                    elif fn_name == "get_upcoming_calendar_events":
                        days = int(fn_args.get("days", 7))
                        tool_output = await get_upcoming_calendar_events(db=db, user_id=user_id, user_tz_str=user_tz, days=days)
                        navigation = CopilotNavigationTarget(
                            route="/calendar",
                            params={"view": "week"},
                            label="View Calendar Schedule",
                        )

                    elif fn_name == "get_calendar_event_details":
                        event_id = str(fn_args.get("event_id", ""))
                        tool_output = await get_calendar_event_details(db=db, user_id=user_id, event_id=event_id)

                    elif fn_name == "search_gmail_messages":
                        query = fn_args.get("query")
                        limit = int(fn_args.get("limit", 10))
                        tool_output = await search_gmail_messages(db=db, user_id=user_id, query=query, limit=limit)
                        navigation = CopilotNavigationTarget(
                            route="/gmail",
                            params={},
                            label="Open Gmail Inbox",
                        )

                    elif fn_name == "get_gmail_message":
                        message_id = str(fn_args.get("message_id", ""))
                        tool_output = await get_gmail_message(db=db, user_id=user_id, message_id=message_id)

                    elif fn_name == "get_gmail_thread":
                        thread_id = str(fn_args.get("thread_id", ""))
                        tool_output = await get_gmail_thread(db=db, user_id=user_id, thread_id=thread_id)

                    elif fn_name == "summarize_gmail_message":
                        message_id = str(fn_args.get("message_id", ""))
                        tool_output = await summarize_gmail_message(db=db, user_id=user_id, message_id=message_id)

                    elif fn_name == "prepare_gmail_reply":
                        target = str(fn_args.get("target_query_or_recipient", ""))
                        intent_desc = str(fn_args.get("reply_intent", ""))
                        tool_output = await prepare_gmail_reply_tool(
                            db=db, user_id=user_id, target_query_or_recipient=target, reply_intent=intent_desc
                        )
                        approval_id = tool_output.get("approval_id")
                        email_draft = EmailDraftPreview(
                            thread_id=tool_output.get("thread_id"),
                            recipient_email=tool_output.get("recipient_email", ""),
                            recipient_name=tool_output.get("recipient_name"),
                            subject=tool_output.get("subject", ""),
                            body=tool_output.get("body", ""),
                            context_summary=tool_output.get("context_summary"),
                            requires_confirmation=True,
                            approval_id=approval_id,
                            status=tool_output.get("status", "draft_ready"),
                            clarification_question=tool_output.get("clarification_question"),
                            candidates=tool_output.get("candidates"),
                        )
                        navigation = CopilotNavigationTarget(
                            route="/gmail",
                            params={"thread_id": tool_output.get("thread_id") or ""},
                            label="Open Thread in Gmail",
                        )

                    elif fn_name == "search_educational_resources":
                        q = str(fn_args.get("query", ""))
                        tool_output = search_educational_resources_tool(q)
                        found_res, _ = EducationalSearchService.search_educational_resources(q)
                        resources = found_res

                    elif fn_name == "get_student_accountability":
                        tool_output = await get_student_accountability_tool(db=db, user_id=user_id)
                        from app.services.copilot.accountability import StudentAccountabilityService
                        accountability_data = await StudentAccountabilityService.get_accountability_summary(
                            db=db, user_id=user_id
                        )

                    else:
                        tool_output = {"error": f"Unknown tool: {fn_name}"}

                except Exception as t_err:
                    logger.error("Tool execution failed", tool=fn_name, error=str(t_err))
                    tool_output = {"error": f"Tool execution failed: {t_err}"}

                tool_results_list.append({"tool": fn_name, "args": fn_args, "output": tool_output})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_output),
                    }
                )

        # Enforce 100-line limit per code example
        bounded_reply, max_code_lines = enforce_code_line_limits(final_reply)

        # Generate clean spoken version for TTS
        spoken_reply = cls._clean_text_for_speech(bounded_reply)

        # If voice mode was requested, synthesize audio
        speech_audio_b64: str | None = None
        if req.input_mode == "voice" and client:
            voice_to_use = req.voice_preset or preferred_voice or settings.OPENAI_DEFAULT_VOICE or "nova"
            try:
                audio_bytes = await cls.synthesize_speech(spoken_reply, voice_preset=voice_to_use)
                speech_audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            except Exception as tts_err:
                logger.warning("TTS generation failed during message processing", error=str(tts_err))

        return CopilotResponse(
            reply=bounded_reply,
            spoken_reply=spoken_reply,
            speech_audio_base64=speech_audio_b64,
            speech_audio_format="audio/mpeg",
            input_mode=req.input_mode,
            intent="openai_agent",
            tools_invoked=tools_invoked,
            tool_results=tool_results_list,
            schedule_summary=schedule_summary,
            resources=resources,
            email_draft=email_draft,
            approval_id=approval_id,
            navigation=navigation,
            accountability=accountability_data,
            code_line_count=max_code_lines,
            verification_status="verified",
        )

    @classmethod
    async def transcribe_audio(cls, file_bytes: bytes, filename: str = "recording.webm") -> CopilotTranscribeResponse:
        """Transcribe speech audio file using OpenAI Whisper STT model."""
        client = cls.get_openai_client()
        if not client:
            raise ValueError("OpenAI API key is not configured. Speech transcription requires OPENAI_API_KEY.")

        buffer = io.BytesIO(file_bytes)
        buffer.name = filename

        stt_model = settings.OPENAI_STT_MODEL or "whisper-1"
        try:
            transcript_obj = await client.audio.transcriptions.create(
                model=stt_model,
                file=buffer,
            )
            return CopilotTranscribeResponse(
                transcript=transcript_obj.text.strip(),
                language=getattr(transcript_obj, "language", None),
            )
        except (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        ) as api_err:
            logger.error("OpenAI Whisper STT API error", error=str(api_err), model=stt_model)
            raise
        except Exception as exc:
            logger.error("Whisper transcription failed", error=str(exc))
            raise RuntimeError(f"Speech transcription failed: {exc}") from exc

    @classmethod
    async def synthesize_speech(cls, text: str, voice_preset: str = "nova") -> bytes:
        """Synthesize spoken audio using OpenAI TTS API."""
        client = cls.get_openai_client()
        if not client:
            raise ValueError("OpenAI API key is not configured. Speech synthesis requires OPENAI_API_KEY.")

        # Clean text and bound to safe length
        clean_text = cls._clean_text_for_speech(text)[:4096]
        if not clean_text or not clean_text.strip():
            clean_text = "I am ready to help."

        # Validate voice preset against supported OpenAI TTS presets
        valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        selected_voice = voice_preset.lower() if voice_preset.lower() in valid_voices else "nova"

        # Check TTS model compatibility
        valid_models = {"tts-1", "tts-1-hd"}
        tts_model = settings.OPENAI_TTS_MODEL if settings.OPENAI_TTS_MODEL in valid_models else "tts-1"

        try:
            response = await client.audio.speech.create(
                model=tts_model,
                voice=selected_voice,
                input=clean_text,
            )
            if hasattr(response, "content") and isinstance(response.content, bytes) and response.content:
                return response.content
            if hasattr(response, "aread") and callable(response.aread):
                res = response.aread()
                if hasattr(res, "__await__"):
                    return await res
                if isinstance(res, bytes):
                    return res
            if hasattr(response, "read") and callable(response.read):
                res = response.read()
                if hasattr(res, "__await__"):
                    return await res
                if isinstance(res, bytes):
                    return res
            return getattr(response, "content", b"")
        except (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        ) as api_err:
            logger.error("OpenAI TTS speech synthesis API error", error=str(api_err), voice=selected_voice, model=tts_model)
            raise
        except Exception as exc:
            logger.error("OpenAI TTS speech synthesis failed", error=str(exc))
            raise RuntimeError(f"Text-to-speech synthesis failed: {exc}") from exc

    @classmethod
    def get_supported_voices(cls) -> list[CopilotVoiceOption]:
        """Return supported voice preset options with acoustic descriptions."""
        return SUPPORTED_VOICE_OPTIONS

    @classmethod
    def _clean_text_for_speech(cls, text: str) -> str:
        """Remove markdown artifacts, code blocks, raw JSON, tool signatures, and URLs for natural spoken playback."""
        if not text:
            return ""

        # Remove fenced code blocks
        clean = re.sub(r"```[\s\S]*?```", "Here is a code example.", text)

        # Remove JSON-like payload blocks (e.g. {"tool": ..., ...} or {...})
        clean = re.sub(r"\{[^{}]*\"[a-zA-Z0-9_-]+\"\s*:[^{}]*\}", "", clean)
        clean = re.sub(r"\{[\s\S]*?\}", "", clean)

        # Remove markdown GitHub alert headers like > [!NOTE], > [!IMPORTANT]
        clean = re.sub(r">\s*\[!.*?\]", "", clean)
        clean = re.sub(r"^>+\s*", "", clean, flags=re.MULTILINE)

        # Remove internal tool names/signatures like get_today_tasks(), prepare_gmail_reply(...)
        clean = re.sub(
            r"\b(get_today_tasks|get_task_details|get_upcoming_deadlines|get_overdue_tasks|get_completed_tasks|get_task_summary|get_today_calendar_events|get_calendar_events_for_date|get_upcoming_calendar_events|get_calendar_event_details|search_gmail_messages|get_gmail_message|get_gmail_thread|summarize_gmail_message|prepare_gmail_reply|search_educational_resources|get_student_accountability)\([^)]*\)",
            "",
            clean,
        )
        clean = re.sub(
            r"\b(get_today_tasks|get_task_details|get_upcoming_deadlines|get_overdue_tasks|get_completed_tasks|get_task_summary|get_today_calendar_events|get_calendar_events_for_date|get_upcoming_calendar_events|get_calendar_event_details|search_gmail_messages|get_gmail_message|get_gmail_thread|summarize_gmail_message|prepare_gmail_reply|search_educational_resources|get_student_accountability)\b",
            "",
            clean,
        )

        # Remove UUIDs and approval tokens
        clean = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "", clean)
        clean = re.sub(r"\bappr_[0-9a-fA-F]+\b", "", clean)

        # Remove markdown table rows and separators
        clean = re.sub(r"\|[^\n]+\|", "", clean)
        clean = re.sub(r"[-:]{3,}", "", clean)

        # Remove markdown links, keep anchor label
        clean = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean)
        # Remove standalone URLs
        clean = re.sub(r"https?://\S+", "", clean)
        # Remove markdown bold/italics/headers/bullets/backticks
        clean = re.sub(r"[*_#`~]", "", clean)
        clean = re.sub(r"^\s*[-+*]\s+", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"^\s*\d+\.\s+", "", clean, flags=re.MULTILINE)

        # Replace multiple newlines with single period
        clean = re.sub(r"\n+", ". ", clean)
        # Collapse multiple spaces and trim
        clean = re.sub(r"\s+", " ", clean).strip()
        # Clean up double periods or trailing punctuation
        clean = re.sub(r"\.{2,}", ".", clean)
        clean = re.sub(r"\s+\.", ".", clean)
        return clean.strip()
