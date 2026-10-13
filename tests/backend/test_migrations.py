"""Tests verifying Alembic database migrations."""

import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from app.db.session import get_database_url


def test_alembic_migrations_upgrade_and_downgrade() -> None:
    """Verify that alembic upgrade head and downgrade base execute without error."""
    backend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    )
    ini_path = os.path.join(backend_dir, "alembic.ini")
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

    # 1. Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # 2. Inspect database schema using SQLAlchemy inspector with sync connection
    db_url = get_database_url()
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    sync_engine = create_engine(sync_url)
    try:
        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()

        required_tables = [
            "profiles",
            "user_preferences",
            "tasks",
            "calendar_events",
            "schedules",
            "schedule_blocks",
            "action_history",
            "audit_logs",
            "external_connections",
        ]
        for table in required_tables:
            assert (
                table in tables
            ), f"Expected table {table} was not created by migration"

        # 3. Test downgrade reversibility
        command.downgrade(alembic_cfg, "base")

        inspector = inspect(sync_engine)
        tables_after_downgrade = inspector.get_table_names()
        for table in required_tables:
            assert (
                table not in tables_after_downgrade
            ), f"Table {table} was not removed after downgrade"

        # 4. Re-apply upgrade so test database remains in head state
        command.upgrade(alembic_cfg, "head")
    finally:
        sync_engine.dispose()
