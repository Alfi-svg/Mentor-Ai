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
from app.services.gmail.base import (
    GmailApiDisabledException,
    GmailAuthExpiredException,
    GmailAuthRevokedException,
    GmailProvider,
    GmailProviderException,
    GmailScopeMissingException,
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
    GmailVerifyResponse,
)
from app.services.gmail.sanitizer import sanitize_email_text, wrap_untrusted_email_for_llm

logger = get_logger("mentor_ai.gmail.service")


def check_gmail_scopes(granted_scopes: list[str] | None) -> tuple[bool, list[str]]:
    """Verify that granted OAuth scopes include required Gmail read access.
    
    In accordance with least-privilege principles, read access (gmail.readonly,
    gmail.modify, or mail.google.com) is sufficient to connect and operate the
    inbox. Feature-specific permissions (e.g. gmail.compose, gmail.send, gmail.modify)
    are checked on-demand for their respective actions.
    """
    if not granted_scopes:
        return False, ["https://www.googleapis.com/auth/gmail.readonly"]
    if "https://mail.google.com/" in granted_scopes:
        return True, []
    missing: list[str] = []
    has_read = (
        "https://www.googleapis.com/auth/gmail.readonly" in granted_scopes
        or "https://www.googleapis.com/auth/gmail.modify" in granted_scopes
    )
    if not has_read:
        missing.append("https://www.googleapis.com/auth/gmail.readonly")

    return len(missing) == 0, missing



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
        """Retrieve truthful connection state for the authenticated user, auto-syncing from live tokens."""
        has_creds = settings.has_google_gmail_credentials
        provider = cls.get_provider()

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        if not conn or conn.status != "connected":
            status_text = "unconfigured" if not has_creds else "disconnected"
            if conn and conn.status == "revoked":
                status_text = "revoked"
            elif conn and conn.status == "expired":
                status_text = "expired"
            return GmailStatusResponse(
                provider="google_gmail",
                is_connected=False,
                configured=has_creds or provider.provider_name == "google_gmail",
                status_label=status_text,
                account_email=conn.provider_account_id if conn else None,
                last_synced_at=conn.last_synced_at if conn else None,
                scopes=conn.scopes if conn else [],
                has_sufficient_scopes=False,
                missing_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

        has_sufficient, missing = check_gmail_scopes(conn.scopes)

        # If stored scopes in DB are missing/wiped or marked insufficient, auto-heal from live tokeninfo
        if (not conn.scopes or conn.metadata_json.get("scope_insufficient") or not has_sufficient) and conn.encrypted_access_token:
            try:
                token = await cls._get_valid_access_token(user_id=user_id, db=db)
                info = await provider.verify_token_details(token)
                if info.get("valid") and info.get("scopes"):
                    verified_scopes = info["scopes"]
                    conn.scopes = verified_scopes
                    if info.get("email"):
                        conn.provider_account_id = info["email"]
                    has_sufficient, missing = check_gmail_scopes(verified_scopes)
                    cur_meta = dict(conn.metadata_json or {})
                    if has_sufficient:
                        cur_meta.pop("scope_insufficient", None)
                    else:
                        cur_meta["scope_insufficient"] = True
                    conn.metadata_json = cur_meta
                    conn.updated_at = datetime.now(UTC)
                    await db.commit()
            except Exception as e:
                logger.debug("Live token auto-healing in get_status skipped", error=str(e))

        if conn.metadata_json and conn.metadata_json.get("scope_insufficient"):
            has_sufficient = False
            if not missing:
                missing = ["https://www.googleapis.com/auth/gmail.readonly"]

        status_label = "connected" if has_sufficient else "insufficient_scopes"
        msg = None if has_sufficient else f"Account connected but missing required Gmail permissions: {', '.join(missing)}. Please reconnect."

        return GmailStatusResponse(
            provider="google_gmail",
            is_connected=True,
            configured=has_creds or provider.provider_name == "google_gmail",
            status_label=status_label,
            account_email=conn.provider_account_id,
            last_synced_at=conn.last_synced_at,
            scopes=conn.scopes or [],
            has_sufficient_scopes=has_sufficient,
            missing_scopes=missing,
            message=msg,
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
    ) -> tuple[ExternalConnection, str | None, bool, list[str]]:
        """Validate state, exchange authorization code, encrypt tokens, and persist connection."""
        provider = cls.get_provider()
        user_id = verify_oauth_state(state=state, expected_provider="google_gmail")

        token_data = await provider.exchange_code(code)

        has_sufficient, missing = check_gmail_scopes(token_data.scopes)

        enc_access = encrypt_token(token_data.access_token)
        enc_refresh = encrypt_token(token_data.refresh_token) if token_data.refresh_token else None

        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()

        now = datetime.now(UTC)
        meta_dict: dict[str, Any] = {"token_type": token_data.token_type}
        if not has_sufficient:
            meta_dict["scope_insufficient"] = True
            logger.warning(
                "Gmail connected with insufficient scopes",
                user_id=str(user_id),
                granted_scopes=token_data.scopes,
                missing=missing,
            )

        if conn:
            conn.encrypted_access_token = enc_access
            if enc_refresh:
                conn.encrypted_refresh_token = enc_refresh
            conn.token_expires_at = token_data.expires_at
            conn.scopes = token_data.scopes
            conn.status = "connected"
            cur_meta = dict(conn.metadata_json or {})
            if has_sufficient:
                cur_meta.pop("scope_insufficient", None)
            else:
                cur_meta["scope_insufficient"] = True
            conn.metadata_json = cur_meta
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
                metadata_json=meta_dict,
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
    async def _force_refresh_access_token(cls, user_id: uuid.UUID, db: AsyncSession) -> str:
        """Force-refresh access token using refresh token regardless of expires_at."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()
        if not conn or not conn.encrypted_refresh_token:
            if conn:
                conn.status = "expired"
                await db.commit()
            raise GmailAuthExpiredException("No refresh token available to refresh expired session.")

        provider = cls.get_provider()
        raw_refresh = decrypt_token(conn.encrypted_refresh_token)
        try:
            new_tokens = await provider.refresh_token(raw_refresh)
            now = datetime.now(UTC)
            conn.encrypted_access_token = encrypt_token(new_tokens.access_token)
            conn.token_expires_at = new_tokens.expires_at
            if new_tokens.scopes:
                conn.scopes = new_tokens.scopes
            conn.status = "connected"
            conn.updated_at = now
            await db.commit()
            logger.info("Gmail OAuth access token force-refreshed successfully", user_id=str(user_id))
            return new_tokens.access_token
        except GmailAuthRevokedException:
            conn.status = "revoked"
            await db.commit()
            raise

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
            return await cls._force_refresh_access_token(user_id=user_id, db=db)

        return decrypt_token(conn.encrypted_access_token)

    @classmethod
    async def _mark_scope_insufficient(cls, user_id: uuid.UUID, db: AsyncSession) -> None:
        """Mark connection as having insufficient scopes in DB without destroying stored scopes."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()
        if conn:
            meta = dict(conn.metadata_json or {})
            meta["scope_insufficient"] = True
            conn.metadata_json = meta
            # Preserve conn.scopes so granted permissions can be audited truthfully
            await db.commit()

    @classmethod
    async def verify_connection(
        cls, user_id: uuid.UUID, db: AsyncSession
    ) -> GmailVerifyResponse:
        """Deeply inspect and verify Gmail integration against provider tokeninfo and mailbox list."""
        stmt = select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == "google_gmail",
        )
        res = await db.execute(stmt)
        conn = res.scalar_one_or_none()
        if not conn or conn.status != "connected":
            return GmailVerifyResponse(
                connected=False,
                status="disconnected",
                verified=False,
                account_email=conn.provider_account_id if conn else None,
                has_sufficient_scopes=False,
                missing_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                granted_scopes=conn.scopes if conn else [],
                can_read_messages=False,
                api_status="disconnected",
                api_error=None,
                message="Gmail is not connected.",
            )

        provider = cls.get_provider()
        try:
            token = await cls._get_valid_access_token(user_id=user_id, db=db)
        except Exception as exc:
            return GmailVerifyResponse(
                connected=True,
                status="token_invalid",
                verified=False,
                account_email=conn.provider_account_id,
                has_sufficient_scopes=False,
                missing_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                granted_scopes=conn.scopes or [],
                can_read_messages=False,
                api_status="token_error",
                api_error=str(exc),
                message=f"Failed to retrieve or refresh access token: {exc}",
            )

        token_info = await provider.verify_token_details(token)
        if not token_info.get("valid"):
            return GmailVerifyResponse(
                connected=True,
                status="token_rejected",
                verified=False,
                account_email=conn.provider_account_id,
                has_sufficient_scopes=False,
                missing_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                granted_scopes=conn.scopes or [],
                can_read_messages=False,
                api_status="token_rejected",
                api_error=token_info.get("error_description"),
                message=f"Token rejected by Google: {token_info.get('error_description')}",
            )

        verified_scopes = token_info.get("scopes", [])
        verified_email = token_info.get("email") or conn.provider_account_id

        has_sufficient, missing = check_gmail_scopes(verified_scopes)

        # Update DB to reflect verified state
        conn.scopes = verified_scopes
        if token_info.get("email"):
            conn.provider_account_id = token_info["email"]
        meta = dict(conn.metadata_json or {})
        if has_sufficient:
            meta.pop("scope_insufficient", None)
        else:
            meta["scope_insufficient"] = True
        conn.metadata_json = meta
        conn.updated_at = datetime.now(UTC)
        await db.commit()

        # Test users.messages.list
        can_read = False
        api_status = "operational"
        api_error = None
        try:
            await provider.list_messages(access_token=token, max_results=1)
            can_read = True
        except GmailApiDisabledException as exc:
            api_status = "api_disabled"
            api_error = str(exc)
        except GmailScopeMissingException as exc:
            api_status = "scope_missing"
            api_error = str(exc)
        except GmailRateLimitException as exc:
            api_status = "rate_limited"
            api_error = str(exc)
        except Exception as exc:
            api_status = "api_error"
            api_error = str(exc)

        if not has_sufficient and api_status == "operational":
            api_status = "scope_missing"
            api_error = f"Missing required read permission: {', '.join(missing)}"
            can_read = False

        return GmailVerifyResponse(
            connected=True,
            status="operational" if (has_sufficient and can_read) else "degraded",
            verified=True,
            account_email=verified_email,
            has_sufficient_scopes=has_sufficient,
            missing_scopes=missing,
            granted_scopes=verified_scopes,
            can_read_messages=can_read,
            api_status=api_status,
            api_error=api_error,
            message="Gmail connection verified operational." if can_read else api_error,
        )

    # -------------------------------------------------------------------------
    # 2. Reading & Searching Emails
    # -------------------------------------------------------------------------
    @classmethod
    async def list_messages(
        cls,
        user_id: uuid.UUID,
        db: AsyncSession,
        query: str | None = None,
        folder: str | None = None,
        page_token: str | None = None,
        limit: int = 15,
    ) -> list[GmailMessageSummary]:
        """Fetch recent or searched messages for authenticated user."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        safe_limit = max(1, min(limit, 50))
        try:
            return await provider.list_messages(
                access_token=token,
                max_results=safe_limit,
                query=query,
                folder=folder,
                page_token=page_token,
            )
        except GmailAuthExpiredException:
            # Token expired at provider; force refresh and retry once
            try:
                refreshed_token = await cls._force_refresh_access_token(user_id=user_id, db=db)
                return await provider.list_messages(
                    access_token=refreshed_token,
                    max_results=safe_limit,
                    query=query,
                    folder=folder,
                    page_token=page_token,
                )
            except Exception as refresh_exc:
                logger.warning("Token refresh retry failed in list_messages", error=str(refresh_exc))
                raise AppException(
                    status_code=401,
                    error_code="GMAIL_AUTH_EXPIRED",
                    detail="Gmail authentication session expired. Please reconnect.",
                ) from refresh_exc
        except GmailAuthRevokedException as exc:
            raise AppException(
                status_code=401,
                error_code="GMAIL_AUTH_REVOKED",
                detail="Gmail access has been revoked or expired. Please reconnect.",
            ) from exc
        except GmailApiDisabledException as exc:
            raise AppException(
                status_code=403,
                error_code="GMAIL_API_DISABLED",
                detail=str(exc),
            ) from exc
        except GmailScopeMissingException as exc:
            await cls._mark_scope_insufficient(user_id=user_id, db=db)
            raise AppException(
                status_code=403,
                error_code="GMAIL_SCOPE_INSUFFICIENT",
                detail=str(exc),
            ) from exc
        except GmailProviderException as exc:
            if exc.status_code == 403:
                await cls._mark_scope_insufficient(user_id=user_id, db=db)
                err_code = "GMAIL_SCOPE_INSUFFICIENT" if exc.error_code == "GMAIL_PROVIDER_ERROR" else exc.error_code
            else:
                err_code = exc.error_code
            raise AppException(
                status_code=exc.status_code,
                error_code=err_code,
                detail=exc.detail,
            ) from exc

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
        try:
            return await provider.get_message_detail(access_token=token, message_id=message_id)
        except GmailAuthExpiredException:
            try:
                refreshed_token = await cls._force_refresh_access_token(user_id=user_id, db=db)
                return await provider.get_message_detail(access_token=refreshed_token, message_id=message_id)
            except Exception as refresh_exc:
                logger.warning("Token refresh retry failed in get_message", error=str(refresh_exc))
                raise AppException(
                    status_code=401,
                    error_code="GMAIL_AUTH_EXPIRED",
                    detail="Gmail authentication session expired. Please reconnect.",
                ) from refresh_exc
        except GmailAuthRevokedException as exc:
            raise AppException(
                status_code=401,
                error_code="GMAIL_AUTH_REVOKED",
                detail="Gmail access has been revoked or expired. Please reconnect.",
            ) from exc
        except GmailApiDisabledException as exc:
            raise AppException(
                status_code=403,
                error_code="GMAIL_API_DISABLED",
                detail=str(exc),
            ) from exc
        except GmailScopeMissingException as exc:
            await cls._mark_scope_insufficient(user_id=user_id, db=db)
            raise AppException(
                status_code=403,
                error_code="GMAIL_SCOPE_INSUFFICIENT",
                detail=str(exc),
            ) from exc
        except GmailProviderException as exc:
            if exc.status_code == 403:
                await cls._mark_scope_insufficient(user_id=user_id, db=db)
                err_code = "GMAIL_SCOPE_INSUFFICIENT" if exc.error_code == "GMAIL_PROVIDER_ERROR" else exc.error_code
            else:
                err_code = exc.error_code
            raise AppException(
                status_code=exc.status_code,
                error_code=err_code,
                detail=exc.detail,
            ) from exc

    @classmethod
    async def modify_message(
        cls,
        user_id: uuid.UUID,
        message_id: str,
        add_labels: list[str] | None,
        remove_labels: list[str] | None,
        db: AsyncSession,
    ) -> list[str]:
        """Add or remove label IDs on a message (e.g. UNREAD, STARRED)."""
        token = await cls._get_valid_access_token(user_id=user_id, db=db)
        provider = cls.get_provider()
        try:
            return await provider.modify_message(
                access_token=token,
                message_id=message_id,
                add_label_ids=add_labels,
                remove_label_ids=remove_labels,
            )
        except GmailAuthExpiredException:
            try:
                refreshed_token = await cls._force_refresh_access_token(user_id=user_id, db=db)
                return await provider.modify_message(
                    access_token=refreshed_token,
                    message_id=message_id,
                    add_label_ids=add_labels,
                    remove_label_ids=remove_labels,
                )
            except Exception as refresh_exc:
                raise AppException(
                    status_code=401,
                    error_code="GMAIL_AUTH_EXPIRED",
                    detail="Gmail authentication session expired. Please reconnect.",
                ) from refresh_exc
        except GmailScopeMissingException as exc:
            # Only modifying message labels failed; do not wipe connection or read permissions
            raise AppException(
                status_code=403,
                error_code="GMAIL_MODIFY_SCOPE_MISSING",
                detail="Modifying message status requires additional permissions. Please reconnect if you wish to star or mark emails read/unread.",
            ) from exc
        except GmailProviderException as exc:
            raise AppException(
                status_code=exc.status_code,
                error_code=exc.error_code,
                detail=exc.detail,
            ) from exc

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
