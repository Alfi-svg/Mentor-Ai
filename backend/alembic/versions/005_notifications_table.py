"""Create notifications table for deadline alerts and reminders.

Revision ID: 005_notifications_table
Revises: 004_external_calendar_connections
Create Date: 2026-10-14 04:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_notifications_table"
down_revision: str | None = "004_external_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("notification_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "notification_type IN ('due_soon', 'due_now', 'overdue')",
            name="chk_notification_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Indexes
    op.create_index(
        "idx_notifications_user_read",
        "notifications",
        ["user_id", "is_read"],
    )
    op.create_index(
        "idx_notifications_user_scheduled",
        "notifications",
        ["user_id", "scheduled_for"],
    )
    op.create_index(
        "idx_notifications_task_type",
        "notifications",
        ["task_id", "notification_type"],
    )

    # 3. Enable Row-Level Security for PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS auth;")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$
            BEGIN
                RETURN NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
            EXCEPTION WHEN OTHERS THEN
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql STABLE;
            """
        )
        op.execute("ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public'
                    AND tablename = 'notifications'
                    AND policyname = 'notifications_tenant_isolation'
                ) THEN
                    CREATE POLICY "notifications_tenant_isolation"
                        ON public.notifications
                        FOR ALL
                        USING (auth.uid() = user_id)
                        WITH CHECK (auth.uid() = user_id);
                END IF;
            END $$;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            'DROP POLICY IF EXISTS "notifications_tenant_isolation" ON public.notifications;'
        )
    op.drop_index("idx_notifications_task_type", table_name="notifications")
    op.drop_index("idx_notifications_user_scheduled", table_name="notifications")
    op.drop_index("idx_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
