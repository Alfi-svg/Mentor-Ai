"""Pydantic schemas and transfer objects for Gmail integration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GmailStatusResponse(BaseModel):
    """Status of user's external Gmail connection."""

    provider: str = "google_gmail"
    is_connected: bool
    configured: bool
    status_label: str  # connected, disconnected, unconfigured, revoked, expired
    account_email: str | None = None
    last_synced_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


class GmailConnectResponse(BaseModel):
    """OAuth initiation response with signed authorization URL."""

    authorization_url: str
    state: str
    provider: str = "google_gmail"


class GmailMessageSummary(BaseModel):
    """Lightweight metadata summary of an email message."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    sender: str
    recipient: str | None = None
    subject: str
    date: datetime | str | None = None
    snippet: str
    is_unread: bool = False
    has_attachments: bool = False


class GmailMessageDetail(BaseModel):
    """Full detail of an email message with sanitized plain body."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    sender: str
    recipient: str | None = None
    subject: str
    date: datetime | str | None = None
    snippet: str
    body_plain: str
    sanitized: bool = True
    has_attachments: bool = False
    labels: list[str] = Field(default_factory=list)


class GmailEmailSummaryResult(BaseModel):
    """Structured email summary strictly distinguishing facts from AI interpretation."""

    message_id: str
    subject: str
    sender: str
    verified_facts: list[str] = Field(
        description="Explicit factual statements (dates, senders, deadlines) extracted directly from the email"
    )
    ai_interpretation: str = Field(
        description="AI contextual synthesis and recommended next steps"
    )
    confidence_score: float = Field(
        default=0.9, ge=0.0, le=1.0, description="Confidence rating of the interpretation"
    )


class EmailTaskCandidate(BaseModel):
    """Proposed task candidate extracted from email content for user review."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    proposed_deadline: datetime | None = None
    is_deadline_proposed: bool = True
    is_deadline_ambiguous: bool = False
    ambiguity_reason: str | None = None
    estimated_duration_minutes: int = Field(default=60, ge=5, le=720)
    priority: str = Field(default="P3", pattern="^(P1|P2|P3|P4)$")
    energy_level: str = Field(default="medium", pattern="^(high|medium|low)$")
    source_message_id: str
    source_subject: str
    source_sender: str


class GmailDraftCreate(BaseModel):
    """Payload to create an email draft without sending."""

    to: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    thread_id: str | None = None


class GmailDraftResponse(BaseModel):
    """Result of draft creation."""

    draft_id: str
    message_id: str | None = None
    to: str
    subject: str
    created_at: datetime


class GmailSendPayload(BaseModel):
    """Payload for staged email sending (requires explicit approval)."""

    to: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    thread_id: str | None = None
    source_reference: str | None = None


class GmailSendResult(BaseModel):
    """Verified outcome of a completed email send action."""

    message_id: str
    thread_id: str
    to: str
    subject: str
    sent_at: datetime
    verified: bool = True
