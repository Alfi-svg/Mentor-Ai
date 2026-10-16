"""Expand task calendar_sync_status length to 32.

Revision ID: 009_expand_task_sync_status
Revises: 008_task_calendar_sync
Create Date: 2026-10-17 01:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_expand_task_sync_status"
down_revision: str | None = "008_task_calendar_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column(
            "calendar_sync_status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            existing_nullable=False,
            existing_server_default="unsynced",
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column(
            "calendar_sync_status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=20),
            existing_nullable=False,
            existing_server_default="unsynced",
        )
