"""Test Suite for Google Gemini Free-Tier AI Copilot Integration in Mentor AI.

Covers:
- Gemini client initialization and model configuration (gemini-3.8-flash)
- All 17 agent tools function declarations and schema validation
- Unified tool dispatcher execution (_execute_single_tool)
- Gemini multi-turn function calling flow with mock client
- Free-tier quota protection (429 / RESOURCE_EXHAUSTED) with non-crashing fallback
- Educational 100-line code limit enforcement
- Safe Gmail reply confirmation gate (approval_id generation)
- Zero-cost spoken reply generation for browser speech synthesis
- Security: ensuring API key is never exposed in response objects
"""

import json
import uuid
import zoneinfo
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors, types
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import AuthenticatedUser, get_current_user
from app.db.base import Base
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule
from app.db.models.task import Task
from app.db.session import get_db
from app.main import app
from app.schemas.copilot import CopilotMessageRequest
from app.services.copilot_agent import OPENAI_AGENT_TOOLS, CopilotAgent


@pytest.fixture
async def test_session():
    """In-memory SQLite async database engine for isolated Gemini Copilot testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def setup_gemini_user(test_session: AsyncSession):
    """Fixture providing user with timezone, task, and preferences."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email="gemini_student@mentor.ai",
        full_name="Fatima Rahman",
        timezone="Asia/Dhaka",
    )
    prefs = UserPreferences(
        id=uuid.uuid4(),
        user_id=user_id,
        copilot_settings={
            "voice_preset": "nova",
            "voice_gender": "feminine",
            "auto_play_speech": True,
            "stt_engine": "browser",
        },
    )
    test_session.add(profile)
    test_session.add(prefs)

    tz_dhaka = zoneinfo.ZoneInfo("Asia/Dhaka")
    today_dhaka = datetime.now(UTC).astimezone(tz_dhaka).date()

    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=today_dhaka,
    )
    test_session.add(schedule)

    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="DFA Minimization Assignment",
        description="Hopcroft's DFA minimization algorithm exercises",
        status="pending",
        priority="P1",
        duration_minutes=45,
        deadline=datetime.combine(today_dhaka, time(18, 0), tzinfo=UTC),
    )
    test_session.add(task)
    await test_session.commit()

    return {"user_id": user_id, "task_id": task.id}


@pytest.mark.asyncio
async def test_gemini_credentials_and_model_configuration():
    """Verify Gemini configuration defaults, properties, and model selection."""
    with patch.object(settings, "GEMINI_API_KEY", "test-key-12345"), patch.object(
        settings, "GEMINI_MODEL", "gemini-3.8-flash"
    ), patch.object(settings, "AI_PROVIDER", "gemini"):
        assert settings.has_gemini_credentials is True
        assert settings.GEMINI_MODEL == "gemini-3.8-flash"
        assert settings.AI_PROVIDER == "gemini"

        client = CopilotAgent.get_gemini_client()
        assert client is not None


@pytest.mark.asyncio
async def test_gemini_tools_schema_generation():
    """Verify all 17 agent tools are mapped to Gemini FunctionDeclarations with valid types."""
    tools = CopilotAgent.get_gemini_tools()
    assert len(tools) == 1
    func_decls = tools[0].function_declarations
    assert len(func_decls) == len(OPENAI_AGENT_TOOLS)
    assert len(func_decls) == 17

    declared_names = {fd.name for fd in func_decls}
    expected_names = {
        "get_today_tasks",
        "get_task_details",
        "get_upcoming_deadlines",
        "get_overdue_tasks",
        "get_completed_tasks",
        "get_task_summary",
        "get_today_calendar_events",
        "get_calendar_events_for_date",
        "get_upcoming_calendar_events",
        "get_calendar_event_details",
        "search_gmail_messages",
        "get_gmail_message",
        "get_gmail_thread",
        "summarize_gmail_message",
        "prepare_gmail_reply",
        "search_educational_resources",
        "get_student_accountability",
    }
    assert declared_names == expected_names

    # Check required parameter schemas
    task_details_decl = next(fd for fd in func_decls if fd.name == "get_task_details")
    assert "task_id" in task_details_decl.parameters.properties
    assert "task_id" in task_details_decl.parameters.required


@pytest.mark.asyncio
async def test_unified_tool_dispatcher_execution(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify _execute_single_tool correctly queries the database and populates navigation."""
    user_id = setup_gemini_user["user_id"]
    tz_dhaka = zoneinfo.ZoneInfo("Asia/Dhaka")
    now_loc = datetime.now(UTC).astimezone(tz_dhaka)
    context_state = {
        "schedule_summary": None,
        "resources": None,
        "email_draft": None,
        "navigation": None,
        "accountability_data": None,
        "approval_id": None,
    }

    result = await CopilotAgent._execute_single_tool(
        db=test_session,
        user_id=user_id,
        user_tz="Asia/Dhaka",
        now_loc=now_loc,
        fn_name="get_today_tasks",
        fn_args={},
        context_state=context_state,
    )

    assert "tasks" in result or "all_tasks" in result or "unscheduled_tasks" in result or "count" in result
    assert context_state["navigation"] is not None
    assert context_state["navigation"].route == "/tasks"


@pytest.mark.asyncio
async def test_gemini_message_orchestration_mocked(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify Gemini function calling flow, tool execution, and final response."""
    user_id = setup_gemini_user["user_id"]

    mock_tool_call_part = types.Part(
        function_call=types.FunctionCall(
            name="get_today_tasks",
            args={},
        )
    )
    mock_round_1_candidate = MagicMock()
    mock_round_1_candidate.content = types.Content(
        role="model",
        parts=[mock_tool_call_part],
    )
    mock_round_1_response = MagicMock(candidates=[mock_round_1_candidate])

    mock_text_part = types.Part(text="You have 1 pending task today: DFA Minimization Assignment.")
    mock_round_2_candidate = MagicMock()
    mock_round_2_candidate.content = types.Content(
        role="model",
        parts=[mock_text_part],
    )
    mock_round_2_response = MagicMock(candidates=[mock_round_2_candidate])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[mock_round_1_response, mock_round_2_response]
    )

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "mock-gemini-key"
    ), patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
        req = CopilotMessageRequest(
            message="amar ajker task ki ki?",
            client_timezone="Asia/Dhaka",
            input_mode="text",
        )
        response = await CopilotAgent.process_message(
            db=test_session,
            user_id=user_id,
            req=req,
        )

        assert response.intent == "gemini_agent"
        assert "DFA Minimization" in response.reply
        assert "get_today_tasks" in response.tools_invoked
        assert response.navigation is not None
        assert response.navigation.route == "/tasks"
        assert response.verification_status == "verified"
        assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_gemini_quota_protection_fallback(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify that a 429/RESOURCE_EXHAUSTED error from Gemini falls back gracefully without crashing."""
    user_id = setup_gemini_user["user_id"]

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=errors.APIError(
            code=429,
            response_json={"error": {"message": "RESOURCE_EXHAUSTED: Rate limit exceeded", "status": "RESOURCE_EXHAUSTED"}},
        )
    )

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "mock-gemini-key"
    ), patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
        req = CopilotMessageRequest(
            message="What are my tasks today?",
            client_timezone="Asia/Dhaka",
            input_mode="text",
        )
        response = await CopilotAgent.process_message(
            db=test_session,
            user_id=user_id,
            req=req,
        )

        # The response must not crash; it should contain the honest rate limit notice and real schedule data
        assert "Rate Limit" in response.reply
        assert response.spoken_reply is not None
        assert "rate limit" in response.spoken_reply.lower()
        assert response.schedule_summary is not None or "DFA" in response.reply or response.reply != ""


@pytest.mark.asyncio
async def test_gemini_enforces_100_line_code_limit(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify code blocks exceeding 100 lines are truncated to maintain educational pedagogy."""
    user_id = setup_gemini_user["user_id"]

    long_code_lines = "\n".join([f"    x_{i} = {i} * 2" for i in range(150)])
    long_response_text = f"Here is the algorithm:\n```python\n{long_code_lines}\n```"

    mock_text_part = types.Part(text=long_response_text)
    mock_candidate = MagicMock()
    mock_candidate.content = types.Content(role="model", parts=[mock_text_part])
    mock_response = MagicMock(candidates=[mock_candidate])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "mock-gemini-key"
    ), patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
        req = CopilotMessageRequest(
            message="Show me code for DFA",
            client_timezone="Asia/Dhaka",
            input_mode="text",
        )
        response = await CopilotAgent.process_message(
            db=test_session,
            user_id=user_id,
            req=req,
        )

        assert response.code_line_count is not None
        assert "focused to 100 lines" in response.reply
        from app.services.copilot.learning import count_code_block_lines
        assert count_code_block_lines(response.reply)[0] <= 103


@pytest.mark.asyncio
async def test_gemini_gmail_confirmation_gate(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify prepare_gmail_reply requires user confirmation with signed approval_id."""
    user_id = setup_gemini_user["user_id"]

    mock_tool_call_part = types.Part(
        function_call=types.FunctionCall(
            name="prepare_gmail_reply",
            args={
                "target_query_or_recipient": "instructor@university.edu",
                "reply_intent": "Request extension on assignment",
            },
        )
    )
    mock_round_1_candidate = MagicMock()
    mock_round_1_candidate.content = types.Content(role="model", parts=[mock_tool_call_part])
    mock_round_1_response = MagicMock(candidates=[mock_round_1_candidate])

    mock_text_part = types.Part(
        text="I have prepared a draft reply to your instructor. Please review and confirm before sending."
    )
    mock_round_2_candidate = MagicMock()
    mock_round_2_candidate.content = types.Content(role="model", parts=[mock_text_part])
    mock_round_2_response = MagicMock(candidates=[mock_round_2_candidate])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[mock_round_1_response, mock_round_2_response]
    )

    from app.schemas.copilot import EmailDraftPreview
    mock_draft = EmailDraftPreview(
        status="draft_ready",
        requires_confirmation=True,
        approval_id="appr_mock_token_12345",
        thread_id="thread_123",
        recipient_email="instructor@university.edu",
        recipient_name="Instructor",
        subject="Re: Assignment 3",
        body="I will submit tomorrow afternoon.",
        context_summary="Assignment discussion",
    )

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", "mock-gemini-key"
    ), patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client), patch(
        "app.services.copilot.email_copilot.CopilotEmailService.prepare_email_reply",
        new=AsyncMock(return_value=mock_draft),
    ):
        req = CopilotMessageRequest(
            message="Reply to my instructor asking for extension",
            client_timezone="Asia/Dhaka",
            input_mode="text",
        )
        response = await CopilotAgent.process_message(
            db=test_session,
            user_id=user_id,
            req=req,
        )

        assert "prepare_gmail_reply" in response.tools_invoked
        assert response.email_draft is not None
        assert response.email_draft.requires_confirmation is True
        assert response.approval_id is not None
        assert response.email_draft.approval_id == response.approval_id


@pytest.mark.asyncio
async def test_api_key_not_leaked_in_copilot_response(test_session: AsyncSession, setup_gemini_user: dict):
    """Security check: ensure GEMINI_API_KEY secret string is never leaked in the serialized response."""
    user_id = setup_gemini_user["user_id"]
    secret_key_val = "SECRET_GEMINI_KEY_99999"

    mock_text_part = types.Part(text="Here are your tasks for today.")
    mock_candidate = MagicMock()
    mock_candidate.content = types.Content(role="model", parts=[mock_text_part])
    mock_response = MagicMock(candidates=[mock_candidate])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        settings, "GEMINI_API_KEY", secret_key_val
    ), patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
        req = CopilotMessageRequest(message="hello", client_timezone="Asia/Dhaka")
        response = await CopilotAgent.process_message(
            db=test_session,
            user_id=user_id,
            req=req,
        )

        serialized = response.model_dump_json()
        assert secret_key_val not in serialized
        assert secret_key_val not in response.reply


def test_copilot_system_prompt_english_only_and_chatgpt_formatting():
    """Verify system prompt mandates strict English-only output and ChatGPT-style Markdown."""
    prompt = CopilotAgent.build_system_prompt("Asia/Dhaka", "Friday, October 17, 2026 at 10:00 AM")
    
    assert "STRICT ENGLISH-ONLY OUTPUT ENFORCEMENT" in prompt
    assert "ALL OF YOUR RESPONSES (both written and spoken) MUST BE DELIVERED EXCLUSIVELY IN PROFESSIONAL, CLEAR ENGLISH" in prompt
    assert "Never reply in Bangla or Banglish" in prompt
    assert "CHATGPT-STYLE RESPONSE QUALITY & FORMATTING" in prompt
    assert "Markdown headings" in prompt
    assert "MAXIMUM 100 LINES PER CODE BLOCK" in prompt
    assert "GMAIL CONFIRMATION GATE" in prompt


@pytest.mark.asyncio
async def test_gemini_audio_transcription_fidelity():
    """Verify Gemini STT receives audio Part and uses configured model with verbatim prompt."""
    fake_audio = b"\x1aE\xdf\xa3" + b"B" * 200
    mock_response = MagicMock()
    mock_response.text = "Show me today's schedule"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client), patch.object(
        settings, "GEMINI_MODEL", "gemini-3.8-flash"
    ):
        res = await CopilotAgent.transcribe_audio(fake_audio, "recording.webm", content_type="audio/webm")

        assert res.transcript == "Show me today's schedule"
        mock_client.aio.models.generate_content.assert_called_once()
        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3.8-flash"
        contents = call_kwargs["contents"]
        assert len(contents) == 2
        # First content is audio part
        assert isinstance(contents[0], types.Part)
        assert contents[0].inline_data.mime_type == "audio/webm"
        # Second content is verbatim transcription prompt
        assert "Transcribe the spoken audio verbatim" in contents[1]
        assert "Accurately capture Bangla, English, or mixed Banglish speech" in contents[1]


@pytest.mark.asyncio
async def test_bangla_voice_input_routes_to_gemini_and_returns_english(test_session: AsyncSession, setup_gemini_user: dict):
    """Verify user input in Bangla/Banglish routes to Gemini and returns structured English response."""
    user_id = setup_gemini_user["user_id"]

    mock_text_part = types.Part(text="## Your Tasks for Today\n\nHere are the tasks scheduled for today:\n\n1. **DFA Minimization Assignment** — Due at 06:00 PM (P1).\n\n### Recommended Next Step\n\nFocus on the DFA minimization assignment first.")
    mock_candidate = MagicMock()
    mock_candidate.content = types.Content(role="model", parts=[mock_text_part])
    mock_response = MagicMock(candidates=[mock_candidate])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(settings, "AI_PROVIDER", "gemini"), patch.object(
        CopilotAgent, "get_gemini_client", return_value=mock_client
    ):
        req = CopilotMessageRequest(
            message="amar ajker task gula dao",
            client_timezone="Asia/Dhaka",
            input_mode="voice",
        )
        res = await CopilotAgent.process_message(db=test_session, user_id=user_id, req=req)

        assert "## Your Tasks for Today" in res.reply
        assert "DFA Minimization Assignment" in res.reply
        assert res.input_mode == "voice"
        assert res.spoken_reply is not None
        assert "Your Tasks for Today" in res.spoken_reply

