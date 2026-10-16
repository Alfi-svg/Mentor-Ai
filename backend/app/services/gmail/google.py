"""Production Google Gmail API v1 provider implementation using httpx."""

import asyncio
import base64
import email
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.calendar.models import OAuthTokenData
from app.services.gmail.base import (
    GmailApiDisabledException,
    GmailAuthExpiredException,
    GmailAuthRevokedException,
    GmailProvider,
    GmailProviderException,
    GmailRateLimitException,
    GmailScopeMissingException,
    GmailTimeoutException,
)
from app.services.gmail.models import (
    GmailDraftCreate,
    GmailDraftResponse,
    GmailMessageDetail,
    GmailMessageSummary,
    GmailSendPayload,
    GmailSendResult,
)
from app.services.gmail.sanitizer import sanitize_email_text

logger = get_logger("mentor_ai.gmail.google")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Least-privilege Gmail scopes
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _safe_b64decode(data: str) -> str:
    """Safely decode base64url data from Gmail API payloads with proper padding."""
    if not data:
        return ""
    clean_str = data.strip().replace("\n", "").replace("\r", "")
    missing_padding = (4 - len(clean_str) % 4) % 4
    if missing_padding:
        clean_str += "=" * missing_padding
    try:
        decoded_bytes = base64.urlsafe_b64decode(clean_str.encode("utf-8"))
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_google_error(resp: httpx.Response, default_msg: str = "Google API request failed") -> tuple[str, str]:
    """Extract human-readable error message and specific machine reason from Google API error response."""
    error_msg = default_msg
    error_reason = "unknown"
    try:
        body = resp.json()
        error_obj = body.get("error", {})
        if isinstance(error_obj, dict):
            error_msg = error_obj.get("message") or error_msg
            status_val = error_obj.get("status")
            details = error_obj.get("details", [])
            if isinstance(details, list):
                for d in details:
                    if isinstance(d, dict) and "reason" in d:
                        error_reason = d["reason"]
                        break
            errors = error_obj.get("errors", [])
            if error_reason == "unknown" and isinstance(errors, list):
                for e in errors:
                    if isinstance(e, dict) and "reason" in e:
                        error_reason = e["reason"]
                        break
            if error_reason == "unknown" and status_val:
                error_reason = str(status_val)
    except Exception:
        error_msg = resp.text or default_msg

    return error_msg, error_reason



class GoogleGmailAdapter(GmailProvider):
    """Production adapter for Google Gmail API v1."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "google_gmail"

    def _get_client_id(self) -> str:
        return settings.GOOGLE_GMAIL_CLIENT_ID or settings.GOOGLE_CLIENT_ID

    def _get_client_secret(self) -> str:
        return settings.GOOGLE_GMAIL_CLIENT_SECRET or settings.GOOGLE_CLIENT_SECRET

    def get_authorization_url(self, state: str) -> str:
        """Construct the Google OAuth 2.0 authorization URL for Gmail."""
        if not settings.has_google_gmail_credentials:
            raise GmailProviderException(
                "Google Gmail credentials are not configured in environment.",
                status_code=503,
            )

        params = {
            "client_id": self._get_client_id(),
            "redirect_uri": settings.GOOGLE_GMAIL_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent select_account",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client and not self._client.is_closed:
            return self._client
        return httpx.AsyncClient(timeout=settings.GMAIL_REQUEST_TIMEOUT_SECONDS)

    async def exchange_code(self, code: str) -> OAuthTokenData:
        """Exchange authorization code for OAuth tokens."""
        client = await self._get_client()
        should_close = client != self._client

        payload = {
            "code": code,
            "client_id": self._get_client_id(),
            "client_secret": self._get_client_secret(),
            "redirect_uri": settings.GOOGLE_GMAIL_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        try:
            resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if resp.status_code == 400:
                raise GmailProviderException(
                    "Failed to exchange authorization code with Google.",
                    status_code=400,
                )
            resp.raise_for_status()
            data = resp.json()

            email_addr: str | None = None
            access_token = data.get("access_token", "")
            if access_token:
                try:
                    ui_resp = await client.get(
                        GOOGLE_USERINFO_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if ui_resp.status_code == 200:
                        email_addr = ui_resp.json().get("email")
                except Exception as exc:
                    logger.warning("Failed to fetch user email during Gmail OAuth exchange", error=str(exc))

            expires_in = data.get("expires_in", 3600)
            return OAuthTokenData(
                access_token=access_token,
                refresh_token=data.get("refresh_token"),
                token_type=data.get("token_type", "Bearer"),
                expires_in=expires_in,
                expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
                scopes=data.get("scope", "").split(),
                account_email=email_addr,
            )
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def refresh_token(self, refresh_token: str) -> OAuthTokenData:
        """Obtain a fresh access token using a refresh token."""
        client = await self._get_client()
        should_close = client != self._client

        payload = {
            "client_id": self._get_client_id(),
            "client_secret": self._get_client_secret(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if resp.status_code in (400, 401):
                raise GmailAuthRevokedException(
                    "Gmail refresh token is invalid or consent was revoked."
                )
            resp.raise_for_status()
            data = resp.json()

            expires_in = data.get("expires_in", 3600)
            return OAuthTokenData(
                access_token=data.get("access_token", ""),
                refresh_token=refresh_token,
                token_type=data.get("token_type", "Bearer"),
                expires_in=expires_in,
                expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
                scopes=data.get("scope", "").split() if "scope" in data else GMAIL_SCOPES,
            )
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def revoke_token(self, token: str) -> bool:
        """Revoke authorization token with Google."""
        client = await self._get_client()
        should_close = client != self._client

        try:
            resp = await client.post(
                GOOGLE_REVOKE_URL,
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Error revoking Google Gmail token", error=str(exc))
            return False
        finally:
            if should_close:
                await client.aclose()

    async def verify_token_details(self, access_token: str) -> dict[str, Any]:
        """Query Google's tokeninfo endpoint to verify token validity, granted scopes, and account email."""
        client = await self._get_client()
        should_close = client != self._client

        try:
            resp = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"access_token": access_token},
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_scope = data.get("scope", "")
                granted_scopes = raw_scope.split() if isinstance(raw_scope, str) else []
                return {
                    "valid": True,
                    "email": data.get("email"),
                    "scopes": granted_scopes,
                    "expires_in": int(data.get("expires_in", 0)),
                    "audience": data.get("aud") or data.get("azp"),
                }
            elif resp.status_code in (400, 401):
                err_data = {}
                try:
                    err_data = resp.json()
                except Exception:
                    pass
                return {
                    "valid": False,
                    "error": err_data.get("error", "invalid_token"),
                    "error_description": err_data.get("error_description", resp.text),
                }
            return {
                "valid": False,
                "error": f"http_{resp.status_code}",
                "error_description": resp.text,
            }
        except Exception as exc:
            logger.warning("Google tokeninfo verification failed with network/parsing exception", error=str(exc))
            return {
                "valid": False,
                "error": "verification_exception",
                "error_description": str(exc),
            }
        finally:
            if should_close:
                await client.aclose()

    async def list_messages(
        self,
        access_token: str,
        max_results: int = 10,
        query: str | None = None,
        folder: str | None = None,
        page_token: str | None = None,
    ) -> list[GmailMessageSummary]:
        """Fetch list of message summaries matching query and folder."""
        client = await self._get_client()
        should_close = client != self._client

        safe_max = max(1, min(max_results, 50))
        params: dict[str, Any] = {"maxResults": safe_max}
        if query:
            params["q"] = query

        if folder:
            folder_upper = folder.upper()
            if folder_upper in ("INBOX", "STARRED", "SENT", "DRAFT", "TRASH", "SPAM"):
                params["labelIds"] = [folder_upper]

        if page_token:
            params["pageToken"] = page_token

        try:
            resp = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code == 401:
                raise GmailAuthExpiredException()
            if resp.status_code == 403:
                err_msg, err_reason = _parse_google_error(resp, "Forbidden: Gmail API access denied.")
                logger.error(
                    "Google Gmail API 403 Forbidden on list_messages",
                    error_message=err_msg,
                    error_reason=err_reason,
                )
                if err_reason == "SERVICE_DISABLED" or "disabled" in err_msg.lower() or "has not been used in project" in err_msg.lower():
                    raise GmailApiDisabledException(
                        f"Gmail API is disabled in your Google Cloud project. Please enable it at https://console.developers.google.com/apis/api/gmail.googleapis.com/overview: {err_msg}"
                    )
                if err_reason in ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", "insufficientPermissions") or "scope" in err_msg.lower():
                    raise GmailScopeMissingException(
                        f"Google account permissions missing. Please reconnect and grant read access to your Gmail messages: {err_msg}"
                    )
                raise GmailProviderException(f"Gmail API forbidden (403): {err_msg}", status_code=403)
            if resp.status_code == 429:
                raise GmailRateLimitException()
            resp.raise_for_status()

            data = resp.json()
            messages_meta = data.get("messages", [])
            if not messages_meta:
                # Legitimate empty mailbox / folder
                return []

            async def fetch_summary(mid: str) -> GmailMessageSummary | None:
                try:
                    m_resp = await client.get(
                        f"{GMAIL_API_BASE}/messages/{mid}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={
                            "format": "metadata",
                            "metadataHeaders": ["Subject", "From", "To", "Date"],
                        },
                    )
                    if m_resp.status_code == 401:
                        raise GmailAuthExpiredException()
                    if m_resp.status_code == 403:
                        sub_msg, sub_reason = _parse_google_error(m_resp, "Forbidden to get message metadata.")
                        if sub_reason == "SERVICE_DISABLED" or "disabled" in sub_msg.lower():
                            raise GmailApiDisabledException(sub_msg)
                        raise GmailScopeMissingException(sub_msg)
                    if m_resp.status_code == 429:
                        raise GmailRateLimitException()
                    m_resp.raise_for_status()

                    m_data = m_resp.json()
                    headers = {h["name"].lower(): h["value"] for h in m_data.get("payload", {}).get("headers", [])}
                    lbls = m_data.get("labelIds", [])
                    return GmailMessageSummary(
                        id=m_data["id"],
                        thread_id=m_data.get("threadId", m_data["id"]),
                        sender=sanitize_email_text(headers.get("from", "Unknown")),
                        recipient=sanitize_email_text(headers.get("to")),
                        subject=sanitize_email_text(headers.get("subject", "(No Subject)")),
                        date=headers.get("date"),
                        snippet=sanitize_email_text(m_data.get("snippet", "")),
                        is_unread="UNREAD" in lbls,
                        is_starred="STARRED" in lbls,
                        has_attachments=any(
                            part.get("filename")
                            for part in m_data.get("payload", {}).get("parts", [])
                        ),
                        labels=lbls,
                    )
                except (GmailAuthExpiredException, GmailAuthRevokedException, GmailApiDisabledException, GmailScopeMissingException, GmailRateLimitException):
                    raise
                except Exception as exc:
                    logger.warning("Failed fetching metadata for Gmail message", message_id=mid, error=str(exc))
                    return None

            tasks = [fetch_summary(item["id"]) for item in messages_meta if "id" in item]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Re-raise any fatal auth/scope exceptions
            for r in results:
                if isinstance(r, (GmailAuthExpiredException, GmailAuthRevokedException, GmailApiDisabledException, GmailScopeMissingException, GmailRateLimitException)):
                    raise r

            summaries: list[GmailMessageSummary] = [
                r for r in results if isinstance(r, GmailMessageSummary)
            ]

            # Distinguish: if messages existed but all failed to load, do NOT return an empty list
            if messages_meta and not summaries and results:
                first_exc = next((r for r in results if isinstance(r, Exception)), None)
                err_detail = str(first_exc) if first_exc else "Failed to parse message summaries"
                raise GmailProviderException(
                    f"Found {len(messages_meta)} messages in Gmail, but failed to retrieve details: {err_detail}",
                    status_code=502,
                )

            return summaries
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    def _extract_body_text(self, payload: dict[str, Any]) -> str:
        """Extract plain text from nested Gmail message payload parts."""
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime_type == "text/plain" and body_data:
            text = _safe_b64decode(body_data)
            if text:
                return text

        # If html and no plain found yet
        if mime_type == "text/html" and body_data:
            text = _safe_b64decode(body_data)
            if text:
                return sanitize_email_text(text)

        # Check multipart parts
        parts = payload.get("parts", [])
        for part in parts:
            extracted = self._extract_body_text(part)
            if extracted:
                return extracted

        return ""

    def _extract_html_text(self, payload: dict[str, Any]) -> str | None:
        """Extract html body from nested Gmail message payload parts."""
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime_type == "text/html" and body_data:
            text = _safe_b64decode(body_data)
            if text:
                return text

        parts = payload.get("parts", [])
        for part in parts:
            extracted = self._extract_html_text(part)
            if extracted:
                return extracted

        return None

    def _extract_attachments_summary(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect attachment names, mime types, and file sizes."""
        attachments: list[dict[str, Any]] = []
        for part in payload.get("parts", []):
            fname = part.get("filename")
            if fname:
                attachments.append(
                    {
                        "filename": fname,
                        "mime_type": part.get("mimeType", "application/octet-stream"),
                        "size": part.get("body", {}).get("size", 0),
                    }
                )
            if "parts" in part:
                attachments.extend(self._extract_attachments_summary(part))
        return attachments

    async def get_message_detail(
        self,
        access_token: str,
        message_id: str,
    ) -> GmailMessageDetail:
        """Fetch full details and body of a single message."""
        client = await self._get_client()
        should_close = client != self._client

        try:
            resp = await client.get(
                f"{GMAIL_API_BASE}/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"},
            )
            if resp.status_code == 401:
                raise GmailAuthExpiredException()
            if resp.status_code == 403:
                err_msg, err_reason = _parse_google_error(resp, "Forbidden to get message details.")
                if err_reason == "SERVICE_DISABLED" or "disabled" in err_msg.lower():
                    raise GmailApiDisabledException(err_msg)
                raise GmailScopeMissingException(err_msg)
            if resp.status_code == 404:
                raise GmailProviderException("Message not found in Gmail.", status_code=404)
            resp.raise_for_status()

            m_data = resp.json()
            payload = m_data.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

            raw_body = self._extract_body_text(payload)
            if not raw_body:
                raw_body = m_data.get("snippet", "")

            sanitized_body = sanitize_email_text(raw_body)
            raw_html = self._extract_html_text(payload)
            attachments = self._extract_attachments_summary(payload)
            labels = m_data.get("labelIds", [])

            return GmailMessageDetail(
                id=m_data["id"],
                thread_id=m_data.get("threadId", m_data["id"]),
                sender=sanitize_email_text(headers.get("from", "Unknown")),
                recipient=sanitize_email_text(headers.get("to")),
                subject=sanitize_email_text(headers.get("subject", "(No Subject)")),
                date=headers.get("date"),
                snippet=sanitize_email_text(m_data.get("snippet", "")),
                body_plain=sanitized_body,
                body_html=raw_html,
                sanitized=True,
                has_attachments=len(attachments) > 0,
                attachments=attachments,
                labels=labels,
                is_starred="STARRED" in labels,
            )
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def modify_message(
        self,
        access_token: str,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> list[str]:
        """Add or remove label IDs (e.g. UNREAD, STARRED) from a message."""
        client = await self._get_client()
        should_close = client != self._client
        payload: dict[str, Any] = {
            "addLabelIds": add_label_ids or [],
            "removeLabelIds": remove_label_ids or [],
        }

        try:
            resp = await client.post(
                f"{GMAIL_API_BASE}/messages/{message_id}/modify",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
            if resp.status_code == 401:
                raise GmailAuthExpiredException()
            if resp.status_code == 403:
                err_msg, err_reason = _parse_google_error(resp, "Forbidden to modify message.")
                if err_reason == "SERVICE_DISABLED" or "disabled" in err_msg.lower():
                    raise GmailApiDisabledException(err_msg)
                raise GmailScopeMissingException(
                    f"Modifying message labels requires modify permission: {err_msg}"
                )
            if resp.status_code == 404:
                raise GmailProviderException("Message not found in Gmail.", status_code=404)
            resp.raise_for_status()
            data = resp.json()
            return data.get("labelIds", [])
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def create_draft(
        self,
        access_token: str,
        draft: GmailDraftCreate,
    ) -> GmailDraftResponse:
        """Create a draft email without sending."""
        client = await self._get_client()
        should_close = client != self._client

        msg = MIMEText(draft.body, "plain", "utf-8")
        msg["To"] = draft.to
        msg["Subject"] = draft.subject

        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        body_payload: dict[str, Any] = {"message": {"raw": raw_b64}}
        if draft.thread_id:
            body_payload["message"]["threadId"] = draft.thread_id

        try:
            resp = await client.post(
                f"{GMAIL_API_BASE}/drafts",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body_payload,
            )
            if resp.status_code == 401:
                raise GmailAuthExpiredException()
            resp.raise_for_status()

            res_data = resp.json()
            return GmailDraftResponse(
                draft_id=res_data["id"],
                message_id=res_data.get("message", {}).get("id"),
                to=draft.to,
                subject=draft.subject,
                created_at=datetime.now(UTC),
            )
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def send_email(
        self,
        access_token: str,
        payload: GmailSendPayload,
    ) -> GmailSendResult:
        """Directly send an email message via Gmail API."""
        client = await self._get_client()
        should_close = client != self._client

        msg = MIMEText(payload.body, "plain", "utf-8")
        msg["To"] = payload.to
        msg["Subject"] = payload.subject

        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        body_payload: dict[str, Any] = {"raw": raw_b64}
        if payload.thread_id:
            body_payload["threadId"] = payload.thread_id

        try:
            resp = await client.post(
                f"{GMAIL_API_BASE}/messages/send",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body_payload,
            )
            if resp.status_code == 401:
                raise GmailAuthExpiredException()
            resp.raise_for_status()

            res_data = resp.json()
            return GmailSendResult(
                message_id=res_data["id"],
                thread_id=res_data.get("threadId", res_data["id"]),
                to=payload.to,
                subject=payload.subject,
                sent_at=datetime.now(UTC),
                verified=True,
            )
        except httpx.TimeoutException as exc:
            raise GmailTimeoutException() from exc
        finally:
            if should_close:
                await client.aclose()

    async def verify_email_sent(
        self,
        access_token: str,
        subject: str,
        recipient: str,
        sent_after: datetime,
    ) -> str | None:
        """Query sent messages to independently verify whether an email was delivered."""
        client = await self._get_client()
        should_close = client != self._client

        # Search for message to recipient
        query = f"to:{recipient}"
        try:
            resp = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "maxResults": 5},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            messages = data.get("messages", [])
            for item in messages:
                mid = item["id"]
                m_resp = await client.get(
                    f"{GMAIL_API_BASE}/messages/{mid}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"format": "metadata", "metadataHeaders": ["Subject", "To"]},
                )
                if m_resp.status_code == 200:
                    m_data = m_resp.json()
                    headers = {h["name"].lower(): h["value"] for h in m_data.get("payload", {}).get("headers", [])}
                    if headers.get("subject", "").strip().lower() == subject.strip().lower():
                        return str(m_data["id"])
            return None
        except Exception as exc:
            logger.warning("Error verifying sent email with Gmail provider", error=str(exc))
            return None
        finally:
            if should_close:
                await client.aclose()
