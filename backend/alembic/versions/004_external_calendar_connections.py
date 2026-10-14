"""Create external_connections table for encrypted OAuth tokens and calendar links.

Revision ID: 004_external_calendar_connections
Revises: 003_task_constraints_and_archiving
Create Date: 2026-10-14 01:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "004_external_calendar_connections"
down_revision: str | None = "003_task_constraints_and_archiving"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cross-dialect JSON column type
JSON_TYPE = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    # 1. Create external_connections table
    op.create_table(
        "external_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=30),
            server_default="google_calendar",
            nullable=False,
        ),
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", JSON_TYPE, server_default="[]", nullable=False),
        sa.Column(
            "status",
            sa.String(length=25),
            server_default="connected",
            nullable=False,
        ),
        sa.Column("metadata_json", JSON_TYPE, server_default="{}", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('connected', 'expired', 'revoked', 'disconnected')",
            name="chk_connection_status",
        ),
        sa.CheckConstraint(
            "provider IN ('google_calendar', 'ical')",
            name="chk_connection_provider",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_connection"),
    )
    op.create_index(
        "idx_ext_conn_user_status",
        "external_connections",
        ["user_id", "status"],
    )

    # 2. Enable Row-Level Security for PostgreSQL
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
        op.execute("ALTER TABLE public.external_connections ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public'
                    AND tablename = 'external_connections'
                    AND policyname = 'external_connections_tenant_isolation'
                ) THEN
                    CREATE POLICY "external_connections_tenant_isolation"
                        ON public.external_connections
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
            'DROP POLICY IF EXISTS "external_connections_tenant_isolation" ON public.external_connections;'
        )
    op.drop_index("idx_ext_conn_user_status", table_name="external_connections")
    op.drop_table("external_connections")
