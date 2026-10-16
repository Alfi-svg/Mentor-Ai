"""Gmail endpoints for OAuth connection, message queries, AI summarization, task extraction, and staged sends."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppException
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
    GmailModifyRequest,
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
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = Query(default=None, description="Authorization code from OAuth provider"),
    state: str | None = Query(default=None, description="Signed CSRF state parameter"),
    error: str | None = Query(default=None, description="Error code from OAuth provider"),
    error_description: str | None = Query(default=None, description="Error description from OAuth provider"),
) -> Any:
    """Exchange authorization code and activate external Gmail connection."""
    accept_header = request.headers.get("accept", "")
    is_browser_nav = "text/html" in accept_header and "application/json" not in accept_header

    # Handle provider denial or error (e.g. user clicked Cancel on Google consent screen)
    if error:
        err_msg = error_description or error or "OAuth authorization was denied or cancelled."
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/gmail?error={quote_plus(error)}&error_description={quote_plus(err_msg)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_ACCESS_DENIED",
            detail=f"Gmail authorization was denied: {err_msg}",
        )

    if not code or not state:
        err_msg = "Missing required OAuth authorization code or state token."
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/gmail?error=missing_parameters&error_description={quote_plus(err_msg)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_MISSING_PARAMETERS",
            detail=err_msg,
        )

    try:
        conn, email = await GmailService.handle_callback(code=code, state=state, db=db)
    except AppException as exc:
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/gmail?error={quote_plus(exc.error_code)}&error_description={quote_plus(exc.detail)}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise
    except Exception as exc:
        if is_browser_nav:
            dest = f"{settings.FRONTEND_URL}/settings/gmail?error=callback_failed&error_description={quote_plus(str(exc))}"
            return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
        raise AppException(
            status_code=400,
            error_code="OAUTH_CALLBACK_FAILED",
            detail=f"Failed to complete Gmail authentication: {exc}",
        )

    if is_browser_nav:
        email_param = f"&email={quote_plus(email)}" if email else ""
        dest = f"{settings.FRONTEND_URL}/settings/gmail?connected=true{email_param}"
        return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)

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
    description="Retrieves a paginated list of recent messages, optionally filtered by search query or folder.",
)
async def list_messages(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(default=None, description="Optional Gmail search query (e.g. is:unread, subject:hw)"),
    folder: str | None = Query(default=None, description="Optional folder/label filter (INBOX, STARRED, SENT, DRAFT)"),
    page_token: str | None = Query(default=None, description="Pagination token for next page of messages"),
    limit: int = Query(default=15, ge=1, le=50, description="Max messages to return"),
) -> list[GmailMessageSummary]:
    """Fetch paginated message summaries."""
    return await GmailService.list_messages(
        user_id=current_user.id,
        db=db,
        query=query,
        folder=folder,
        page_token=page_token,
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


@router.post(
    "/messages/{message_id}/modify",
    summary="Modify Message Labels",
    description="Adds or removes label IDs from a Gmail message (e.g. mark read/unread, star/unstar).",
)
async def modify_message(
    message_id: str,
    payload: GmailModifyRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Modify message labels in Gmail."""
    labels = await GmailService.modify_message(
        user_id=current_user.id,
        message_id=message_id,
        add_labels=payload.add_label_ids,
        remove_labels=payload.remove_label_ids,
        db=db,
    )
    return {
        "id": message_id,
        "labels": labels,
        "is_unread": "UNREAD" in labels,
        "is_starred": "STARRED" in labels,
    }


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
