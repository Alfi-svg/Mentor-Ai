"""Gmail endpoints for OAuth connection, message queries, AI summarization, task extraction, and staged sends."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.action import ActionResponse
from app.services.action_service import ActionService
from app.services.gmail.models import (
    EmailTaskCandidate,
    GmailConnectResponse,
    GmailDraftCreate,
    GmailDraftResponse,
    GmailEmailSummaryResult,
    GmailMessageDetail,
    GmailMessageSummary,
    GmailSendPayload,
    GmailStatusResponse,
)
from app.services.gmail.service import GmailService

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get(
    "/status",
    response_model=GmailStatusResponse,
    summary="Gmail Connection Status",
    description="Returns whether the user has a connected Gmail integration truthfully.",
)
async def get_gmail_status(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GmailStatusResponse:
    """Check connection status for current user."""
    return await GmailService.get_status(user_id=current_user.id, db=db)


@router.get(
    "/connect",
    response_model=GmailConnectResponse,
    summary="Initiate Gmail Connection",
    description="Generates an OAuth authorization URL with signed CSRF state token.",
)
async def connect_gmail(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> GmailConnectResponse:
    """Generate signed OAuth authorization URL for Gmail."""
    return await GmailService.get_connect_url(user_id=current_user.id)


@router.get(
    "/callback",
    summary="OAuth Callback",
    description="Handles Google OAuth redirect for Gmail, validates CSRF state, and stores encrypted tokens.",
)
async def oauth_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="Signed CSRF state parameter"),
) -> dict[str, Any]:
    """Exchange authorization code and activate external Gmail connection."""
    conn, email = await GmailService.handle_callback(code=code, state=state, db=db)
    return {
        "status": "connected",
        "provider": conn.provider,
        "account_email": email,
        "connected_at": conn.created_at.isoformat(),
    }


@router.post(
    "/disconnect",
    summary="Disconnect Gmail",
    description="Revokes access with provider and removes stored tokens.",
)
async def disconnect_gmail(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Revoke tokens and disconnect Gmail integration."""
    await GmailService.disconnect(user_id=current_user.id, db=db)
    return {
        "status": "disconnected",
        "provider": "google_gmail",
        "message": "Gmail connection has been successfully disconnected.",
    }


@router.get(
    "/messages",
    response_model=list[GmailMessageSummary],
    summary="List Gmail Messages",
    description="Retrieves a paginated list of recent messages, optionally filtered by search query.",
)
async def list_messages(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(default=None, description="Optional Gmail search query (e.g. is:unread, subject:hw)"),
    limit: int = Query(default=10, ge=1, le=25, description="Max messages to return"),
) -> list[GmailMessageSummary]:
    """Fetch paginated message summaries."""
    return await GmailService.list_messages(
        user_id=current_user.id,
        db=db,
        query=query,
        limit=limit,
    )


@router.get(
    "/messages/{message_id}",
    response_model=GmailMessageDetail,
    summary="Get Gmail Message Detail",
    description="Retrieves message metadata and sanitized plain text content.",
)
async def get_message_detail(
    message_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GmailMessageDetail:
    """Fetch full detail of a single email message."""
    return await GmailService.get_message(
        user_id=current_user.id,
        message_id=message_id,
        db=db,
    )


@router.get(
    "/messages/{message_id}/summary",
    response_model=GmailEmailSummaryResult,
    summary="Summarize Email",
    description="Generates an AI summary of an email, clearly distinguishing verified facts from AI interpretation.",
)
async def summarize_message(
    message_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GmailEmailSummaryResult:
    """Summarize email distinguishing verified facts from interpretation."""
    return await GmailService.summarize_message(
        user_id=current_user.id,
        message_id=message_id,
        db=db,
    )


@router.post(
    "/extract-tasks",
    response_model=list[EmailTaskCandidate],
    summary="Extract Tasks From Emails",
    description="Analyzes selected emails, detects assignments/commitments, and extracts proposed tasks with deadlines.",
)
async def extract_tasks(
    message_ids: list[str],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[EmailTaskCandidate]:
    """Extract candidate tasks with proposed deadlines from emails."""
    return await GmailService.extract_tasks_from_messages(
        user_id=current_user.id,
        message_ids=message_ids,
        db=db,
    )


@router.post(
    "/drafts",
    response_model=GmailDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Email Draft",
    description="Creates a draft message in Gmail safely without sending.",
)
async def create_draft(
    draft: GmailDraftCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GmailDraftResponse:
    """Create draft message in Gmail."""
    return await GmailService.create_draft(
        user_id=current_user.id,
        draft=draft,
        db=db,
    )


@router.post(
    "/send-staged",
    response_model=ActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Stage Email Send for Approval",
    description="Stages an email send action in action_history. Never sends without explicit human approval.",
)
async def stage_send_email(
    payload: GmailSendPayload,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: str | None = Query(default=None, description="Client-provided deduplication key"),
) -> ActionResponse:
    """Stage consequential email sending action for human confirmation."""
    action = await ActionService.stage_action(
        db=db,
        user_id=current_user.id,
        action_type="send_email",
        payload=payload.model_dump(mode="json"),
        idempotency_key=idempotency_key,
    )
    return ActionResponse.model_validate(action)
