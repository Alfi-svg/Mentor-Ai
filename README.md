# Mentor AI

> **Your Goals. Your Plan. Your Next Move.**

A real, deployable personal scheduling and task-orchestration application built for university students and working professionals. Mentor AI translates natural-language instructions into conflict-free, time-blocked schedules using deterministic constraint-satisfaction algorithms, human-in-the-loop action verification, and the Model Context Protocol (MCP).

---

## 🛠 Prerequisites

Ensure the following runtimes are installed on your machine:
- **Python:** 3.12+ (or 3.11+)
- **Node.js:** 20.x+ (LTS)
- **npm:** 10.x+
- **Git**

---

## 📁 Monorepo Layout

```
mentor-ai/
├── backend/                         # FastAPI Application (Python 3.12+)
│   ├── alembic/                     # Database version migrations
│   │   ├── versions/                # 001_initial_schema.py, 002_row_level_security.py
│   │   └── env.py                   # Async migration runner (PostgreSQL + SQLite)
│   ├── app/
│   │   ├── api/v1/                  # Versioned API routes & endpoints
│   │   │   ├── endpoints/actions.py # Two-phase human approvals, confirm & verify
│   │   │   ├── endpoints/auth.py    # Signup, login, logout, me, preferences
│   │   │   ├── endpoints/chat.py    # Natural language chat assistant endpoint
│   │   │   ├── endpoints/health.py  # Truthful liveness & readiness probes
│   │   │   ├── endpoints/planner.py # Draft plan generation & explicit confirmation
│   │   │   ├── endpoints/schedule.py # Deterministic schedule generation & approval
│   │   │   ├── endpoints/tasks.py   # Task CRUD, filters, actions & archiving
│   │   │   └── router.py            # Aggregated v1 router
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings & safe CORS validation
│   │   │   ├── errors.py            # Consistent error response envelopes
│   │   │   ├── logging.py           # Structured logging foundation
│   │   │   └── security.py          # JWT claims validation & FastAPI auth dependencies
│   │   ├── db/
│   │   │   ├── base.py              # DeclarativeBase metadata
│   │   │   ├── session.py           # Async engine, sessionmaker & fallback provider
│   │   │   └── models/              # Profile, UserPreferences, Task, Schedule, Block, etc.
│   │   ├── schemas/                 # Pydantic v2 schemas
│   │   │   ├── action.py            # ActionResponse, Confirm & Verify schemas
│   │   │   ├── planner.py           # DraftPlan, PlanProposal, Confirm schemas
│   │   │   └── task.py              # TaskCreate, TaskUpdate, TaskResponse schemas
│   │   ├── services/
│   │   │   ├── action_service.py    # Staged actions, approvals & idempotency cache
│   │   │   ├── ai/                  # Provider-agnostic AI adapters (Gemini, Groq, Offline)
│   │   │   │   ├── base.py          # BaseLLMAdapter interface
│   │   │   │   ├── factory.py       # Resilient fallback orchestration
│   │   │   │   ├── gemini.py        # Google Gemini 1.5/2.0 Flash HTTP adapter
│   │   │   │   ├── groq.py          # Groq Llama 3.3 70B HTTP adapter
│   │   │   │   ├── models.py        # Context & parse result models
│   │   │   │   ├── offline.py       # Deterministic rule & heuristic parser
│   │   │   │   └── sanitizer.py     # Prompt injection defense & JSON auto-repair
│   │   │   ├── auth/                # Supabase GoTrue Auth service adapter
│   │   │   ├── mcp/                 # Official Python MCP SDK server implementation
│   │   │   │   └── server.py        # 8 typed tools, MCPServer instance & auth middleware
│   │   │   ├── planner_service.py   # Draft generation, clarification & preview engine
│   │   │   ├── scheduler/           # Pure deterministic interval engine & validator
│   │   │   └── task_service.py      # Task domain service, state transitions & audit trail
│   │   └── main.py                  # FastAPI application entrypoint & middleware
│   ├── mcp_server.py                # Standalone CLI runner for stdio and remote SSE MCP
│   ├── alembic.ini                  # Alembic CLI configuration
│   ├── pyproject.toml               # Tool configs (Ruff, Pytest, Mypy)
│   ├── requirements.txt             # Pinned production dependencies (mcp>=2.3.0)
│   ├── requirements-dev.txt         # Dev, testing, and linting dependencies
│   └── .env.example                 # Backend configuration placeholders
├── frontend/                        # Next.js 15 Web Application (TypeScript)
│   ├── app/
│   │   ├── layout.tsx               # Root layout & accessibility metadata
│   │   ├── page.tsx                 # Landing page & system architecture overview
│   │   └── globals.css              # Tailwind base styling
│   ├── components/                  # Reusable UI components
│   │   └── HealthStatusBadge.tsx    # Live backend health probe indicator
│   ├── lib/api.ts                   # Type-safe backend API fetch client
│   ├── package.json                 # Pinned dependencies & scripts
│   ├── tsconfig.json                # Strict TypeScript configuration
│   └── .env.example                 # Frontend client configuration
├── tests/                           # Multi-tier test suite
│   └── backend/                     # Pytest suite (77 tests, 100% pass)
│       ├── conftest.py              # TestClient fixtures, JWT tokens & isolated DB
│       ├── test_actions.py          # Action staging, approval workflow & idempotency
│       ├── test_ai_adapters.py      # Offline parser, Gemini/Groq mocks, timeouts & injection
│       ├── test_auth.py             # Signup, login, logout, token validation & expired claims
│       ├── test_cors.py             # Safe CORS origin validation tests
│       ├── test_data_isolation.py   # Multi-tenant data isolation & ownership verification
│       ├── test_errors.py           # Standardized error envelope tests
│       ├── test_health.py           # Truthful liveness & readiness probe assertions
│       ├── test_mcp_tools.py        # Protocol unit & integration tests for 8 MCP tools
│       ├── test_migrations.py       # Alembic migration upgrade & downgrade reversibility
│       ├── test_planner.py          # Draft plan generation, preview schedule & confirmation
│       ├── test_scheduler.py        # Deterministic solver, validator, intervals & persistence
│       └── test_tasks.py            # Task CRUD, filters, state transitions & validation
├── infra/                           # Operational scripts
│   ├── local-dev.sh                 # Unified / standalone development runner
│   └── README.md                    # Deployment runbook & zero-budget topology
├── docs/                            # Comprehensive approved engineering specifications
│   ├── PRD.md                       # Product Requirements Document
│   ├── ARCHITECTURE.md              # System Architecture & Component Deep-Dive
│   ├── DATABASE_DESIGN.md           # Database ER Diagram, Schema DDL & RLS Policies
│   ├── API_CONTRACT.md              # OpenAPI 3.1 Contract & Endpoint Specifications
│   ├── AI_AND_SCHEDULER.md          # Deterministic Scheduler & NLU Pipeline
│   ├── MCP_SPEC.md                  # FastMCP Server Specification (8 Typed Tools)
│   ├── THREAT_MODEL.md              # STRIDE Security Model & Defense-in-Depth
│   ├── DEPLOYMENT_PLAN.md           # Zero-Budget Free-Tier Matrix & Topology
│   ├── 12_DAY_PLAN.md               # 12-Day Implementation Roadmap
│   └── ACCEPTANCE_CRITERIA.md       # Master Acceptance Criteria & Verification Matrix
├── .github/workflows/ci.yml         # GitHub Actions CI for Lint, Type-Check & Build
├── .gitignore                       # Git ignore rules for node, python, secrets
└── README.md
```

---

## 🚀 Local Development Setup

The frontend and backend are completely decoupled and can run independently.

### 1. Backend Setup (FastAPI)

```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Create local environment file from template
cp .env.example .env

# Run development server with hot-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- **Interactive OpenAPI Documentation:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **Liveness Health Probe:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 2. Database Migrations (PostgreSQL & SQLite Fallback)

Migrations are managed via Alembic:
```bash
# Apply all migrations up to latest schema & RLS policies
alembic upgrade head

# Rollback one migration revision
alembic downgrade -1

# Rollback all migrations to clean base
alembic downgrade base
```
*Note: In development and test modes without live Supabase credentials configured, the backend automatically uses a local SQLite fallback (`sqlite+aiosqlite:///./mentor_ai_dev.db`). When Supabase credentials (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) are provided in `.env`, the engine connects directly to managed PostgreSQL with Row Level Security (RLS) enforcement.*

### 3. Frontend Setup (Next.js)

```bash
# Navigate to frontend directory in a separate terminal
cd frontend

# Install dependencies
npm install

# Create local environment file from template
cp .env.example .env.local

# Run Next.js development server
npm run dev
```
- **Web Application:** [http://localhost:3000](http://localhost:3000)

### 4. Unified Runner

You can also use the helper script from the repository root:
```bash
# Start both backend and frontend simultaneously
./infra/local-dev.sh all

# Or start only backend
./infra/local-dev.sh backend

# Or start only frontend
./infra/local-dev.sh frontend
```

---

## 🧪 Testing & Code Quality Commands

### Backend Commands
From `backend/` with active virtual environment:
```bash
# Run automated test suite
pytest ../tests/backend

# Run Ruff linter
ruff check .

# Run Ruff formatter check
ruff format --check .

# Run Mypy static type checking
mypy app
```

### Frontend Commands
From `frontend/`:
```bash
# Run Next.js ESLint
npm run lint

# Run TypeScript static type check
npm run type-check

# Run Next.js production build
npm run build
```

---

## 🔒 Safe CORS & Security Policy

- In development, the backend restricts cross-origin requests strictly to origins specified in `ALLOWED_ORIGINS` (`http://localhost:3000`, `http://127.0.0.1:3000`).
- In production, wildcard `*` origins are strictly prohibited by Pydantic configuration validation.
- All non-2xx responses return a standardized `ErrorResponse` envelope containing a correlation `trace_id` and timestamp. Server stack traces are never exposed in production responses.
- Passwords are never stored directly in the Mentor AI database; authentication is handled via Supabase GoTrue Auth with strict RS256/HS256 JWT claims validation.

---

## 🤖 AI Provider Configuration, Testing & Fallbacks

Mentor AI features a **provider-agnostic AI planning pipeline** that decouples natural language understanding from mathematical scheduling decisions.

### Free-Tier Provider Setup

1. **Deterministic Offline Parser (Default / $0.00 / Zero Network):**
   - Configured by default in `.env`:
     ```env
     AI_PROVIDER=offline
     ```
   - Uses a pure deterministic rule-and-regex engine with zero external network calls or billing requirements. 100% of automated tests run against this mode with zero API keys required.

2. **Google Gemini Flash Free Tier (Google AI Studio):**
   - Obtain a free API key from [Google AI Studio](https://aistudio.google.com/).
   - Add to `backend/.env`:
     ```env
     AI_PROVIDER=gemini
     GEMINI_API_KEY=your_actual_gemini_api_key
     GEMINI_MODEL=gemini-2.0-flash
     ```
   - Features structured JSON schema output and 15 Requests Per Minute (RPM) free limit.

3. **Groq Llama 3.3 70B Free Tier:**
   - Obtain a free API key from [Groq Console](https://console.groq.com/).
   - Add to `backend/.env`:
     ```env
     AI_PROVIDER=groq
     GROQ_API_KEY=gsk_your_actual_groq_api_key
     GROQ_MODEL=llama-3.3-70b-versatile
     ```

### Truthful Fallback & Traceability Guarantees

- **No Hallucinations:** If a task's duration or date is unspecified, the system **never invents durations or deadlines**. It sets `duration_minutes: null`, generates a concise `clarification_question`, and marks `requires_confirmation: false`.
- **Truthful Labeling:** When an external model times out, encounters a rate limit (HTTP 429), or has missing credentials, the system automatically falls back to `DeterministicOfflineAdapter` with explicit disclosure:
  `fallback_applied: true`, `parser_used: "deterministic_offline"`, and records the primary error in metadata.
- **Dry-Run Preview:** `POST /api/v1/planner/draft` runs a zero-mutation dry run through the Day 5 deterministic solver so the user can inspect their timeline before committing.
- **Two-Phase Confirmation:** Database writes and calendar mutations happen **only** when the user explicitly submits `POST /api/v1/planner/confirm`.

---

## 🔌 Model Context Protocol (MCP) & Safe Action Execution

Mentor AI exposes an official Model Context Protocol (MCP) server implemented with the Python MCP SDK (`mcp` v2.3.0). It enables external AI agents (e.g., Google Antigravity IDE, Claude Desktop, Cursor) to safely read user context, list and stage tasks, evaluate calendar availability, and generate conflict-free schedules without granting arbitrary code execution or unconstrained tool access.

### The 8 Approved Typed Tools

| Tool Name | Category | Side Effects | Description |
| :--- | :--- | :--- | :--- |
| `get_user_context` | Read-Only | None | Returns user timezone, working hours (`work_start_time`, `work_end_time`), buffer minutes, and pending task count. |
| `list_tasks` | Read-Only | None | Queries user backlog with optional `status`, `priority`, and bounded `limit` filters. |
| `create_task` | Safe Mutation | Database write | Creates a validated backlog task draft (`title`, `duration_minutes`, `priority`, `deadline`). |
| `update_task` | Safe Mutation | Database write | Updates task fields or transitions task lifecycle (`pending` -> `in_progress` -> `completed`). |
| `get_calendar_events` | Read-Only | None | Queries fixed commitments and existing calendar events within a time range. |
| `create_calendar_event` | Staged Action | **Zero external write** | Staged pending human review; returns `status: staged_pending_approval` and `requires_human_approval: true`. |
| `generate_schedule` | Algorithmic | None | Invokes Day 5 deterministic solver to generate a feasible schedule proposal without mutating database state. |
| `verify_action` | Read-Only | None | Truthfully probes whether a staged action has been executed and persisted. |

### Two-Phase Human Approval & Idempotency State Machine

1. **Staged Proposals (`staged_pending_approval`):** Consequential external actions (such as publishing calendar events) are **never executed directly** by AI agents. They are staged as `ActionExecutionRecord` entries in the approval inbox.
2. **Idempotency Protection:** Every staged mutation requires an `idempotency_key`. Rapid retries or duplicate LLM tool calls return the cached staging record without creating duplicate calendar slots or phantom tasks.
3. **User Confirmation Endpoint:** The user approves or rejects staged actions via `POST /api/v1/actions/{action_id}/confirm` (`action: "approve" | "reject"`).
4. **Truthful Post-Condition Verification:** `GET /api/v1/actions/{action_id}/verify` runs an independent read verification probe against the database or calendar provider. It returns `verified: false` until the entity is confirmed and persisted.

### Running the MCP Server

```bash
# 1. Standard I/O Transport (Local Agent CLI / Claude Desktop / Cursor / Antigravity)
python backend/mcp_server.py

# 2. Remote SSE Transport (Server-Sent Events)
MCP_TRANSPORT=sse MCP_PORT=8001 python backend/mcp_server.py

# 3. Via FastAPI Mount (Production / Remote)
# Mounted at /mcp/sse (SSE stream) and /mcp/messages/ (JSON-RPC POST)
# Protected by MCPAuthMiddleware (enforces JWT Bearer token in non-development environments)
```

### Tested MCP Host Environments
- **Google Antigravity IDE** (`stdio` transport via `python backend/mcp_server.py`)
- **Claude Desktop** (Configured in `claude_desktop_config.json`)
- **Cursor** (Configured in MCP server settings)

### ⚠️ Hackathon Architectural Clarification: MCP vs. Alexa
- **Alexa / Alexa+:** Amazon Echo devices require the **Alexa Skills Kit (ASK)** with HTTPS webhook endpoints dispatching Amazon Directive JSON payloads.
- **MCP:** An open JSON-RPC protocol over `stdio` or HTTP `sse` for developer tooling and agent orchestration.
- Having an MCP server does **not** equal native Alexa voice skill support; Mentor AI provides `/api/v1/chat/message` for external assistant webhooks and browser-native Web Speech API for voice.

---

## 🗓️ Google Calendar Integration & Action Verification

Mentor AI implements a real, production-ready calendar integration with Google Calendar API v3 and OAuth 2.0.

### 1. Minimal Least-Privilege Scopes
To guarantee zero unnecessary data exposure, Mentor AI strictly requests only:
- `https://www.googleapis.com/auth/calendar.events` — View and edit events on calendars the user owns.
- `openid` & `email` — Authenticate and verify account identity.
*Full calendar management scopes (`https://www.googleapis.com/auth/calendar`) and read-only scopes are rejected in favor of the precise event scope.*

### 2. Zero-Cost Test Boundary Adapter (`MockCalendarAdapter`)
When Google OAuth credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) are not provided in the environment:
- The system **never crashes and never falsely claims live connectivity**.
- `/api/v1/calendar/status` truthfully returns `"Not Connected (OAuth Credentials Not Configured)"`.
- The system automatically activates `MockCalendarAdapter` in test and development modes to allow complete end-to-end testing of event synchronization, conflict detection, token refresh, and action approval without incurring external API quotas or setup friction.

### 3. Server-Side Security & Token Encryption at Rest
- **Encrypted At Rest:** OAuth access tokens and refresh tokens are encrypted using AES-128-CBC / HMAC-SHA256 authenticated encryption (Fernet) via `CALENDAR_ENCRYPTION_KEY` before writing to `external_connections`. Plaintext tokens are never stored in the database.
- **CSRF State Verification:** OAuth initiation produces an HMAC-SHA256 signed `state` token embedding the user UUID and expiration timestamp. Callbacks with invalid signatures or expired timestamps are rejected with HTTP 403.
- **Automatic Token Refresh:** Expired access tokens are refreshed automatically using the stored refresh token when sync or event creation is requested. Revoked tokens immediately transition the connection record to `revoked`.

### 4. Two-Phase Human Approval for Calendar Mutations
- Creating external calendar events is treated as a consequential external side-effect.
- The AI planner and MCP tools only stage `create_calendar_event` actions in the approval inbox.
- Events are pushed to the external Google Calendar **only after the user explicitly submits approval** via `POST /api/v1/actions/{id}/confirm`.
- **Follow-up Read Verification:** Upon remote event creation, Mentor AI immediately performs an independent GET read check (`get_event`) against Google Calendar to verify persistence before reporting success.

---

## 💻 Next.js 15 Frontend Architecture & SaaS Dashboard

The frontend is built with Next.js 15 (App Router), React 19, TypeScript, and Tailwind CSS. It connects to the FastAPI backend using a typed API client (`frontend/lib/api-client.ts`) with zero client-side credential leakage and automated session expiration handling.

### The 10 Core Application Screens

1. **Accurate Landing Page (`/`):** Explains Mentor AI's value proposition, architectural pillars (deterministic solver, two-phase action approvals, Google Calendar sync, RLS), and backend liveness indicator.
2. **Authentication (`/login` & `/signup`):** Accessible tabbed forms with inline validation, minimum 8-character password enforcement, and secure JWT session handling.
3. **Workspace Dashboard (`/dashboard`):** Real, truthful metric cards (backlog tasks, today's scheduled blocks, pending action approvals, calendar connection status), today's timeline preview, and priority backlog.
4. **Natural-Language Command Center (`/planner`):** Text prompt interface with rich real-world examples, target date selection, timezone detection, and dry-run extraction.
5. **Interactive Plan Review Screen (`/planner`):** Displays extracted intent, explanation, parser disclosure (`gemini`, `groq`, or `deterministic_offline`), editable tasks table (custom durations and priorities), missing parameter alerts, and dry-run schedule preview before confirmation.
6. **Deterministic Schedule View (`/schedule`):** Day-by-day navigation, time blocks with visual categorization (fixed commitments, task allocations, breaks, buffers), collision alerts, and unscheduled task feedback.
7. **Task Backlog Management (`/tasks`):** Status filtering (`all`, `pending`, `completed`, `archived`), priority filtering (`P1`-`P4`), live text search, quick completion toggle, task creation, and editing modals.
8. **Calendar Connection & Settings (`/settings/calendar`):** Real connection status (`Connected`, `Disconnected`, or `OAuth Credentials Not Configured`), minimal scope transparency (`calendar.events`), manual sync trigger, and date-based conflict inspector.
9. **Action Approval Inbox (`/actions`):** Consequential external actions staged in `pending_approval` with detailed parameter breakdowns, consequence disclosures, and one-click Approve/Reject buttons.
10. **Audit & Verification History (`/actions`):** Complete immutable audit log of executed actions with on-demand post-condition verification probes (`GET /actions/{id}/verify`).

---

---

## 🛡️ Security & Quality Gate Audit (Day 10)

The entire platform underwent an exhaustive security and quality gate audit with zero budget consumption:
- **Test Suite:** 109 automated tests passing (104 backend tests in 4.05s, 5 frontend tests in 83ms).
- **Security Audit Test Suite:** 10 dedicated security tests in `tests/backend/test_security_audit.py` verifying IDOR isolation, token invalidation, health probe secret stripping, prompt injection sanitization, idempotency keys, and rate limiting.
- **Static Analysis & Screening:** 0 Bandit security vulnerabilities (`ruff check backend/app --select S`), 0 Mypy type issues across 60 source files, 0 ESLint warnings.
- **Frontend Quality:** Next.js production build cleanly compiles all 13 routes as static optimized pages with accessible ARIA controls and WCAG 2.1 AA compliant contrast.
- **Documentation:** Full audit logs and findings documented in [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md) and [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md).

---

## 🚀 Production Deployment & Free-Tier Architecture (Day 11)

Mentor AI is configured and verified for production deployment on zero-cost free tiers:
- **Frontend Hosting (Vercel Hobby):** Pre-rendered static pages + Edge CDN, zero sleep, automatic SSL, and strict security headers via [`frontend/vercel.json`](frontend/vercel.json).
- **Backend Hosting (Render Free / Container):** FastAPI deployed via [`render.yaml`](render.yaml) or non-root multi-stage [`backend/Dockerfile`](backend/Dockerfile), with truthful liveness (`/health`) and readiness (`/health/ready`) probes.
- **Database & Auth (Supabase Free Tier):** Dedicated PostgreSQL 15 with kernel-level Row Level Security (RLS) migrations managed via [`infra/run-migrations.sh`](infra/run-migrations.sh).
- **Cold-Start Handling:** `HealthStatusBadge` detects delays $> 2.5\text{s}$ and transparently informs users when the free-tier backend is spinning up (~50s).
- **Automated Verification:** [`infra/verify-production.py`](infra/verify-production.py) tests deployed endpoints for liveness, secret stripping, CORS preflights, 401 auth rejections, cross-user IDOR defense, and AI planning.
- **Rollback Runbooks:** Documented in [`docs/DEPLOYMENT_PLAN.md`](docs/DEPLOYMENT_PLAN.md) with 1-click Vercel rollback, Render commit redeploy, and Alembic database migration reversal.

---

## 🏁 Release Verification & Documentation Index (Day 12)

Mentor AI has completed its 12-day engineering plan. The platform has been verified against all PRD requirements and acceptance criteria, operating on 100% free-tier zero-budget infrastructure.

### Complete Documentation Suite
1. **[User Guide & Operator Manual (`docs/USER_GUIDE.md`)](docs/USER_GUIDE.md):** Complete guide for students and working professionals, workflows, natural language commands, and screen walkthroughs.
2. **[Production Deployment Guide (`docs/DEPLOYMENT_GUIDE.md`)](docs/DEPLOYMENT_GUIDE.md):** Step-by-step reproducible setup for Vercel, Render, Supabase, and Google Cloud OAuth.
3. **[Security Review & Quality Gate (`docs/SECURITY_REVIEW.md`)](docs/SECURITY_REVIEW.md):** Threat modeling, multi-tenant RLS, IDOR defense, and cryptographic token audits.
4. **[Comprehensive Test Report (`docs/TEST_REPORT.md`)](docs/TEST_REPORT.md):** 109 automated tests passing (104 backend, 5 frontend), 0 static type issues, 0 lint warnings.
5. **[Known Limitations & Free-Tier Constraints (`docs/KNOWN_LIMITATIONS.md`)](docs/KNOWN_LIMITATIONS.md):** Honest disclosure of Render cold starts, Supabase inactivity pauses, and API rate limits.
6. **[Release Verification Checklist (`docs/RELEASE_CHECKLIST.md`)](docs/RELEASE_CHECKLIST.md):** Formal sign-off checklist and master feature status matrix.

---

## 📅 12-Day Implementation Progress

- [x] **Day 1: Requirements, Architecture, Database Design, Threat Model & Acceptance Criteria**
- [x] **Day 2: Maintainable Monorepo Foundation, Health Endpoints, Tooling & CI**
- [x] **Day 3: Authentication, Migrations, Database Schema & Row-Level Security**
- [x] **Day 4: Task Management CRUD & API Validation**
- [x] **Day 5: Deterministic Scheduling Engine & Conflict Detection**
- [x] **Day 6: Natural-Language Parsing & AI Tool Calling**
- [x] **Day 7: MCP Server, Approval Workflow & Idempotency**
- [x] **Day 8: Real Calendar Integration & Action Verification**
- [x] **Day 9: Next.js Frontend & Full-Stack Integration**
- [x] **Day 10: Security Review, Automated Testing & Critical Bug Fixes**
- [x] **Day 11: Production Deployment, Environment Setup & Health Monitoring**
- [x] **Day 12: Live Production Verification, Documentation & Release Sign-Off**
