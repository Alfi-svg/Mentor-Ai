"""Abstract provider protocol and exceptions for Gmail integration."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.core.errors import AppException
from app.services.calendar.models import OAuthTokenData
from app.services.gmail.models import (
    GmailDraftCreate,
    GmailDraftResponse,
    GmailMessageDetail,
    GmailMessageSummary,
    GmailSendPayload,
    GmailSendResult,
)


class GmailProviderException(AppException):
    """Base exception for Gmail API provider errors."""

    def __init__(self, detail: str, status_code: int = 500, error_code: str = "GMAIL_PROVIDER_ERROR"):
        super().__init__(detail=detail, status_code=status_code, error_code=error_code)


class GmailAuthExpiredException(GmailProviderException):
    """Raised when access token has expired and must be refreshed."""

    def __init__(self, detail: str = "Gmail access token has expired."):
        super().__init__(detail=detail, status_code=401, error_code="GMAIL_AUTH_EXPIRED")


class GmailAuthRevokedException(GmailProviderException):
    """Raised when OAuth consent has been revoked by user or administrator."""

    def __init__(self, detail: str = "Gmail connection was revoked by provider. Please reconnect."):
        super().__init__(detail=detail, status_code=401, error_code="GMAIL_AUTH_REVOKED")


class GmailTimeoutException(GmailProviderException):
    """Raised when request to Gmail API exceeds timeout."""

    def __init__(self, detail: str = "Request to Gmail API timed out."):
        super().__init__(detail=detail, status_code=504, error_code="GMAIL_TIMEOUT")


class GmailRateLimitException(GmailProviderException):
    """Raised when Gmail API rate limit / quota is exceeded."""

    def __init__(self, detail: str = "Gmail API rate limit exceeded."):
        super().__init__(detail=detail, status_code=429, error_code="GMAIL_RATE_LIMIT")


class GmailScopeMissingException(GmailProviderException):
    """Raised when an operation requires a scope not granted by the token."""

    def __init__(self, detail: str = "Required Gmail scope has not been granted by user."):
        super().__init__(detail=detail, status_code=403, error_code="GMAIL_SCOPE_MISSING")


class GmailApiDisabledException(GmailProviderException):
    """Raised when Gmail API is not enabled in Google Cloud Console."""

    def __init__(self, detail: str = "Gmail API is not enabled in your Google Cloud project."):
        super().__init__(detail=detail, status_code=403, error_code="GMAIL_API_DISABLED")


@runtime_checkable
class GmailProvider(Protocol):
    """Protocol for Gmail provider adapters (Google production vs mock test adapter)."""

    @property
    def provider_name(self) -> str:
        """Normalized provider identifier ('google_gmail')."""
        ...

    def get_authorization_url(self, state: str) -> str:
        """Construct the Google OAuth 2.0 authorization URL."""
        ...

    async def exchange_code(self, code: str) -> OAuthTokenData:
        """Exchange authorization code for OAuth tokens."""
        ...

    async def refresh_token(self, refresh_token: str) -> OAuthTokenData:
        """Obtain fresh access token using refresh token."""
        ...

    async def revoke_token(self, token: str) -> bool:
        """Revoke authorization token with Google."""
        ...

    async def verify_token_details(self, access_token: str) -> dict[str, Any]:
        """Verify access token against provider, returning validity, scopes, and account email."""
        ...

    async def list_messages(
        self,
        access_token: str,
        max_results: int = 10,
        query: str | None = None,
        folder: str | None = None,
        page_token: str | None = None,
    ) -> list[GmailMessageSummary]:
        """Fetch list of message summaries matching query and folder."""
        ...

    async def get_message_detail(
        self,
        access_token: str,
        message_id: str,
    ) -> GmailMessageDetail:
        """Fetch full details and body of a single message."""
        ...

    async def modify_message(
        self,
        access_token: str,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> list[str]:
        """Add or remove label IDs (e.g. UNREAD, STARRED) from an email message."""
        ...

    async def create_draft(
        self,
        access_token: str,
        draft: GmailDraftCreate,
    ) -> GmailDraftResponse:
        """Create a draft email without sending."""
        ...

    async def send_email(
        self,
        access_token: str,
        payload: GmailSendPayload,
    ) -> GmailSendResult:
        """Directly send an email message."""
        ...

    async def verify_email_sent(
        self,
        access_token: str,
        subject: str,
        recipient: str,
        sent_after: datetime,
    ) -> str | None:
        """Query sent messages to independently verify whether a message was delivered."""
        ...
