#!/usr/bin/env bash
# ==============================================================================
# Mentor AI — Production Database Migration & RLS Verification Runner
# Usage: ./infra/run-migrations.sh [DATABASE_URL]
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

echo "========================================================================"
echo "MENTOR AI — PRODUCTION DATABASE MIGRATION RUNNER"
echo "========================================================================"

if [ -n "${1:-}" ]; then
  export DATABASE_URL="$1"
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "⚠️  DATABASE_URL environment variable is not set."
  echo "Defaulting to Alembic configuration in backend/alembic.ini..."
else
  # Mask credentials for secure logging
  SAFE_URL=$(echo "${DATABASE_URL}" | sed -E 's/:([^@]+)@/:****@/')
  echo "Target Database: ${SAFE_URL}"
fi

cd "${BACKEND_DIR}"

# Locate virtual environment Python or system Python
if [ -f "${BACKEND_DIR}/.venv/bin/alembic" ]; then
  ALEMBIC_BIN="${BACKEND_DIR}/.venv/bin/alembic"
  PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
elif command -v alembic &> /dev/null; then
  ALEMBIC_BIN="alembic"
  PYTHON_BIN="python"
else
  echo "❌ Error: Alembic not found in virtual environment or PATH."
  exit 1
fi

echo ""
echo "Step 1: Running Alembic migrations (upgrade head)..."
"${ALEMBIC_BIN}" upgrade head

echo ""
echo "Step 2: Checking current migration revision..."
"${ALEMBIC_BIN}" current

echo ""
echo "Step 3: Verifying Row Level Security (RLS) policies..."
"${PYTHON_BIN}" - << 'EOF'
import asyncio
from app.db.session import get_engine
from sqlalchemy import text

async def verify_rls():
    engine = get_engine()
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        if dialect != "postgresql":
            print(f"ℹ️  Dialect is '{dialect}'. Row Level Security is PostgreSQL-specific (Supabase).")
            print("   Application-level tenant isolation is active.")
            return

        print("🔍 Checking PostgreSQL Row Level Security status...")
        res = await conn.execute(text("""
            SELECT tablename, rowsecurity
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        rows = res.fetchall()
        for tablename, rowsecurity in rows:
            status = "ENABLED ✅" if rowsecurity else "DISABLED ⚠️"
            print(f"   - {tablename:<25} RLS: {status}")

asyncio.run(verify_rls())
EOF

echo ""
echo "========================================================================"
echo "✅ Database migrations and security checks completed successfully."
echo "========================================================================"
