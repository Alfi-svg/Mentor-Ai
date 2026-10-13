# Infrastructure & Deployment Specifications — Mentor AI

This directory contains minimal, zero-cost operational scripts and deployment configuration. In accordance with project rules, Docker and Kubernetes are not introduced because lightweight standalone runtimes fit the zero-budget tier with minimal overhead.

---

## 1. Local Development (`infra/local-dev.sh`)

Run backend and frontend independently or simultaneously:
```bash
# Run both frontend and backend
./infra/local-dev.sh all

# Run FastAPI backend only (port 8000)
./infra/local-dev.sh backend

# Run Next.js frontend only (port 3000)
./infra/local-dev.sh frontend
```

---

## 2. Cloud Deployment Topology (Zero-Budget Tier)

1. **Frontend (Vercel Hobby Tier):**
   - Connect GitHub repository `frontend/` directory.
   - Build command: `npm run build`
   - Output directory: `.next`
   - Environment variables: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

2. **Backend (Render Free Web Service / Fly.io):**
   - Connect GitHub repository `backend/` directory.
   - Environment: Python 3.12+
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/v1/health`
   - Environment variables: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ALLOWED_ORIGINS`, `GEMINI_API_KEY`.
