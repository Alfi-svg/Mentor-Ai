"""Comprehensive Test Suite for Phase 9 Step 3: Production-Ready Voice Configuration.

Tests speech-to-text (Whisper), text-to-speech (TTS), audio validation, provider failure modes,
per-user isolation, voice preference persistence, unified agent tool execution, and speech text sanitization.
"""

import base64
import io
import json
import uuid
import zoneinfo
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import AuthenticatedUser, get_current_user
from app.db.base import Base
from app.db.models.profile import Profile, UserPreferences
from app.db.models.task import Task
from app.db.session import get_db
from app.main import app
from app.schemas.copilot import (
    CopilotMessageRequest,
    CopilotPreferencesUpdate,
    CopilotSpeechRequest,
)
from app.services.copilot_agent import CopilotAgent

@pytest.fixture(autouse=True)
def configure_openai_voice_provider():
    """Ensure tests in this module route specifically to the OpenAI voice provider without network calls."""
    with patch.object(settings, "AI_PROVIDER", "openai"), patch.object(settings, "GEMINI_API_KEY", ""):
        yield


@pytest.fixture
async def test_session():
    """Isolated in-memory SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_user(test_session: AsyncSession):
    """Fixture providing an authenticated profile with initial preferences."""
    user_id = uuid.uuid4()
    profile = Profile(
        id=user_id,
        email="voice_student@mentor.ai",
        full_name="Voice Test Student",
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
            "review_before_send": True,
        },
    )
    test_session.add(profile)
    test_session.add(prefs)

    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Voice Study Task",
        description="Verify unified agent tool invocation",
        status="pending",
        priority="P1",
        duration_minutes=30,
    )
    test_session.add(task)

    await test_session.commit()
    return AuthenticatedUser(
        id=user_id,
        email="voice_student@mentor.ai",
        role="authenticated",
    )


# -----------------------------------------------------------------------------
# 1. Speech-to-Text (Whisper STT) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_audio_success(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Uploading a valid audio recording returns 200 with transcript."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    dummy_audio = b"\x1aE\xdf\xa3" + b"A" * 200  # Valid dummy webm header + payload
    mock_response = MagicMock()
    mock_response.text = "Ajke amar ki task ache?"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    try:
        with patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                files = {"file": ("speech.webm", dummy_audio, "audio/webm")}
                res = await ac.post("/api/v1/copilot/transcribe", files=files)

                assert res.status_code == 200
                data = res.json()
                assert data["transcript"] == "Ajke amar ki task ache?"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_empty_recording(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Uploading empty or corrupt audio (< 64 bytes) returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            files = {"file": ("empty.webm", b"too short", "audio/webm")}
            res = await ac.post("/api/v1/copilot/transcribe", files=files)
            assert res.status_code == 400
            assert "empty or corrupt" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_oversized_recording(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Uploading audio exceeding 25MB returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    oversized = b"A" * (25 * 1024 * 1024 + 10)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            files = {"file": ("huge.webm", oversized, "audio/webm")}
            res = await ac.post("/api/v1/copilot/transcribe", files=files)
            assert res.status_code == 400
            assert "25mb" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_unsupported_format(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Uploading unsupported file formats (e.g. .pdf or .exe) returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            files = {"file": ("malware.exe", b"MZ" + b"X" * 100, "application/octet-stream")}
            res = await ac.post("/api/v1/copilot/transcribe", files=files)
            assert res.status_code == 400
            assert "unsupported audio format" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_unsupported_mime(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Uploading with invalid MIME type returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            files = {"file": ("document.webm", b"A" * 100, "application/pdf")}
            res = await ac.post("/api/v1/copilot/transcribe", files=files)
            assert res.status_code == 400
            assert "unsupported audio mime type" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_provider_rate_limit(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Gemini 429 rate limit maps to HTTP 429 Too Many Requests."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    dummy_audio = b"\x1aE\xdf\xa3" + b"A" * 200
    from google.genai.errors import APIError
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=APIError(code=429, response_json={"error": {"message": "Rate limit reached"}})
    )

    try:
        with patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                files = {"file": ("speech.webm", dummy_audio, "audio/webm")}
                res = await ac.post("/api/v1/copilot/transcribe", files=files)
                assert res.status_code == 429
                assert "rate limit exceeded" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_provider_timeout(test_session: AsyncSession, test_user: AuthenticatedUser):
    """TimeoutError maps to HTTP 504 Gateway Timeout."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    dummy_audio = b"\x1aE\xdf\xa3" + b"A" * 200
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=TimeoutError("Request timed out"))

    try:
        with patch.object(CopilotAgent, "get_gemini_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                files = {"file": ("speech.webm", dummy_audio, "audio/webm")}
                res = await ac.post("/api/v1/copilot/transcribe", files=files)
                assert res.status_code == 504
                assert "timed out" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transcribe_audio_unauthenticated():
    """Unauthenticated calls to /transcribe are rejected with 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        files = {"file": ("speech.webm", b"A" * 100, "audio/webm")}
        res = await ac.post("/api/v1/copilot/transcribe", files=files)
        assert res.status_code == 401


# -----------------------------------------------------------------------------
# 2. Text-to-Speech (OpenAI TTS) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_synthesize_speech_endpoint_success(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Valid text synthesis returns 200 OK with audio/mpeg and X-AI-Generated: true."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    mock_audio_bytes = b"ID3\x03\x00\x00\x00" + b"\xff\xfb\x90\x44" * 50
    mock_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.content = mock_audio_bytes
    mock_client.audio.speech.create.return_value = mock_res

    try:
        with patch.object(CopilotAgent, "get_openai_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                payload = {"text": "You have one academic assignment due at 2 PM.", "voice": "nova"}
                res = await ac.post("/api/v1/copilot/speech", json=payload)

                assert res.status_code == 200
                assert res.headers["content-type"] == "audio/mpeg"
                assert res.headers["x-ai-generated"] == "true"
                assert res.content == mock_audio_bytes
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_synthesize_speech_empty_text(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Empty or whitespace-only text returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/copilot/speech", json={"text": "   "})
            assert res.status_code == 400
            assert "empty or whitespace" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_synthesize_speech_oversized_text(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Text exceeding 4096 characters returns 400 Bad Request."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    huge_text = "Learn " * 1000
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/copilot/speech", json={"text": huge_text})
            assert res.status_code in (400, 422)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_synthesize_speech_rate_limit(test_session: AsyncSession, test_user: AuthenticatedUser):
    """OpenAI RateLimitError during TTS maps to HTTP 429."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_client.audio.speech.create.side_effect = RateLimitError(
        message="TTS rate limit exceeded", response=mock_resp, body=None
    )

    try:
        with patch.object(CopilotAgent, "get_openai_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                res = await ac.post("/api/v1/copilot/speech", json={"text": "Review today's schedule."})
                assert res.status_code == 429
                assert "rate limit exceeded" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_synthesize_speech_voice_fallback():
    """Unsupported voice preset falls back cleanly to 'nova'."""
    mock_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.content = b"AUDIO_DATA"
    mock_client.audio.speech.create.return_value = mock_res

    with patch.object(CopilotAgent, "get_openai_client", return_value=mock_client):
        audio = await CopilotAgent.synthesize_speech("Hello!", voice_preset="unknown_alien_voice")
        assert audio == b"AUDIO_DATA"

        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["voice"] == "nova"


# -----------------------------------------------------------------------------
# 3. Preferences Persistence & Voice Options
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_available_voices(test_session: AsyncSession, test_user: AuthenticatedUser):
    """GET /voices returns masculine and feminine acoustic options."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/v1/copilot/voices")
            assert res.status_code == 200
            voices = res.json()
            assert len(voices) >= 4
            voice_ids = [v["id"] for v in voices]
            assert "nova" in voice_ids
            assert "shimmer" in voice_ids
            assert "echo" in voice_ids
            assert "onyx" in voice_ids
            assert any(v["perceived_sound"] == "masculine" for v in voices)
            assert any(v["perceived_sound"] == "feminine" for v in voices)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_preferences_persistence_and_update(test_session: AsyncSession, test_user: AuthenticatedUser):
    """PUT /preferences persists voice preferences and review_before_send."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Check initial preferences
            get_res = await ac.get("/api/v1/copilot/preferences")
            assert get_res.status_code == 200
            assert get_res.json()["voice_preset"] == "nova"
            assert get_res.json()["review_before_send"] is True

            # 2. Update preferences
            update_payload = {
                "voice_preset": "echo",
                "voice_gender": "masculine",
                "review_before_send": False,
            }
            put_res = await ac.put("/api/v1/copilot/preferences", json=update_payload)
            assert put_res.status_code == 200
            data = put_res.json()
            assert data["voice_preset"] == "echo"
            assert data["voice_gender"] == "masculine"
            assert data["review_before_send"] is False

            # 3. Verify in database directly
            stmt = select(UserPreferences).where(UserPreferences.user_id == test_user.id)
            db_prefs = await test_session.scalar(stmt)
            assert db_prefs.copilot_settings["voice_preset"] == "echo"
            assert db_prefs.copilot_settings["review_before_send"] is False
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 4. Unified Agent Orchestration (Voice Uses Same Tools As Text)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_voice_mode_invokes_same_agent_and_tools(test_session: AsyncSession, test_user: AuthenticatedUser):
    """Voice input mode (input_mode='voice') invokes the exact same tools and user isolation as text mode."""
    req = CopilotMessageRequest(
        message="amar ajker task ki ki?",
        client_timezone="Asia/Dhaka",
        input_mode="voice",
        voice_preset="echo",
    )

    # Mock tool call from OpenAI model to get_today_tasks
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_voice_123"
    mock_tool_call.function.name = "get_today_tasks"
    mock_tool_call.function.arguments = json.dumps({})

    round1_choice = MagicMock()
    round1_choice.message.role = "assistant"
    round1_choice.message.content = None
    round1_choice.message.tool_calls = [mock_tool_call]

    round2_choice = MagicMock()
    round2_choice.message.role = "assistant"
    round2_choice.message.content = "Today you have: Voice Study Task."
    round2_choice.message.tool_calls = None

    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[round1_choice]),
        MagicMock(choices=[round2_choice]),
    ]

    mock_speech_res = MagicMock()
    mock_speech_res.content = b"SYNTHESIZED_VOICE_STREAM"
    mock_client.audio.speech.create.return_value = mock_speech_res

    with patch.object(CopilotAgent, "get_openai_client", return_value=mock_client):
        res = await CopilotAgent.process_message(
            db=test_session,
            user_id=test_user.id,
            req=req,
            preferred_voice="echo",
        )

        assert res.input_mode == "voice"
        assert "get_today_tasks" in res.tools_invoked
        assert res.speech_audio_base64 == base64.b64encode(b"SYNTHESIZED_VOICE_STREAM").decode("utf-8")
        assert res.speech_audio_format == "audio/mpeg"
        assert "Voice Study Task" in res.reply
        assert res.spoken_reply is not None


# -----------------------------------------------------------------------------
# 5. Spoken Text Sanitization (No Tool Calls, JSON, Tokens, or System Prompts)
# -----------------------------------------------------------------------------
def test_clean_text_for_speech_strips_internal_artifacts():
    """_clean_text_for_speech thoroughly removes code blocks, JSON payloads, internal tool names, UUIDs, and tokens."""
    dirty_text = """
    > [!NOTE]
    > SYSTEM: Context initialized.

    Here is what I found:
    ```python
    def solve():
        return 42
    ```

    Tool output: get_today_tasks(user_id="4bd1b566-00a3-4568-9e42-e27b29c23794")
    JSON Result: {"tool": "get_today_tasks", "status": "success"}

    Your approval ID is appr_0123456789abcdef.
    For more details, visit [Course Link](https://example.com/course).

    | Task | Status |
    | --- | --- |
    | Math Homework | Completed |

    - First task
    - Second task
    """

    cleaned = CopilotAgent._clean_text_for_speech(dirty_text)

    # Must NOT contain code or tool signatures
    assert "def solve():" not in cleaned
    assert "get_today_tasks" not in cleaned
    assert '{"tool":' not in cleaned
    assert "appr_" not in cleaned
    assert "4bd1b566" not in cleaned
    assert "https://" not in cleaned
    assert "[!NOTE]" not in cleaned
    assert "| --- |" not in cleaned

    # Must contain natural spoken phrasing
    assert "Here is a code example." in cleaned
    assert "Here is what I found" in cleaned
    assert "Course Link" in cleaned
