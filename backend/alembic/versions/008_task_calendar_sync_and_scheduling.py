"""Task calendar sync and scheduling extensions.

Revision ID: 008_task_calendar_sync
Revises: 007_gmail_integration
Create Date: 2026-10-16 19:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_task_calendar_sync"
down_revision: str | None = "007_gmail_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add scheduling and Google Calendar sync columns to tasks
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("google_calendar_event_id", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("calendar_sync_status", sa.String(length=20), server_default="unsynced", nullable=False)
        )
        batch_op.add_column(sa.Column("calendar_sync_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("idx_tasks_user_gcal_event", ["user_id", "google_calendar_event_id"])
        batch_op.create_index("idx_tasks_user_sync_status", ["user_id", "calendar_sync_status"])
        batch_op.create_index("idx_tasks_user_scheduled_start", ["user_id", "scheduled_start"])

    # 2. Add calendar_auto_sync column to user_preferences
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.add_column(
            sa.Column("calendar_auto_sync", sa.Boolean(), server_default=sa.true(), nullable=False)
        )


def downgrade() -> None:
    # 1. Remove calendar_auto_sync column from user_preferences
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.drop_column("calendar_auto_sync")

    # 2. Remove scheduling and sync columns and indexes from tasks
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("idx_tasks_user_scheduled_start")
        batch_op.drop_index("idx_tasks_user_sync_status")
        batch_op.drop_index("idx_tasks_user_gcal_event")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("calendar_sync_error")
        batch_op.drop_column("calendar_sync_status")
        batch_op.drop_column("google_calendar_event_id")
        batch_op.drop_column("scheduled_end")
        batch_op.drop_column("scheduled_start")
