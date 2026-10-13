"""Enable PostgreSQL Row Level Security (RLS) policies.

Revision ID: 002_row_level_security
Revises: 001_initial_schema
Create Date: 2026-10-14 00:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "002_row_level_security"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES_WITH_USER_ID = [
    "user_preferences",
    "tasks",
    "calendar_events",
    "schedules",
    "schedule_blocks",
    "action_history",
    "audit_logs",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # RLS is PostgreSQL-specific; SQLite uses application-level ownership filtering
        return

    # Enable RLS on profiles (isolated by primary key id = auth.uid())
    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'profiles_tenant_isolation'
            ) THEN
                CREATE POLICY profiles_tenant_isolation ON profiles
                FOR ALL USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
            END IF;
        END $$;
        """
    )

    # Enable RLS on all child tables (isolated by user_id = auth.uid())
    for table in TABLES_WITH_USER_ID:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE tablename = '{table}' AND policyname = '{table}_tenant_isolation'
                ) THEN
                    CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP POLICY IF EXISTS profiles_tenant_isolation ON profiles;")
    op.execute("ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;")

    for table in TABLES_WITH_USER_ID:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
