"""Pydantic schemas for Mentor AI Educational Copilot, Schedule Intelligence & Voice Assistant."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CopilotChatMessage(BaseModel):
    """A message in the conversational history."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CopilotMessageRequest(BaseModel):
    """User input prompt submitted to the Copilot (via text or voice transcript)."""

    message: str = Field(..., min_length=1, description="User instruction or question")
    input_mode: Literal["text", "voice"] = Field(
        default="text", description="Originating interaction mode: text or voice"
    )
    client_timezone: str = Field(default="Asia/Dhaka", description="User IANA timezone")
    conversation_history: list[CopilotChatMessage] = Field(
        default_factory=list, description="Prior conversation messages for context"
    )
    target_date: str | None = Field(
        default=None, description="Optional target date in YYYY-MM-DD format"
    )
    voice_preset: str | None = Field(
        default=None, description="Optional override TTS voice preset (e.g. nova, echo)"
    )


class CopilotScheduleItem(BaseModel):
    """A single scheduled task block or fixed calendar event."""

    id: str
    title: str
    item_type: Literal["task", "calendar_event"]
    start_time: str = Field(description="Formatted start time, e.g. 09:00 AM or ISO")
    end_time: str = Field(description="Formatted end time, e.g. 10:30 AM or ISO")
    raw_start: datetime
    raw_end: datetime
    status: str = "scheduled"
    is_completed: bool = False
    is_overdue: bool = False
    priority: str | None = None
    task_id: UUID | None = None
    event_id: UUID | None = None
    sync_status: str | None = None


class CopilotScheduleSummary(BaseModel):
    """Structured schedule intelligence returned to the Copilot."""

    target_date: str
    timezone: str
    total_items: int
    scheduled_items: list[CopilotScheduleItem] = Field(default_factory=list)
    unscheduled_tasks: list[dict[str, Any]] = Field(default_factory=list)
    deadlines: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str | None = None
    next_action_time: str | None = None
    summary_text: str


class EducationalResource(BaseModel):
    """Verified educational resource recommended by Mentor Copilot."""

    title: str
    url: str
    platform: str
    topic: str
    difficulty: Literal["Beginner", "Intermediate", "Advanced", "All Levels"] = "Beginner"
    is_free: bool = True
    description: str
    why_recommended: str


class EmailDraftPreview(BaseModel):
    """Contextual email draft requiring user explicit confirmation before sending."""

    thread_id: str | None = None
    recipient_email: str
    recipient_name: str | None = None
    subject: str
    body: str
    context_summary: str | None = None
    requires_confirmation: bool = True
    approval_id: str | None = None
    status: Literal["draft_ready", "ambiguous_recipient", "not_found", "sent", "failed"] = (
        "draft_ready"
    )
    clarification_question: str | None = None
    candidates: list[dict[str, str]] | None = None


class CopilotNavigationTarget(BaseModel):
    """Typed application navigation destination."""

    route: str = Field(description="Destination frontend path, e.g. /calendar, /tasks, /gmail")
    params: dict[str, str] = Field(default_factory=dict, description="URL query parameters")
    label: str = Field(description="Human-readable label for the navigation pill")


class StudentAccountabilitySummary(BaseModel):
    """Constructive student progress and missed session accountability metrics."""

    missed_sessions_count: int = 0
    completed_today_count: int = 0
    total_tasks_count: int = 0
    streak_days: int = 0
    supportive_message: str
    suggested_recovery_task: dict[str, Any] | None = None


class CopilotResponse(BaseModel):
    """Complete structured response envelope returned by CopilotService."""

    reply: str = Field(description="Assistant natural conversational response")
    spoken_reply: str | None = Field(
        default=None, description="Concise text optimized for text-to-speech reading"
    )
    speech_audio_base64: str | None = Field(
        default=None, description="Base64-encoded audio when voice mode is active"
    )
    speech_audio_format: str | None = Field(
        default="audio/mpeg", description="MIME format of synthesized audio"
    )
    input_mode: Literal["text", "voice"] = Field(
        default="text", description="Echo of request interaction mode"
    )
    intent: str = Field(
        default="general_guidance",
        description="Classified intent, e.g. schedule_inquiry, educational_search, etc.",
    )
    tools_invoked: list[str] = Field(
        default_factory=list, description="Names of tools invoked by the agent"
    )
    tool_results: list[dict[str, Any]] = Field(
        default_factory=list, description="Structured tool outputs"
    )
    schedule_summary: CopilotScheduleSummary | None = None
    resources: list[EducationalResource] | None = None
    email_draft: EmailDraftPreview | None = None
    approval_id: str | None = Field(
        default=None, description="Signed approval ID for consequential action confirmation"
    )
    navigation: CopilotNavigationTarget | None = None
    accountability: StudentAccountabilitySummary | None = None
    code_line_count: int | None = None
    verification_status: Literal[
        "verified", "clarification_needed", "unsupported", "error", "unconfigured"
    ] = "verified"


class CopilotActionConfirmRequest(BaseModel):
    """Request to execute an explicitly confirmed consequential Copilot action."""

    action_type: Literal["send_email", "reschedule_task"]
    approval_id: str | None = Field(
        default=None, description="Cryptographically signed approval token"
    )
    email_payload: dict[str, Any] | None = None
    task_payload: dict[str, Any] | None = None


class CopilotActionConfirmResponse(BaseModel):
    """Result of executing a confirmed consequential action."""

    success: bool
    action_type: str
    result_message: str
    details: dict[str, Any] | None = None


class CopilotVoiceOption(BaseModel):
    """Available OpenAI TTS voice preset with description and perceived characteristics."""

    id: str = Field(description="Voice preset identifier (e.g. nova, echo, onyx, shimmer)")
    name: str = Field(description="Human-friendly voice name")
    perceived_sound: Literal["masculine", "feminine"] = Field(
        description="Perceived sound tone (not identity)"
    )
    description: str = Field(description="Acoustic description, e.g. 'Warm and clear'")
    sample_text: str = Field(
        default="Hello! I am Mentor, your educational assistant. How can I help with your studies today?"
    )


class CopilotPreferences(BaseModel):
    """Persisted user Copilot settings."""

    voice_preset: str = "nova"
    voice_gender: Literal["masculine", "feminine"] = "feminine"
    auto_play_speech: bool = True
    stt_engine: str = "openai"
    review_before_send: bool = True


class CopilotPreferencesUpdate(BaseModel):
    """Payload to update user Copilot settings."""

    voice_preset: str | None = None
    voice_gender: Literal["masculine", "feminine"] | None = None
    auto_play_speech: bool | None = None
    stt_engine: str | None = None
    review_before_send: bool | None = None


class CopilotTranscribeResponse(BaseModel):
    """Response returned from speech-to-text audio transcription."""

    transcript: str
    language: str | None = None


class CopilotSpeechRequest(BaseModel):
    """Request to synthesize spoken audio from text."""

    text: str = Field(..., min_length=1, max_length=4096)
    voice: str | None = Field(default=None, description="Voice preset (e.g. echo, nova)")
