"""Copilot API endpoints for conversational educational guidance, schedule intelligence, and voice assistant."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.core.security import AuthenticatedUser, get_current_user
from app.db.models.profile import UserPreferences
from app.db.session import get_db
from app.schemas.copilot import (
    CopilotActionConfirmRequest,
    CopilotActionConfirmResponse,
    CopilotMessageRequest,
    CopilotPreferences,
    CopilotPreferencesUpdate,
    CopilotResponse,
    CopilotScheduleSummary,
    CopilotSpeechRequest,
    CopilotTranscribeResponse,
    CopilotVoiceOption,
    StudentAccountabilitySummary,
)
from app.services.copilot.accountability import StudentAccountabilityService
from app.services.copilot.email_copilot import CopilotEmailService
from app.services.copilot.tools import get_today_schedule, resolve_user_timezone
from app.services.copilot_agent import CopilotAgent

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm", ".wav", ".mp3", ".m4a", ".ogg", ".oga", ".flac", ".mp4", ".mpeg", ".mpga"
}
ALLOWED_AUDIO_MIME_PREFIXES = ("audio/", "video/", "application/octet-stream")
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MIN_AUDIO_BYTES = 64

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post(
    "/message",
    response_model=CopilotResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit natural language or voice transcript to Mentor Educational Copilot",
)
async def process_copilot_message(
    payload: CopilotMessageRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotResponse:
    """Orchestrate schedule intelligence, educational resource search, email drafting, or programming tutoring."""
    stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    prefs = await db.scalar(stmt)
    copilot_settings = prefs.copilot_settings if prefs else None
    voice_pref = "nova"
    if copilot_settings and isinstance(copilot_settings, dict):
        voice_pref = copilot_settings.get("voice_preset", "nova")
    if payload.voice_preset:
        voice_pref = payload.voice_preset

    return await CopilotAgent.process_message(
        db=db,
        user_id=current_user.id,
        req=payload,
        preferred_voice=voice_pref,
    )


@router.post(
    "/action/confirm",
    response_model=CopilotActionConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an explicitly confirmed consequential Copilot action (e.g. send approved email)",
)
async def confirm_copilot_action(
    payload: CopilotActionConfirmRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotActionConfirmResponse:
    """Execute action only after user has reviewed and explicitly approved the preview."""
    if payload.action_type == "send_email":
        data = payload.email_payload or {}
        recipient = data.get("recipient_email") or data.get("to")
        subject = data.get("subject", "")
        body = data.get("body", "")
        thread_id = data.get("thread_id")
        approval_id = payload.approval_id or data.get("approval_id")

        if not recipient or not body:
            return CopilotActionConfirmResponse(
                success=False,
                action_type="send_email",
                result_message="Missing recipient email address or message body.",
            )

        success, message, details = await CopilotEmailService.send_confirmed_email(
            db=db,
            user_id=current_user.id,
            recipient_email=recipient,
            subject=subject,
            body=body,
            thread_id=thread_id,
            approval_id=approval_id,
        )
        return CopilotActionConfirmResponse(
            success=success,
            action_type="send_email",
            result_message=message,
            details=details,
        )

    return CopilotActionConfirmResponse(
        success=False,
        action_type=payload.action_type,
        result_message=f"Unsupported action type: {payload.action_type}",
    )


@router.post(
    "/transcribe",
    response_model=CopilotTranscribeResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe audio recording via OpenAI Whisper speech-to-text",
)
async def transcribe_audio_endpoint(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> CopilotTranscribeResponse:
    """Convert spoken voice audio into text transcript."""
    filename = file.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".webm"
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format '{ext}'. Supported formats: webm, wav, mp3, m4a, ogg, flac, mp4.",
        )

    if file.content_type and not any(file.content_type.startswith(prefix) for prefix in ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio MIME type '{file.content_type}'.",
        )

    contents = await file.read()
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording exceeds 25MB maximum upload limit.",
        )
    if not contents or len(contents) < MIN_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording is empty or corrupt.",
        )

    try:
        return await CopilotAgent.transcribe_audio(contents, filename=filename)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(val_err),
        )
    except AuthenticationError as auth_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI authentication failed: {auth_err}",
        )
    except RateLimitError as rl_err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"OpenAI speech-to-text rate limit exceeded: {rl_err}",
        )
    except APITimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Speech-to-text transcription request timed out.",
        )
    except BadRequestError as br_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OpenAI transcription rejected audio: {br_err}",
        )
    except APIConnectionError as conn_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to OpenAI audio service: {conn_err}",
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audio transcription failed: {err}",
        )


@router.post(
    "/speech",
    status_code=status.HTTP_200_OK,
    summary="Synthesize speech audio from text using OpenAI TTS",
)
async def synthesize_speech_endpoint(
    payload: CopilotSpeechRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Response:
    """Generate audio stream for spoken response."""
    if not payload.text or not payload.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speech text must not be empty or whitespace.",
        )
    if len(payload.text) > 4096:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speech text exceeds 4096 character maximum limit.",
        )

    try:
        audio_bytes = await CopilotAgent.synthesize_speech(
            text=payload.text, voice_preset=payload.voice or "nova"
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Type": "audio/mpeg",
                "Accept-Ranges": "bytes",
                "X-AI-Generated": "true",
                "Cache-Control": "private, max-age=3600",
            },
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(val_err),
        )
    except AuthenticationError as auth_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI authentication failed: {auth_err}",
        )
    except RateLimitError as rl_err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"OpenAI speech synthesis rate limit exceeded: {rl_err}",
        )
    except APITimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Speech synthesis request timed out.",
        )
    except BadRequestError as br_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OpenAI speech synthesis rejected: {br_err}",
        )
    except APIConnectionError as conn_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to OpenAI audio service: {conn_err}",
        )
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech synthesis failed: {err}",
        )


@router.get(
    "/voices",
    response_model=list[CopilotVoiceOption],
    status_code=status.HTTP_200_OK,
    summary="List available voice options with perceived sound and acoustic descriptions",
)
async def get_available_voices(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[CopilotVoiceOption]:
    """Retrieve supported voice options for Copilot preferences."""
    return CopilotAgent.get_supported_voices()


@router.get(
    "/preferences",
    response_model=CopilotPreferences,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current user Copilot voice and interaction settings",
)
async def get_copilot_preferences(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotPreferences:
    """Retrieve persisted Copilot voice preferences."""
    stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    prefs = await db.scalar(stmt)
    if not prefs or not prefs.copilot_settings:
        return CopilotPreferences()
    return CopilotPreferences(**prefs.copilot_settings)


@router.put(
    "/preferences",
    response_model=CopilotPreferences,
    status_code=status.HTTP_200_OK,
    summary="Update user Copilot voice and interaction settings",
)
async def update_copilot_preferences(
    payload: CopilotPreferencesUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotPreferences:
    """Update and persist Copilot voice preferences."""
    stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    prefs = await db.scalar(stmt)
    if not prefs:
        prefs = UserPreferences(
            id=uuid.uuid4(),
            user_id=current_user.id,
            copilot_settings={
                "voice_preset": "nova",
                "voice_gender": "feminine",
                "auto_play_speech": True,
                "stt_engine": "openai",
                "review_before_send": True,
            },
        )
        db.add(prefs)

    current_settings = dict(prefs.copilot_settings or {})
    if payload.voice_preset is not None:
        current_settings["voice_preset"] = payload.voice_preset
    if payload.voice_gender is not None:
        current_settings["voice_gender"] = payload.voice_gender
    if payload.auto_play_speech is not None:
        current_settings["auto_play_speech"] = payload.auto_play_speech
    if payload.stt_engine is not None:
        current_settings["stt_engine"] = payload.stt_engine
    if payload.review_before_send is not None:
        current_settings["review_before_send"] = payload.review_before_send

    prefs.copilot_settings = current_settings
    await db.commit()
    await db.refresh(prefs)
    return CopilotPreferences(**prefs.copilot_settings)



@router.get(
    "/schedule/today",
    response_model=CopilotScheduleSummary,
    status_code=status.HTTP_200_OK,
    summary="Direct deterministic today schedule intelligence lookup",
)
async def get_copilot_today_schedule(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    timezone: Annotated[str | None, Query(description="Client IANA timezone")] = None,
) -> CopilotScheduleSummary:
    """Retrieve today's schedule, deadlines, and next action in user timezone without LLM dependency."""
    user_tz = await resolve_user_timezone(db, current_user.id, timezone or "Asia/Dhaka")
    return await get_today_schedule(db=db, user_id=current_user.id, user_tz_str=user_tz)


@router.get(
    "/accountability",
    response_model=StudentAccountabilitySummary,
    status_code=status.HTTP_200_OK,
    summary="Retrieve student consistency metrics, streak days, and recovery recommendations",
)
async def get_copilot_accountability(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentAccountabilitySummary:
    """Calculate streak and supportive recovery guidance."""
    return await StudentAccountabilityService.get_accountability_summary(
        db=db, user_id=current_user.id
    )


@router.post(
    "/accountability/evaluate",
    status_code=status.HTTP_200_OK,
    summary="Trigger evaluation of ended scheduled sessions for supportive notifications",
)
async def evaluate_missed_sessions(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Check for ended schedule blocks with incomplete tasks and queue non-punitive notifications."""
    created = await StudentAccountabilityService.evaluate_missed_sessions(
        db=db, user_id=current_user.id
    )
    return {
        "status": "evaluated",
        "new_notifications_count": len(created),
    }
