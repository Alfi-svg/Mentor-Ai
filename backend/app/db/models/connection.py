"""External service connection domain model for OAuth providers."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# Cross-dialect JSON column type
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class ExternalConnection(Base):
    """Encrypted OAuth integration link with an external service (e.g. Google Calendar)."""

    __tablename__ = "external_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('connected', 'expired', 'revoked', 'disconnected')",
            name="chk_connection_status",
        ),
        CheckConstraint(
            "provider IN ('google_calendar', 'ical', 'google_gmail', 'gmail')",
            name="chk_connection_provider",
        ),
        UniqueConstraint("user_id", "provider", name="uq_user_provider_connection"),
        Index("idx_ext_conn_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="google_calendar")
    provider_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Tokens are strictly encrypted at rest via app.core.crypto.encrypt_token
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    scopes: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(25), nullable=False, default="connected")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="external_connections")  # type: ignore # noqa: F821
