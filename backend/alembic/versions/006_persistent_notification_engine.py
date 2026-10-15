"""Expand notifications table for persistent notification engine and user preferences.

Revision ID: 006_notification_engine
Revises: 005_notifications_table
Create Date: 2026-10-15 06:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "006_notification_engine"
down_revision: str | None = "005_notifications_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1. Add new columns to notifications table
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("action_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("channel", sa.String(length=32), server_default="in_app", nullable=False)
        )
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), server_default="pending", nullable=False)
        )
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False)
        )
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deduplication_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("payload", JSON_TYPE, nullable=True))
        batch_op.create_foreign_key(
            "fk_notifications_action_id",
            "action_history",
            ["action_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2. Add notification_settings column to user_preferences
    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.add_column(
            sa.Column("notification_settings", JSON_TYPE, server_default=sa.text("'{}'"), nullable=True)
        )

    # 3. Synchronize existing notifications delivered state
    op.execute("UPDATE notifications SET status = 'delivered' WHERE delivered_at IS NOT NULL;")

    # 4. Check constraints update
    if is_pg:
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_type;")
        op.create_check_constraint(
            "chk_notification_type",
            "notifications",
            "notification_type IN ('due_soon', 'due_now', 'overdue', 'upcoming_task', 'schedule_conflict', 'calendar_revoked', 'calendar_stale', 'action_required', 'action_failed', 'task_completed')",
        )
        op.create_check_constraint(
            "chk_notification_status",
            "notifications",
            "status IN ('pending', 'processing', 'delivered', 'failed', 'cancelled', 'permanently_failed')",
        )
        op.create_check_constraint(
            "chk_notification_channel",
            "notifications",
            "channel IN ('in_app', 'email', 'browser_push')",
        )

    # 5. Indexes for dispatcher and deduplication queries
    op.create_index(
        "idx_notifications_dispatch",
        "notifications",
        ["status", "scheduled_for", "lease_expires_at"],
    )
    op.create_index(
        "idx_notifications_user_dedup",
        "notifications",
        ["user_id", "deduplication_key"],
    )
    op.create_index(
        "idx_notifications_action_id",
        "notifications",
        ["action_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.drop_index("idx_notifications_action_id", table_name="notifications")
    op.drop_index("idx_notifications_user_dedup", table_name="notifications")
    op.drop_index("idx_notifications_dispatch", table_name="notifications")

    if is_pg:
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_channel;")
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_status;")
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_type;")
        op.create_check_constraint(
            "chk_notification_type",
            "notifications",
            "notification_type IN ('due_soon', 'due_now', 'overdue')",
        )

    with op.batch_alter_table("user_preferences") as batch_op:
        batch_op.drop_column("notification_settings")

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("fk_notifications_action_id", type_="foreignkey")
        batch_op.drop_column("payload")
        batch_op.drop_column("last_error")
        batch_op.drop_column("deduplication_key")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("max_attempts")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("status")
        batch_op.drop_column("channel")
        batch_op.drop_column("action_id")
