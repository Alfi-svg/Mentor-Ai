"""Expand external_connections provider constraint for Gmail integration.

Revision ID: 007_gmail_integration
Revises: 006_notification_engine
Create Date: 2026-10-16 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_gmail_integration"
down_revision: str | None = "006_notification_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.drop_constraint("chk_connection_provider", "external_connections", type_="check")
        op.create_check_constraint(
            "chk_connection_provider",
            "external_connections",
            "provider IN ('google_calendar', 'ical', 'google_gmail', 'gmail')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.drop_constraint("chk_connection_provider", "external_connections", type_="check")
        op.create_check_constraint(
            "chk_connection_provider",
            "external_connections",
            "provider IN ('google_calendar', 'ical')",
        )
