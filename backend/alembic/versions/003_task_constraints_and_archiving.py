"""Add task constraints and archiving fields.

Revision ID: 003_task_constraints_and_archiving
Revises: 002_row_level_security
Create Date: 2026-10-14 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_task_constraints_and_archiving"
down_revision: str | None = "002_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add constraints JSON column with empty object default
    op.add_column(
        "tasks",
        sa.Column("constraints", sa.JSON(), server_default="{}", nullable=False),
    )
    # 2. Add is_archived boolean column with false default
    op.add_column(
        "tasks",
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
    )
    # 3. Create index for efficient filtering by user and archive status
    op.create_index("idx_tasks_user_archived", "tasks", ["user_id", "is_archived"])


def downgrade() -> None:
    op.drop_index("idx_tasks_user_archived", table_name="tasks")
    op.drop_column("tasks", "is_archived")
    op.drop_column("tasks", "constraints")
