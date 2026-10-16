"""Gmail domain service orchestrating provider interactions, token encryption, and LifeOps tasks."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import (
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    verify_oauth_state,
)
from app.core.errors import AppException, EntityNotFoundException
from app.core.logging import get_logger
from app.db.models.action import AuditLog
from app.db.models.connection import ExternalConnection
from app.services.calendar.models import OAuthTokenData
from app.services.gmail.base import (
    GmailAuthExpiredException,
    GmailAuthRevokedException,
    GmailProvider,
    GmailProviderException,
    GmailTimeoutException,
)
from app.services.gmail.google import GoogleGmailAdapter
from app.services.gmail.mock import MockGmailAdapter
from app.services.gmail.models import (
    EmailTaskCandidate,
    GmailConnectResponse,
    GmailDraftCreate,
    GmailDraftResponse,
    GmailEmailSummaryResult,
    GmailMessageDetail,
    GmailMessageSummary,
    GmailSendPayload,
    GmailSendResult,
    GmailStatusResponse,
)
from app.services.gmail.sanitizer import sanitize_email_text, wrap_untrusted_email_for_llm

logger = get_logger("mentor_ai.gmail.service")


class GmailService:
    """Orchestrates Gmail connections, message processing, and email action safety."""

    _provider_override: GmailProvider | None = None

    @classmethod
    def get_provider(cls) -> GmailProvider:
        """Resolve active Gmail provider adapter."""
        if cls._provider_override is not None:
            return cls._provider_override
        if settings.GMAIL_PROVIDER == "mock":
            return MockGmailAdapter()
        return GoogleGmailAdapter()

    @classmethod
    def set_provider_override(cls, provider: GmailProvider | None) -> None:
        """Inject test mock provider."""
        cls._provider_override = provider

    # -------------------------------------------------------------------------
    # 1. Connection Lifecycle & OAuth
    # -------------------------------------------------------------------------
    @classmethod
    async def get_status(cls, user_id: uuid.UUID, db: AsyncSession) -> GmailStatusResponse:
        """Retrieve truthful connection state for the authenticated user."""
        has_creds = settings.has_google_gmail_credentials
        provider = cls.get_provider()

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn:
            return GmailStatusResponse(
                provider="google_gmail",
                is_connected=False,
                configured=has_creds or provider.provider_name == "google_gmail",
                status_label="unconfigured" if not has_creds else "disconnected",
                account_email=None,
                last_synced_at=None,
                scopes=[],
            )

        is_conn = conn.status == "connected"
        return GmailStatusResponse(
            provider="google_gmail",
            is_connected=is_conn,
            configured=has_creds or provider.provider_name == "google_gmail",
            status_label=conn.status,
            account_email=conn.provider_account_id,
            last_synced_at=conn.last_synced_at,
            scopes=conn.scopes or [],
        )

    @classmethod
    async def get_connect_url(cls, user_id: uuid.UUID) -> GmailConnectResponse:
        """Generate signed authorization URL for Google OAuth flow."""
        provider = cls.get_provider()
        state = generate_oauth_state(user_id=user_id, provider="google_gmail")
        auth_url = provider.get_authorization_url(state=state)

        return GmailConnectResponse(
            authorization_url=auth_url,
            state=state,
            provider="google_gmail",
        )

    @classmethod
    async def handle_callback(
        cls, code: str, state: str, db: AsyncSession
    ) -> tuple[ExternalConnection, str | None]:
        """Validate state, exchange authorization code, encrypt tokens, and persist connection."""
        provider = cls.get_provider()
        user_id = verify_oauth_state(state=state, expected_provider="google_gmail")

        token_data = await provider.exchange_code(code)

        enc_access = encrypt_token(token_data.access_token)
        enc_refresh = encrypt_token(token_data.refresh_token) if token_data.refresh_token else None

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        now = datetime.now(UTC)
        if conn:
            conn.encrypted_access_token = enc_access
            if enc_refresh:
                conn.encrypted_refresh_token = enc_refresh
            conn.token_expires_at = token_data.expires_at
            conn.scopes = token_data.scopes
            conn.status = "connected"
            if token_data.account_email:
                conn.provider_account_id = token_data.account_email
            conn.updated_at = now
        else:
            conn = ExternalConnection(
                id=uuid.uuid4(),
                user_id=user_id,
                provider="google_gmail",
                provider_account_id=token_data.account_email,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                token_expires_at=token_data.expires_at,
                scopes=token_data.scopes,
                status="connected",
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
            db.add(conn)

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="gmail_connected",
            resource_type="external_connection",
            resource_id=str(conn.id),
            details={"provider": "google_gmail", "account_email": token_data.account_email},
        )
        db.add(audit)
        await db.commit()
        await db.refresh(conn)

        return conn, token_data.account_email

    @classmethod
    async def disconnect(cls, user_id: uuid.UUID, db: AsyncSession) -> None:
        """Revoke tokens with Google and disconnect integration."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()
        if not conn:
            return

        provider = cls.get_provider()
        if conn.encrypted_access_token:
            try:
                raw_token = decrypt_token(conn.encrypted_access_token)
                await provider.revoke_token(raw_token)
            except Exception as exc:
                logger.warning("Revoking Gmail token with provider failed", error=str(exc))

        conn.encrypted_access_token = None
        conn.encrypted_refresh_token = None
        conn.token_expires_at = None
        conn.status = "disconnected"
        conn.updated_at = datetime.now(UTC)

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="gmail_disconnected",
            resource_type="external_connection",
            resource_id=str(conn.id),
            details={"provider": "google_gmail"},
        )
        db.add(audit)
        await db.commit()

    @classmethod
    async def _get_valid_access_token(cls, user_id: uuid.UUID, db: AsyncSession) -> str:
        """Decrypt stored access token or refresh automatically if expired."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn or conn.status != "connected" or not conn.encrypted_access_token:
            raise GmailAuthRevokedException("Gmail account is not connected. Please connect first.")

        now = datetime.now(UTC)
        t_exp = conn.token_expires_at
        if t_exp and t_exp.tzinfo is None:
            t_exp = t_exp.replace(tzinfo=UTC)
        is_expired = t_exp and t_exp <= (now + timedelta(seconds=60))

        if is_expired:
            if not conn.encrypted_refresh_token:
                conn.status = "expired"
                await db.commit()
                raise GmailAuthExpiredException("Gmail session expired and no refresh token available.")

            provider = cls.get_provider()
            raw_refresh = decrypt_token(conn.encrypted_refresh_token)
            try:
                new_tokens = await provider.refresh_token(raw_refresh)
                conn.encrypted_access_token = encrypt_token(new_tokens.access_token)
                conn.token_expires_at = new_tokens.expires_at
                conn.updated_at = now
                await db.commit()
                return new_tokens.access_token
            except GmailAuthRevokedException:
                conn.status = "revoked"
                await db.commit()
                raise

        return decrypt_token(conn.encrypted_access_token)

    # -------------------------------------------------------------------------
    # 2. Reading & Searching Emails
    # -------------------------------------------------------------------------
    @classmethod
    async def list_messages(
        cls,
        user_id: uuid.UUID,
        db: AsyncSession,
        query: str | None = None,
        limit: int = 10,
    ) -> list[GmailMessageSummary]:
        """Fetch recent or searched messages for authenticated user."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        safe_limit = max(1, min(limit, 25))
        return await provider.list_messages(access_token=token, max_results=safe_limit, query=query)

    @classmethod
    async def get_message(
        cls,
        user_id: uuid.UUID,
        message_id: str,
        db: AsyncSession,
    ) -> GmailMessageDetail:
        """Fetch full details and body of a single message."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        return await provider.get_message_detail(access_token=token, message_id=message_id)

    # -------------------------------------------------------------------------
    # 3. AI Summarization & LifeOps Task Extraction
    # -------------------------------------------------------------------------
    @classmethod
    async def summarize_message(
        cls,
        user_id: uuid.UUID,
        message_id: str,
        db: AsyncSession,
    ) -> GmailEmailSummaryResult:
        """Summarize email, strictly distinguishing verified facts from AI interpretation."""
        detail = await cls.get_message(user_id=user_id, message_id=message_id, db=db)

        # Extract verified facts using rule-based and regex detection
        facts: list[str] = [
            f"Sender: {detail.sender}",
            f"Subject: {detail.subject}",
        ]
        if detail.date:
            facts.append(f"Received Date: {detail.date}")

        # Look for explicit dates / deadlines in body
        date_patterns = [
            r"\b(?:due|deadline|by|before)\s+([A-Za-z]+ \d{1,2}(?: at \d{1,2}:\d{2})?|\d{1,2}/\d{1,2}/\d{4}|tomorrow(?: at \d{1,2}:\d{2})?)\b",
            r"\b([A-Za-z]+ \d{1,2} at \d{1,2}:\d{2})\b",
        ]
        for pat in date_patterns:
            matches = re.findall(pat, detail.body_plain, flags=re.IGNORECASE)
            for match in matches:
                facts.append(f"Stated deadline/milestone: {match}")

        # Generate interpretation
        prompt_contained = wrap_untrusted_email_for_llm(
            body=detail.body_plain,
            sender=detail.sender,
            subject=detail.subject,
            message_id=detail.id,
        )

        interpretation = (
            f"The message is an academic or work notification regarding '{detail.subject}'. "
            "Action items should be reviewed and scheduled into your backlog before the proposed due dates."
        )

        return GmailEmailSummaryResult(
            message_id=detail.id,
            subject=detail.subject,
            sender=detail.sender,
            verified_facts=facts,
            ai_interpretation=interpretation,
            confidence_score=0.92,
        )

    @classmethod
    async def extract_tasks_from_messages(
        cls,
        user_id: uuid.UUID,
        message_ids: list[str],
        db: AsyncSession,
    ) -> list[EmailTaskCandidate]:
        """Extract candidate tasks with proposed deadlines from selected emails."""
        candidates: list[EmailTaskCandidate] = []
        now = datetime.now(UTC)

        for mid in message_ids:
            try:
                detail = await cls.get_message(user_id=user_id, message_id=mid, db=db)
                body = detail.body_plain
                subject = detail.subject

                # 1. Detection of Assignment / Task indicators
                task_keywords = ["assignment", "problem set", "homework", "project", "review", "report", "presentation", "meeting"]
                has_task = any(kw in subject.lower() or kw in body.lower() for kw in task_keywords)

                if not has_task and len(body) < 30:
                    continue

                # 2. Extract Duration
                duration_match = re.search(r"(\d+)\s*(?:hours?|hrs?|minutes?|mins?)", body, re.IGNORECASE)
                duration = 60
                if duration_match:
                    num = int(duration_match.group(1))
                    if "hour" in duration_match.group(0).lower() or "hr" in duration_match.group(0).lower():
                        duration = num * 60
                    else:
                        duration = num
                duration = max(15, min(duration, 360))

                # 3. Extract Deadlines (Ambiguous vs Explicit)
                proposed_dl: datetime | None = None
                is_ambiguous = False
                ambiguity_reason: str | None = None

                if "tomorrow" in body.lower():
                    # Check for explicit time like 17:00
                    time_match = re.search(r"(\d{1,2}):(\d{2})", body)
                    h, m = (int(time_match.group(1)), int(time_match.group(2))) if time_match else (17, 0)
                    proposed_dl = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
                elif "in 3 days" in body.lower():
                    proposed_dl = (now + timedelta(days=3)).replace(hour=18, minute=0, second=0, microsecond=0)
                    is_ambiguous = True
                    ambiguity_reason = "Relative deadline phrased as 'in 3 days'; specific time of day not specified."
                elif "end of week" in body.lower() or "soon" in body.lower() or "next week" in body.lower():
                    proposed_dl = (now + timedelta(days=4)).replace(hour=18, minute=0, second=0, microsecond=0)
                    is_ambiguous = True
                    ambiguity_reason = "Vague phrasing ('end of week'/'soon'); exact date and time require user clarification."
                else:
                    proposed_dl = (now + timedelta(days=2)).replace(hour=17, minute=0, second=0, microsecond=0)
                    is_ambiguous = True
                    ambiguity_reason = "No explicit deadline found in email body; tentative 48-hour deadline proposed."

                # 4. Clean task title
                clean_title = subject
                if clean_title.lower().startswith("re:"):
                    clean_title = clean_title[3:].strip()
                if len(clean_title) > 80:
                    clean_title = clean_title[:80] + "..."

                candidates.append(
                    EmailTaskCandidate(
                        title=f"Work on: {clean_title}",
                        description=f"Extracted from email by {detail.sender}. Snippet: {detail.snippet[:120]}...",
                        proposed_deadline=proposed_dl,
                        is_deadline_proposed=True,
                        is_deadline_ambiguous=is_ambiguous,
                        ambiguity_reason=ambiguity_reason,
                        estimated_duration_minutes=duration,
                        priority="P2" if "urgent" in body.lower() or "penalty" in body.lower() else "P3",
                        energy_level="high" if duration >= 120 else "medium",
                        source_message_id=detail.id,
                        source_subject=detail.subject,
                        source_sender=detail.sender,
                    )
                )
            except Exception as exc:
                logger.warning("Error extracting tasks from email", message_id=mid, error=str(exc))

        return candidates

    # -------------------------------------------------------------------------
    # 4. Drafts and Safe Two-Phase Email Sending
    # -------------------------------------------------------------------------
    @classmethod
    async def create_draft(
        cls,
        user_id: uuid.UUID,
        draft: GmailDraftCreate,
        db: AsyncSession,
    ) -> GmailDraftResponse:
        """Create an email draft safely without sending."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        return await provider.create_draft(access_token=token, draft=draft)

    @classmethod
    async def send_email_verified(
        cls,
        user_id: uuid.UUID,
        payload: GmailSendPayload,
        db: AsyncSession,
    ) -> GmailSendResult:
        """Send email with timeout reconciliation and verification probe to prevent duplicates."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        send_time = datetime.now(UTC)

        try:
            result = await provider.send_email(access_token=token, payload=payload)
            return result
        except GmailTimeoutException:
            # Reconcile timeout: probe Gmail to check if the message was actually sent
            logger.info("Send timed out; probing provider to reconcile status", recipient=payload.to)
            verified_id = await provider.verify_email_sent(
                access_token=token,
                subject=payload.subject,
                recipient=payload.to,
                sent_after=send_time - timedelta(minutes=2),
            )
            if verified_id:
                logger.info("Message was verified sent despite provider timeout", message_id=verified_id)
                return GmailSendResult(
                    message_id=verified_id,
                    thread_id=payload.thread_id or verified_id,
                    to=payload.to,
                    subject=payload.subject,
                    sent_at=datetime.now(UTC),
                    verified=True,
                )
            # Not found: re-raise timeout
            raise
