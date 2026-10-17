"""OpenAI-powered personal educational copilot agent for Mentor AI.

Orchestrates multi-lingual NLU (Bangla/Banglish/English), OpenAI function calling,
secure task/calendar/Gmail access with strict user isolation, 100-line code enforcement,
safe email draft confirmation gates, Whisper STT, and TTS audio synthesis.
"""

import asyncio
import base64
import hashlib
import io
import json
import re
import uuid
import zoneinfo
from datetime import UTC, datetime
from typing import Any

from google import genai
from google.genai import errors, types
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
    """Production Multi-Provider (Gemini / OpenAI) Personal Educational Copilot Agent."""

    @classmethod
    def get_gemini_client(cls) -> genai.Client | None:
        """Initialize google-genai Client if GEMINI_API_KEY is configured."""
        if not settings.has_gemini_credentials:
            return None
        return genai.Client(api_key=settings.GEMINI_API_KEY.strip())

    @classmethod
    def get_gemini_tools(cls) -> list[types.Tool]:
        """Construct Gemini-compatible FunctionDeclaration list for all 17 agent tools."""
        gemini_funcs: list[types.FunctionDeclaration] = []
        for tool_def in OPENAI_AGENT_TOOLS:
            fn = tool_def["function"]
            name = fn["name"]
            desc = fn.get("description", "")
            params = fn.get("parameters", {"type": "object", "properties": {}})
            cleaned_params: dict[str, Any] = {
                "type": params.get("type", "OBJECT"),
                "properties": params.get("properties", {}),
            }
            if "required" in params:
                cleaned_params["required"] = params["required"]
            decl = types.FunctionDeclaration(
                name=name,
                description=desc,
                parameters=cleaned_params,
            )
            gemini_funcs.append(decl)
        return [types.Tool(function_declarations=gemini_funcs)]

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
    async def _execute_single_tool(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        user_tz: str,
        now_loc: datetime,
        fn_name: str,
        fn_args: dict[str, Any],
        context_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Unified tool execution dispatcher enforcing user isolation, validation, and structured context collection."""
        try:
            if fn_name == "get_today_tasks":
                tool_output = await get_today_tasks(db=db, user_id=user_id, user_tz_str=user_tz)
                context_state["schedule_summary"] = await get_today_schedule(db=db, user_id=user_id, user_tz_str=user_tz)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/tasks",
                    params={"filter": "today"},
                    label="View Today's Tasks",
                )
                return tool_output

            elif fn_name == "get_task_details":
                task_id = str(fn_args.get("task_id", ""))
                return await get_task_details(db=db, user_id=user_id, task_id=task_id)

            elif fn_name == "get_upcoming_deadlines":
                days = int(fn_args.get("days", 7))
                deadlines_list = await get_upcoming_deadlines(db=db, user_id=user_id, user_tz_str=user_tz, days=days)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/tasks",
                    params={"filter": "all"},
                    label="Open Task Backlog",
                )
                return {"upcoming_deadlines": deadlines_list, "days": days}

            elif fn_name == "get_overdue_tasks":
                overdue_list = await get_overdue_tasks(db=db, user_id=user_id, user_tz_str=user_tz)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/tasks",
                    params={"filter": "overdue"},
                    label="View Overdue Tasks",
                )
                return {"overdue_tasks": overdue_list, "count": len(overdue_list)}

            elif fn_name == "get_completed_tasks":
                limit = int(fn_args.get("limit", 10))
                comp_list = await get_completed_tasks(db=db, user_id=user_id, limit=limit)
                return {"completed_tasks": comp_list, "count": len(comp_list)}

            elif fn_name == "get_task_summary":
                tool_output = await get_task_summary(db=db, user_id=user_id, user_tz_str=user_tz)
                from app.services.copilot.accountability import StudentAccountabilityService
                context_state["accountability_data"] = await StudentAccountabilityService.get_accountability_summary(
                    db=db, user_id=user_id
                )
                return tool_output

            elif fn_name == "get_today_calendar_events":
                tool_output = await get_today_calendar_events(db=db, user_id=user_id, user_tz_str=user_tz)
                target_d = tool_output.get("date", now_loc.date().isoformat())
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/calendar",
                    params={"date": target_d, "view": "day"},
                    label=f"Open Calendar for {target_d}",
                )
                return tool_output

            elif fn_name == "get_calendar_events_for_date":
                date_str = str(fn_args.get("date_str", now_loc.date().isoformat()))
                tool_output = await get_calendar_events_for_date(db=db, user_id=user_id, date_str=date_str, user_tz_str=user_tz)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/calendar",
                    params={"date": date_str, "view": "day"},
                    label=f"Open Calendar for {date_str}",
                )
                return tool_output

            elif fn_name == "get_upcoming_calendar_events":
                days = int(fn_args.get("days", 7))
                tool_output = await get_upcoming_calendar_events(db=db, user_id=user_id, user_tz_str=user_tz, days=days)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/calendar",
                    params={"view": "week"},
                    label="View Calendar Schedule",
                )
                return tool_output

            elif fn_name == "get_calendar_event_details":
                event_id = str(fn_args.get("event_id", ""))
                return await get_calendar_event_details(db=db, user_id=user_id, event_id=event_id)

            elif fn_name == "search_gmail_messages":
                query = fn_args.get("query")
                limit = int(fn_args.get("limit", 10))
                tool_output = await search_gmail_messages(db=db, user_id=user_id, query=query, limit=limit)
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/gmail",
                    params={},
                    label="Open Gmail Inbox",
                )
                return tool_output

            elif fn_name == "get_gmail_message":
                message_id = str(fn_args.get("message_id", ""))
                return await get_gmail_message(db=db, user_id=user_id, message_id=message_id)

            elif fn_name == "get_gmail_thread":
                thread_id = str(fn_args.get("thread_id", ""))
                return await get_gmail_thread(db=db, user_id=user_id, thread_id=thread_id)

            elif fn_name == "summarize_gmail_message":
                message_id = str(fn_args.get("message_id", ""))
                return await summarize_gmail_message(db=db, user_id=user_id, message_id=message_id)

            elif fn_name == "prepare_gmail_reply":
                target = str(fn_args.get("target_query_or_recipient", ""))
                intent_desc = str(fn_args.get("reply_intent", ""))
                tool_output = await prepare_gmail_reply_tool(
                    db=db, user_id=user_id, target_query_or_recipient=target, reply_intent=intent_desc
                )
                approval_id = tool_output.get("approval_id")
                context_state["approval_id"] = approval_id
                context_state["email_draft"] = EmailDraftPreview(
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
                context_state["navigation"] = CopilotNavigationTarget(
                    route="/gmail",
                    params={"thread_id": tool_output.get("thread_id") or ""},
                    label="Open Thread in Gmail",
                )
                return tool_output

            elif fn_name == "search_educational_resources":
                q = str(fn_args.get("query", ""))
                tool_output = search_educational_resources_tool(q)
                found_res, _ = EducationalSearchService.search_educational_resources(q)
                context_state["resources"] = found_res
                return tool_output

            elif fn_name == "get_student_accountability":
                tool_output = await get_student_accountability_tool(db=db, user_id=user_id)
                from app.services.copilot.accountability import StudentAccountabilityService
                context_state["accountability_data"] = await StudentAccountabilityService.get_accountability_summary(
                    db=db, user_id=user_id
                )
                return tool_output

            else:
                return {"error": f"Unknown tool: {fn_name}"}

        except Exception as t_err:
            logger.error("Tool execution failed", tool=fn_name, error=str(t_err))
            return {"error": f"Tool execution failed: {t_err}"}

    @classmethod
    async def _process_message_gemini(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        req: CopilotMessageRequest,
        user_tz: str,
        now_loc: datetime,
    ) -> CopilotResponse:
        """Execute agent turn using Google Gemini Free-Tier API (gemini-3.8-flash) with function calling."""
        current_time_str = now_loc.strftime("%A, %B %d, %Y at %I:%M %p")
        system_content = cls.build_system_prompt(user_tz, current_time_str)
        tools = cls.get_gemini_tools()
        config = types.GenerateContentConfig(
            system_instruction=system_content,
            tools=tools,
            temperature=0.3,
        )

        contents: list[types.Content] = []
        for msg in req.conversation_history[-6:]:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)],
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=req.message.strip())],
            )
        )

        model_name = settings.GEMINI_MODEL or "gemini-3.8-flash"
        client = cls.get_gemini_client()
        if not client:
            raise ValueError("Gemini client could not be initialized")

        final_reply = ""
        context_state: dict[str, Any] = {
            "schedule_summary": None,
            "resources": None,
            "email_draft": None,
            "navigation": None,
            "accountability_data": None,
            "approval_id": None,
        }
        tools_invoked: list[str] = []
        tool_results_list: list[dict[str, Any]] = []
        executed_signatures: set[str] = set()

        for round_idx in range(MAX_TOOL_ROUNDS):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except (errors.APIError, errors.ClientError, errors.ServerError, Exception) as api_err:
                logger.error("Gemini content generation failed", error=str(api_err))
                from app.services.copilot.service import CopilotService

                fallback_res = await CopilotService.process_message(db=db, user_id=user_id, req=req)
                err_str = str(api_err)
                is_quota = (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "quota" in err_str.lower()
                    or getattr(api_err, "code", None) == 429
                )
                if is_quota:
                    prefix = (
                        "> [!WARNING]\n"
                        "> **Gemini Free-Tier Rate Limit Reached**: The free-tier request rate limit was temporarily reached. "
                        "Mentor has retrieved your verified schedule and task intelligence directly from your database:\n\n"
                    )
                    spoken = "I reached the free-tier API rate limit, but I have retrieved your schedule and tasks."
                    status_val = "verified"
                else:
                    prefix = (
                        f"> [!WARNING]\n"
                        f"> **AI Provider Notice**: ({err_str}). "
                        "Here is your verified schedule intelligence:\n\n"
                    )
                    spoken = "I experienced a connection issue reaching the AI service, but I have retrieved your schedule."
                    status_val = "error"

                return CopilotResponse(
                    reply=prefix + fallback_res.reply,
                    spoken_reply=spoken,
                    input_mode=req.input_mode,
                    intent=fallback_res.intent,
                    schedule_summary=fallback_res.schedule_summary,
                    resources=fallback_res.resources,
                    navigation=fallback_res.navigation,
                    accountability=fallback_res.accountability,
                    verification_status=status_val,
                )

            if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                logger.warning("Gemini returned empty candidate content")
                break

            candidate = response.candidates[0]
            candidate_content = candidate.content

            # Check if there are function calls
            function_calls = [
                p.function_call for p in candidate_content.parts if p.function_call
            ]

            if not function_calls:
                text_parts = [p.text for p in candidate_content.parts if p.text]
                final_reply = "".join(text_parts)
                break

            # Append model turn containing function calls to contents
            contents.append(candidate_content)

            # Execute tool calls
            response_parts: list[types.Part] = []
            for fc in function_calls:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                if call_sig in executed_signatures:
                    logger.warning("Duplicate Gemini tool invocation prevented", signature=call_sig)
                    err_out = {"error": f"Tool '{fn_name}' was already invoked with identical arguments in this turn."}
                    response_parts.append(
                        types.Part.from_function_response(name=fn_name, response=err_out)
                    )
                    continue

                executed_signatures.add(call_sig)
                tools_invoked.append(fn_name)

                tool_output = await cls._execute_single_tool(
                    db=db,
                    user_id=user_id,
                    user_tz=user_tz,
                    now_loc=now_loc,
                    fn_name=fn_name,
                    fn_args=fn_args,
                    context_state=context_state,
                )
                tool_results_list.append({"tool": fn_name, "args": fn_args, "output": tool_output})
                response_parts.append(
                    types.Part.from_function_response(name=fn_name, response=tool_output)
                )

            contents.append(types.Content(role="user", parts=response_parts))

        # Enforce 100-line limit per code example
        bounded_reply, max_code_lines = enforce_code_line_limits(final_reply)

        # Generate clean spoken version for TTS or browser speech
        spoken_reply = cls._clean_text_for_speech(bounded_reply)

        return CopilotResponse(
            reply=bounded_reply,
            spoken_reply=spoken_reply,
            speech_audio_base64=None,
            speech_audio_format="audio/mpeg",
            input_mode=req.input_mode,
            intent="gemini_agent",
            tools_invoked=tools_invoked,
            tool_results=tool_results_list,
            schedule_summary=context_state["schedule_summary"],
            resources=context_state["resources"],
            email_draft=context_state["email_draft"],
            approval_id=context_state["approval_id"],
            navigation=context_state["navigation"],
            accountability=context_state["accountability_data"],
            code_line_count=max_code_lines,
            verification_status="verified",
        )

    @classmethod
    async def _process_message_openai(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        req: CopilotMessageRequest,
        user_tz: str,
        now_loc: datetime,
        preferred_voice: str = "nova",
    ) -> CopilotResponse:
        """Execute agent turn using OpenAI Chat Completions API with tool calling."""
        client = cls.get_openai_client()
        if not client:
            raise ValueError("OpenAI client could not be initialized")

        current_time_str = now_loc.strftime("%A, %B %d, %Y at %I:%M %p")
        system_content = cls.build_system_prompt(user_tz, current_time_str)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

        for msg in req.conversation_history[-6:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": req.message.strip()})

        context_state: dict[str, Any] = {
            "schedule_summary": None,
            "resources": None,
            "email_draft": None,
            "navigation": None,
            "accountability_data": None,
            "approval_id": None,
        }
        tools_invoked: list[str] = []
        tool_results_list: list[dict[str, Any]] = []
        executed_signatures: set[str] = set()

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

            if not tool_calls:
                final_reply = msg.content or ""
                break

            messages.append(msg.model_dump())

            for tc in tool_calls:
                fn_name = tc.function.name
                fn_args_raw = tc.function.arguments or "{}"
                try:
                    fn_args = json.loads(fn_args_raw)
                except Exception:
                    fn_args = {}

                call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                if call_sig in executed_signatures:
                    logger.warning("Duplicate OpenAI tool invocation prevented", signature=call_sig)
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

                tool_output = await cls._execute_single_tool(
                    db=db,
                    user_id=user_id,
                    user_tz=user_tz,
                    now_loc=now_loc,
                    fn_name=fn_name,
                    fn_args=fn_args,
                    context_state=context_state,
                )
                tool_results_list.append({"tool": fn_name, "args": fn_args, "output": tool_output})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_output),
                    }
                )

        bounded_reply, max_code_lines = enforce_code_line_limits(final_reply)
        spoken_reply = cls._clean_text_for_speech(bounded_reply)

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
            schedule_summary=context_state["schedule_summary"],
            resources=context_state["resources"],
            email_draft=context_state["email_draft"],
            approval_id=context_state["approval_id"],
            navigation=context_state["navigation"],
            accountability=context_state["accountability_data"],
            code_line_count=max_code_lines,
            verification_status="verified",
        )

    @classmethod
    async def process_message(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        req: CopilotMessageRequest,
        preferred_voice: str = "nova",
    ) -> CopilotResponse:
        """Route message to active AI provider (Gemini or OpenAI) with graceful deterministic fallback."""
        user_tz = await resolve_user_timezone(db, user_id, req.client_timezone)
        try:
            tz_obj = zoneinfo.ZoneInfo(user_tz)
        except Exception:
            tz_obj = zoneinfo.ZoneInfo("Asia/Dhaka")
            user_tz = "Asia/Dhaka"

        now_loc = datetime.now(UTC).astimezone(tz_obj)

        active_provider = (settings.AI_PROVIDER or "gemini").lower().strip()

        # Prioritize configured AI provider
        if active_provider == "gemini" and settings.has_gemini_credentials:
            return await cls._process_message_gemini(
                db=db,
                user_id=user_id,
                req=req,
                user_tz=user_tz,
                now_loc=now_loc,
            )

        if active_provider == "openai" and settings.has_openai_credentials:
            return await cls._process_message_openai(
                db=db,
                user_id=user_id,
                req=req,
                user_tz=user_tz,
                now_loc=now_loc,
                preferred_voice=preferred_voice,
            )

        # Fallback to whichever provider is credentialed
        if settings.has_gemini_credentials:
            return await cls._process_message_gemini(
                db=db,
                user_id=user_id,
                req=req,
                user_tz=user_tz,
                now_loc=now_loc,
            )

        if settings.has_openai_credentials:
            return await cls._process_message_openai(
                db=db,
                user_id=user_id,
                req=req,
                user_tz=user_tz,
                now_loc=now_loc,
                preferred_voice=preferred_voice,
            )

        # Neither provider is credentialed: fallback to deterministic Phase 8 service
        logger.info("No AI credentials configured; using deterministic Phase 8 fallback", user_id=str(user_id))
        from app.services.copilot.service import CopilotService
        fallback_res = await CopilotService.process_message(db=db, user_id=user_id, req=req)
        setup_note = (
            "> [!NOTE]\n"
            "> **AI Copilot Setup**: `GEMINI_API_KEY` (Free Tier) or `OPENAI_API_KEY` is not yet configured. "
            "Mentor is currently running in deterministic schedule mode. Set `GEMINI_API_KEY` in Render environment to enable conversational intelligence.\n\n"
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

    @classmethod
    async def transcribe_audio(
        cls, file_bytes: bytes, filename: str = "recording.webm", content_type: str | None = None
    ) -> CopilotTranscribeResponse:
        """Transcribe speech audio using Google Gemini multimodal audio transcription."""
        client = cls.get_gemini_client()
        if not client:
            raise ValueError("Gemini API key is not configured. Speech transcription requires GEMINI_API_KEY.")

        mime_map = {
            ".webm": "audio/webm",
            ".wav": "audio/wav",
            ".mp3": "audio/mp3",
            ".m4a": "audio/m4a",
            ".mp4": "audio/mp4",
            ".ogg": "audio/ogg",
            ".oga": "audio/ogg",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
        }
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".webm"
        detected_mime = content_type or mime_map.get(ext, "audio/webm")
        if detected_mime == "audio/x-m4a":
            detected_mime = "audio/m4a"

        audio_part = types.Part.from_bytes(data=file_bytes, mime_type=detected_mime)
        prompt = (
            "Transcribe the spoken audio verbatim. "
            "Accurately capture Bangla, English, or mixed Banglish speech. "
            "Do not summarize, paraphrase, or answer the speech. "
            "Do not add introductory or concluding remarks (e.g. do not say 'Here is the transcript:'). "
            "Output only the exact transcribed speech text."
        )

        model_name = settings.GEMINI_MODEL or "gemini-3.8-flash"
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[audio_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                ),
            )
            raw_transcript = (response.text or "").strip()
            if (raw_transcript.startswith('"') and raw_transcript.endswith('"')) or (
                raw_transcript.startswith("'") and raw_transcript.endswith("'")
            ):
                raw_transcript = raw_transcript[1:-1].strip()

            return CopilotTranscribeResponse(
                transcript=raw_transcript,
                language=None,
            )
        except (errors.APIError, errors.ClientError, errors.ServerError) as api_err:
            logger.error("Gemini audio transcription API error", error=str(api_err), model=model_name)
            raise
        except (TimeoutError, asyncio.TimeoutError):
            raise
        except Exception as exc:
            logger.error("Gemini audio transcription failed", error=str(exc))
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
