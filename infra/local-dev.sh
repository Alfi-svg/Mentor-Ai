#!/usr/bin/env bash
# ==============================================================================
# Mentor AI — Local Development Runner Script
# Usage:
#   ./infra/local-dev.sh backend   -> Starts FastAPI backend on port 8000
#   ./infra/local-dev.sh frontend  -> Starts Next.js frontend on port 3000
#   ./infra/local-dev.sh all       -> Starts both in parallel
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

run_backend() {
    echo "==> [Mentor AI] Starting FastAPI backend..."
    cd "${ROOT_DIR}/backend"
    if [ ! -d ".venv" ]; then
        echo "--> Creating Python virtual environment in backend/.venv..."
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "--> Installing backend dependencies..."
    pip install -q -r requirements-dev.txt
    echo "--> Running FastAPI with hot-reload on http://localhost:8000..."
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

run_frontend() {
    echo "==> [Mentor AI] Starting Next.js frontend..."
    cd "${ROOT_DIR}/frontend"
    if [ ! -d "node_modules" ]; then
        echo "--> Installing frontend dependencies with npm..."
        npm install
    fi
    echo "--> Running Next.js on http://localhost:3000..."
    npm run dev
}

TARGET="${1:-all}"

case "${TARGET}" in
    backend)
        run_backend
        ;;
    frontend)
        run_frontend
        ;;
    all)
        echo "==> [Mentor AI] Starting both backend and frontend..."
        run_backend &
        BACKEND_PID=$!
        run_frontend &
        FRONTEND_PID=$!
        trap 'kill ${BACKEND_PID} ${FRONTEND_PID} 2>/dev/null || true' INT TERM
        wait
        ;;
    *)
        echo "Usage: $0 [backend|frontend|all]"
        exit 1
        ;;
esac
