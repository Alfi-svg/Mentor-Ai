"""Add copilot_settings to user_preferences table.

Revision ID: 011_add_copilot_settings
Revises: 010_copilot_missed_sessions
Create Date: 2026-10-17 05:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_add_copilot_settings"
down_revision: str | None = "010_copilot_missed_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add copilot_settings JSON column to user_preferences
    op.add_column(
        "user_preferences",
        sa.Column(
            "copilot_settings",
            sa.JSON(),
            nullable=True,
            server_default='{"voice_preset": "nova", "voice_gender": "feminine", "auto_play_speech": true, "stt_engine": "openai"}',
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "copilot_settings")
