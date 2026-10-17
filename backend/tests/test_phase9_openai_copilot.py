"""Phase 9 Comprehensive Test Suite: OpenAI Copilot Agent, Tools, Security, and Voice Intelligence."""

import base64
import json
import uuid
import zoneinfo
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models.calendar import CalendarEvent
from app.db.models.connection import ExternalConnection
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.main import app
from app.schemas.copilot import (
    CopilotActionConfirmRequest,
    CopilotMessageRequest,
    CopilotPreferencesUpdate,
    CopilotSpeechRequest,
)
from app.services.calendar.service import CalendarService
from app.services.copilot.approval import generate_action_approval, verify_action_approval
from app.services.copilot.tools import (
    get_calendar_events_for_date,
    get_today_calendar_events,
    get_today_tasks,
    search_gmail_messages,
)
from app.services.copilot_agent import CopilotAgent
from app.services.gmail.service import GmailService

@pytest.fixture(autouse=True)
def configure_openai_provider():
    """Ensure tests in this module route specifically to the OpenAI provider without network calls."""
    with patch.object(settings, "AI_PROVIDER", "openai"), patch.object(settings, "GEMINI_API_KEY", ""):
        yield


@pytest.fixture
async def test_session():
    """In-memory SQLite async database engine for isolated Copilot testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def setup_phase9_user(test_session: AsyncSession):
    """Fixture providing user with timezone, task, and calendar entries."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email=f"student_{user_id.hex[:6]}@example.com",
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
            "stt_engine": "openai",
        },
    )
    test_session.add(profile)
    test_session.add(prefs)

    # Add schedule & tasks
    now_utc = datetime.now(UTC)
    tz_dhaka = zoneinfo.ZoneInfo("Asia/Dhaka")
    today_dhaka = now_utc.astimezone(tz_dhaka).date()

    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=today_dhaka,
    )
    test_session.add(schedule)

    task1 = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Automata Theory Assignment 3",
        description="Formal definition of DFA and transition functions",
        status="pending",
        priority="P1",
        duration_minutes=60,
        deadline=datetime.combine(today_dhaka, time(14, 0), tzinfo=UTC),
    )
    test_session.add(task1)

    block1 = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        task_id=task1.id,
        user_id=user_id,
        title="Focus: Automata Theory Assignment 3",
        block_type="task",
        start_time=datetime.combine(today_dhaka, time(9, 0), tzinfo=UTC),
        end_time=datetime.combine(today_dhaka, time(10, 0), tzinfo=UTC),
    )
    test_session.add(block1)

    # Add fixed calendar event
    cal_event = CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title="CSE 420: Compiler Design Lecture",
        start_time=datetime.combine(today_dhaka, time(11, 0), tzinfo=UTC),
        end_time=datetime.combine(today_dhaka, time(12, 30), tzinfo=UTC),
        source="google_calendar",
        location="Room UB201",
        is_fixed=True,
    )
    test_session.add(cal_event)

    await test_session.commit()
    return user_id


# -----------------------------------------------------------------------------
# 1. Unconfigured OpenAI Fallback & Setup Transparency
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_unconfigured_fallback(test_session: AsyncSession, setup_phase9_user):
    """When OPENAI_API_KEY is not configured, preserve deterministic schedule without crashing."""
    user_id = setup_phase9_user
    req = CopilotMessageRequest(message="Give me today's schedule", client_timezone="Asia/Dhaka")

    with patch.object(settings, "OPENAI_API_KEY", ""):
        res = await CopilotAgent.process_message(db=test_session, user_id=user_id, req=req)
        assert res.verification_status == "unconfigured"
        assert "OPENAI_API_KEY" in res.reply
        assert res.schedule_summary is not None
        assert len(res.schedule_summary.scheduled_items) >= 1


# -----------------------------------------------------------------------------
# 2. Smart Task Tool Retrieval
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_smart_task_access_tool(test_session: AsyncSession, setup_phase9_user):
    """Verify get_today_tasks distinguishes scheduled tasks, unscheduled tasks, and deadlines."""
    user_id = setup_phase9_user
    data = await get_today_tasks(db=test_session, user_id=user_id, user_tz_str="Asia/Dhaka")

    assert data["scheduled_tasks_count"] >= 1
    assert any("Automata Theory" in t["title"] for t in data["scheduled_tasks"])
    assert data["timezone"] == "Asia/Dhaka"


# -----------------------------------------------------------------------------
# 3. Google Calendar Tool Retrieval
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_smart_calendar_events_tool(test_session: AsyncSession, setup_phase9_user):
    """Verify get_today_calendar_events retrieves fixed Google Calendar events chronologically."""
    user_id = setup_phase9_user
    data = await get_today_calendar_events(db=test_session, user_id=user_id, user_tz_str="Asia/Dhaka")

    assert "events" in data
    assert any("CSE 420" in e["title"] for e in data["events"])


# -----------------------------------------------------------------------------
# 4. User Isolation in Tools
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_user_isolation_in_tools(test_session: AsyncSession, setup_phase9_user):
    """Verify another user cannot access tasks or calendar data of setup_phase9_user."""
    other_user_id = uuid.uuid4()
    other_profile = Profile(
        id=other_user_id,
        email="stranger@example.com",
        full_name="Stranger User",
        timezone="Asia/Dhaka",
    )
    test_session.add(other_profile)
    await test_session.commit()

    other_tasks = await get_today_tasks(db=test_session, user_id=other_user_id, user_tz_str="Asia/Dhaka")
    assert other_tasks["scheduled_tasks_count"] == 0
    assert len(other_tasks["scheduled_tasks"]) == 0

    other_events = await get_today_calendar_events(db=test_session, user_id=other_user_id, user_tz_str="Asia/Dhaka")
    assert other_events["events_count"] == 0


# -----------------------------------------------------------------------------
# 5. Approval Token Engine & Tamper Invalidation
# -----------------------------------------------------------------------------
def test_approval_token_security():
    """Verify cryptographic signature, user boundary, and draft tamper invalidation."""
    user_id = uuid.uuid4()
    draft = {
        "recipient_email": "instructor@university.edu",
        "subject": "Re: Assignment 3",
        "body": "I will submit tomorrow afternoon.",
        "thread_id": "thread_123",
    }

    # Generate token
    token = generate_action_approval(user_id, "send_email", draft, expires_in_seconds=600)
    assert token is not None

    # Valid check
    valid, msg = verify_action_approval(token, user_id, "send_email", draft)
    assert valid is True
    assert msg == "Approval verified."

    # Tampered draft body -> Must be invalidated!
    tampered_draft = dict(draft, body="I cannot submit anymore.")
    valid_tamper, msg_tamper = verify_action_approval(token, user_id, "send_email", tampered_draft)
    assert valid_tamper is False
    assert "modified after approval" in msg_tamper

    # Tampered recipient -> Must be invalidated!
    tampered_rec = dict(draft, recipient_email="attacker@evil.com")
    valid_rec, msg_rec = verify_action_approval(token, user_id, "send_email", tampered_rec)
    assert valid_rec is False

    # Different user -> Must be invalidated!
    other_user = uuid.uuid4()
    valid_user, msg_user = verify_action_approval(token, other_user, "send_email", draft)
    assert valid_user is False
    assert "different user" in msg_user


# -----------------------------------------------------------------------------
# 6. Mocked OpenAI Function Calling Orchestration
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_agent_tool_calling_loop(test_session: AsyncSession, setup_phase9_user):
    """Test full agent loop when model calls get_today_tasks and generates answer."""
    user_id = setup_phase9_user
    req = CopilotMessageRequest(
        message="Hey Mentor, amar ajker task ki ki?",
        client_timezone="Asia/Dhaka",
        input_mode="text",
    )

    # Mock tool call from OpenAI
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_today_tasks"
    mock_tool_call.function.arguments = "{}"

    mock_msg1 = MagicMock()
    mock_msg1.tool_calls = [mock_tool_call]
    mock_msg1.content = None
    mock_msg1.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_abc123", "type": "function", "function": {"name": "get_today_tasks", "arguments": "{}"}}],
    }

    mock_msg2 = MagicMock()
    mock_msg2.tool_calls = None
    mock_msg2.content = "আজ তোমার একটি scheduled task আছে: Automata Theory Assignment 3 (বিকেল ২টায় deadline)।"

    mock_resp1 = MagicMock(choices=[MagicMock(message=mock_msg1)])
    mock_resp2 = MagicMock(choices=[MagicMock(message=mock_msg2)])

    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(side_effect=[mock_resp1, mock_resp2])

    with patch.object(settings, "OPENAI_API_KEY", "sk-test-key-1234567890"), \
         patch.object(CopilotAgent, "get_openai_client", return_value=mock_openai):
        res = await CopilotAgent.process_message(db=test_session, user_id=user_id, req=req)

        assert "get_today_tasks" in res.tools_invoked
        assert "Automata Theory" in res.reply
        assert res.verification_status == "verified"
        assert res.navigation is not None
        assert res.navigation.route == "/tasks"


# -----------------------------------------------------------------------------
# 7. 100-Line Code Constraint in Agent
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_agent_100_line_code_limit(test_session: AsyncSession, setup_phase9_user):
    """Verify model output containing > 100 lines of code is bounded strictly."""
    user_id = setup_phase9_user
    req = CopilotMessageRequest(message="Show me python quicksort", client_timezone="Asia/Dhaka")

    long_code_lines = ["def step():", *[f"    x_{i} = {i}" for i in range(120)], "    return x_0"]
    raw_reply = "Here is the code:\n```python\n" + "\n".join(long_code_lines) + "\n```"

    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = raw_reply

    mock_resp = MagicMock(choices=[MagicMock(message=mock_msg)])
    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch.object(settings, "OPENAI_API_KEY", "sk-test-key-1234567890"), \
         patch.object(CopilotAgent, "get_openai_client", return_value=mock_openai):
        res = await CopilotAgent.process_message(db=test_session, user_id=user_id, req=req)

        assert res.code_line_count is not None
        assert "focused to 100 lines" in res.reply
        from app.services.copilot.learning import count_code_block_lines
        assert count_code_block_lines(res.reply)[0] <= 103


# -----------------------------------------------------------------------------
# 8. Supported Voice Presets Listing & Sample Text
# -----------------------------------------------------------------------------
def test_supported_voices():
    """Verify supported voice options include perceived masculine and feminine characteristics."""
    voices = CopilotAgent.get_supported_voices()
    assert len(voices) >= 4

    genders = {v.perceived_sound for v in voices}
    assert "masculine" in genders
    assert "feminine" in genders

    voice_ids = {v.id for v in voices}
    assert "nova" in voice_ids
    assert "echo" in voice_ids


# -----------------------------------------------------------------------------
# 9. Voice Transcription via Whisper (Mocked)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audio_transcription_gemini():
    """Verify transcribe_audio parses Gemini transcription response."""
    fake_audio = b"RIFF....WAVEfmt ...."
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "আজকের ক্লাস কয়টায়?"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
        res = await CopilotAgent.transcribe_audio(fake_audio, "test.wav")
        assert res.transcript == "আজকের ক্লাস কয়টায়?"


# -----------------------------------------------------------------------------
# 10. Voice Synthesis via OpenAI TTS (Mocked)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_speech_synthesis_tts():
    """Verify synthesize_speech requests TTS and returns binary audio bytes."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = b"\xff\xfb\x90\x64\x00\x00fake_mp3_data"
    mock_client.audio.speech.create = AsyncMock(return_value=mock_response)

    with patch.object(CopilotAgent, "get_openai_client", return_value=mock_client):
        audio_bytes = await CopilotAgent.synthesize_speech("Hello student", voice_preset="nova")
        assert len(audio_bytes) > 0
        assert b"fake_mp3" in audio_bytes
