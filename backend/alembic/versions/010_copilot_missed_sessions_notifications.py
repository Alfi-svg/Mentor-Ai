"""Add missed_session and schedule_recovery notification types.

Revision ID: 010_copilot_missed_sessions
Revises: 009_expand_task_sync_status
Create Date: 2026-10-17 04:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "010_copilot_missed_sessions"
down_revision: str | None = "009_expand_task_sync_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_type;")
        op.create_check_constraint(
            "chk_notification_type",
            "notifications",
            "notification_type IN ('due_soon', 'due_now', 'overdue', 'upcoming_task', 'schedule_conflict', 'calendar_revoked', 'calendar_stale', 'action_required', 'action_failed', 'task_completed', 'missed_session', 'schedule_recovery')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notification_type;")
        op.create_check_constraint(
            "chk_notification_type",
            "notifications",
            "notification_type IN ('due_soon', 'due_now', 'overdue', 'upcoming_task', 'schedule_conflict', 'calendar_revoked', 'calendar_stale', 'action_required', 'action_failed', 'task_completed')",
        )
