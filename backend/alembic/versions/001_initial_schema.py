"""Initial schema for Mentor AI entities.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Profiles
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_profiles_email", "profiles", ["email"], unique=True)

    # 2. User Preferences
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "work_start_time", sa.String(length=8), server_default="09:00:00", nullable=False
        ),
        sa.Column("work_end_time", sa.String(length=8), server_default="18:00:00", nullable=False),
        sa.Column("buffer_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("default_task_duration", sa.Integer(), server_default="45", nullable=False),
        sa.Column("max_focus_hours_per_day", sa.Integer(), server_default="8", nullable=False),
        sa.Column("available_days", sa.JSON(), nullable=False),
        sa.Column("auto_schedule_breaks", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "buffer_minutes >= 0 AND buffer_minutes <= 60", name="chk_buffer_minutes"
        ),
        sa.CheckConstraint(
            "default_task_duration > 0 AND default_task_duration <= 480",
            name="chk_default_task_duration",
        ),
        sa.CheckConstraint(
            "max_focus_hours_per_day > 0 AND max_focus_hours_per_day <= 16",
            name="chk_max_focus_hours",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("idx_user_preferences_user_id", "user_preferences", ["user_id"])

    # 3. Tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(length=5), server_default="P3", nullable=False),
        sa.Column("duration_minutes", sa.Integer(), server_default="45", nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("energy_level", sa.String(length=10), server_default="medium", nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(title) > 0", name="chk_task_title_not_empty"),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')", name="chk_task_status"
        ),
        sa.CheckConstraint("priority IN ('P1', 'P2', 'P3', 'P4')", name="chk_task_priority"),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 720", name="chk_task_duration"
        ),
        sa.CheckConstraint("energy_level IN ('high', 'medium', 'low')", name="chk_task_energy"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tasks_user_status", "tasks", ["user_id", "status"])
    op.create_index("idx_tasks_user_deadline", "tasks", ["user_id", "deadline"])

    # 4. Calendar Events
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_all_day", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_fixed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("source", sa.String(length=30), server_default="internal", nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_time > start_time", name="chk_event_end_after_start"),
        sa.CheckConstraint(
            "source IN ('internal', 'google_calendar', 'ical')", name="chk_event_source"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cal_events_user_time", "calendar_events", ["user_id", "start_time", "end_time"]
    )
    op.create_index("idx_cal_events_external_id", "calendar_events", ["external_id"])

    # 5. Schedules
    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="accepted", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'accepted', 'superseded')", name="chk_schedule_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_schedules_user_date", "schedules", ["user_id", "schedule_date"])

    # 6. Schedule Blocks
    op.create_table(
        "schedule_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("calendar_event_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("block_type", sa.String(length=20), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("end_time > start_time", name="chk_block_end_after_start"),
        sa.CheckConstraint(
            "block_type IN ('task', 'fixed_event', 'break', 'buffer')", name="chk_block_type"
        ),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["calendar_event_id"], ["calendar_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_blocks_schedule_id", "schedule_blocks", ["schedule_id"])
    op.create_index("idx_blocks_user_time", "schedule_blocks", ["user_id", "start_time"])

    # 7. Action History
    op.create_table(
        "action_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "status", sa.String(length=25), server_default="pending_approval", nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("verification_result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'executing', 'completed', 'failed', 'rejected')",
            name="chk_action_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_actions_user_status", "action_history", ["user_id", "status"])
    op.create_index("idx_actions_idempotency", "action_history", ["user_id", "idempotency_key"])

    # 8. Audit Logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_logs_user_time", "audit_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("action_history")
    op.drop_table("schedule_blocks")
    op.drop_table("schedules")
    op.drop_table("calendar_events")
    op.drop_table("tasks")
    op.drop_table("user_preferences")
    op.drop_table("profiles")
