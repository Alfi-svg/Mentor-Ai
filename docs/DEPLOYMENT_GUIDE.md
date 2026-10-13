# Mentor AI — Production Deployment & Operator Guide

**Version:** 1.0.0-PROD  
**Target Platform:** Zero-Cost Cloud Infrastructure (Vercel + Render + Supabase)  
**Budget:** $0.00 USD (Zero Budget)

---

## 1. System Requirements & Prerequisites

Ensure the following runtimes and accounts are available before starting:
- **Local Runtimes:** Python 3.12+ (or 3.11+), Node.js 20.x+ (LTS), npm 10.x+, Git.
- **Cloud Accounts (All 100% Free Tiers, No Credit Cards Required):**
  - [Supabase](https://supabase.com/) — PostgreSQL 15 + GoTrue Authentication.
  - [Render](https://render.com/) — Free Python Web Service (512MB RAM, 750 hrs/month).
  - [Vercel](https://vercel.com/) — Next.js Hobby Tier (100GB bandwidth, Edge CDN).
  - [Google AI Studio](https://aistudio.google.com/) — Gemini 2.0 Flash API Key (15 RPM free).
  - [Google Cloud Console](https://console.cloud.google.com/) — Calendar API v3 in Testing Mode.

---

## 2. Local Development Setup (Zero-Cost Offline Mode)

Mentor AI is 100% functional offline without any cloud accounts or API keys:

```bash
# 1. Clone repository
git clone <repository-url>
cd mentor-ai

# 2. Setup backend virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Run database migrations on local SQLite fallback
alembic upgrade head

# 4. Run full test suite (104 backend tests)
pytest tests/backend/ -v

# 5. Setup frontend dependencies
cd ../frontend
npm install
npm run build
npm test

# 6. Run both services simultaneously using the local development script
cd ..
./infra/local-dev.sh all
```
- Backend API is available at `http://localhost:8000/api/v1`
- Next.js Dashboard is available at `http://localhost:3000`

---

## 3. Production Deployment Walkthrough

### Step 1: Initialize Supabase (PostgreSQL & Auth)
1. In the Supabase Dashboard, create a new free project named `mentor-ai-prod`.
2. Under **Project Settings -> Database**:
   - Locate the **Connection String** (Transaction Pooler, port 6543).
   - Format: `postgresql+asyncpg://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres?ssl=require`
3. Under **Authentication -> URL Configuration**:
   - Set **Site URL** to `https://mentor-ai.vercel.app`.
   - Add Redirect URLs: `https://mentor-ai.vercel.app/**`, `http://localhost:3000/**`.
4. Apply migrations and verify Row Level Security:
   ```bash
   ./infra/run-migrations.sh "<your-supabase-connection-string>"
   ```

### Step 2: Deploy Backend to Render (Free Web Service)
1. In the Render Dashboard, click **New -> Blueprint**.
2. Select your repository. Render automatically reads [`render.yaml`](../render.yaml).
3. Fill in the sensitive environment variables in the Render dashboard:
   - `DATABASE_URL`: Your Supabase AsyncPG connection string.
   - `SUPABASE_URL`: `https://<ref>.supabase.co`.
   - `SUPABASE_ANON_KEY`: Your Supabase public key.
   - `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key.
   - `GEMINI_API_KEY`: Your Google AI Studio API key.
   - `ALLOWED_ORIGINS`: `https://mentor-ai.vercel.app,http://localhost:3000`.
4. Deploy the service. Note the backend URL: `https://mentor-ai-api.onrender.com`.

### Step 3: Deploy Frontend to Vercel (Hobby Tier)
1. In the Vercel Dashboard, click **Add New -> Project**.
2. Select your repository. Set **Root Directory** to `frontend`.
3. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL`: `https://mentor-ai-api.onrender.com/api/v1`
   - `NEXT_PUBLIC_SUPABASE_URL`: `https://<ref>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`: `<your-supabase-anon-key>`
4. Click **Deploy**. Vercel compiles all 13 static routes and issues automatic SSL.

### Step 4: Configure Google Calendar OAuth (Testing Mode)
1. In [Google Cloud Console](https://console.cloud.google.com/):
   - Enable **Google Calendar API v3**.
   - Configure **OAuth Consent Screen** in "Testing" mode (up to 100 test user emails).
   - Under **Credentials -> OAuth 2.0 Client IDs**:
     - Authorized JavaScript Origins: `https://mentor-ai.vercel.app`
     - Authorized Redirect URIs: `https://mentor-ai-api.onrender.com/api/v1/calendar/callback`
2. Update `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in Render.

---

## 4. Production Sanity Verification

After deploying, run the automated verification suite:

```bash
python infra/verify-production.py \
  --api-url https://mentor-ai-api.onrender.com/api/v1 \
  --frontend-url https://mentor-ai.vercel.app
```

The suite validates:
- Liveness (`/health`) and Readiness (`/health/ready`) probes.
- Zero secret reflection in health checks.
- Security headers (`nosniff`, `DENY`, `HSTS`, `Referrer-Policy`).
- CORS preflights for production origins.
- 401 Unauthorized rejection on protected endpoints.
- User registration and multi-tenant IDOR protection (User B gets 404 accessing User A's task).
- Natural language plan extraction and deterministic scheduling.
- Zero server keys in the frontend bundle.

---

## 5. Rollback & Disaster Recovery Procedures

### 5.1 Frontend Instant Rollback
- Open Vercel Dashboard -> **Deployments**.
- Locate the previous stable deployment -> Click `...` -> **Instant Rollback**.
- Downtime: 0 seconds.

### 5.2 Backend Rollback
- Open Render Dashboard -> **Deploys**.
- Select the last stable deployment -> Click **Rollback to this deploy**.
- Container activates in $< 60\text{ seconds}$.

### 5.3 Database Rollback & Schema Recovery
- **Revert single migration:**
  ```bash
  DATABASE_URL="<prod-url>" alembic downgrade -1
  ```
- **Disaster Recovery:**
  If the Supabase project is corrupted or paused, create a new project in $< 2\text{ minutes}$ and run:
  ```bash
  ./infra/run-migrations.sh "<new-prod-url>"
  ```
  All tables, foreign keys, and RLS policies are recreated automatically.
