"""Gmail integration service package."""

from app.services.gmail.base import (
    GmailAuthExpiredException,
    GmailAuthRevokedException,
    GmailProvider,
    GmailProviderException,
    GmailRateLimitException,
    GmailScopeMissingException,
    GmailTimeoutException,
)
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
from app.services.gmail.service import GmailService

__all__ = [
    "EmailTaskCandidate",
    "GmailAuthExpiredException",
    "GmailAuthRevokedException",
    "GmailConnectResponse",
    "GmailDraftCreate",
    "GmailDraftResponse",
    "GmailEmailSummaryResult",
    "GmailMessageDetail",
    "GmailMessageSummary",
    "GmailProvider",
    "GmailProviderException",
    "GmailRateLimitException",
    "GmailScopeMissingException",
    "GmailSendPayload",
    "GmailSendResult",
    "GmailService",
    "GmailStatusResponse",
    "GmailTimeoutException",
]
