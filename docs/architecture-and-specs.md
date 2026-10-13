# Mentor AI — Comprehensive System Blueprint & Feasibility Assessment

**Version:** 1.0.0-PROD-SPEC  
**Author:** Software Architecture & Engineering Team  
**Supervision:** CS Student / Antigravity Orchestrator  
**Target Delivery Window:** 12 Days | **Budget Constraint:** $0.00 USD (Strict Zero-Budget)

---

## Executive Summary

**Mentor AI** is a production-oriented personal scheduling and task-orchestration system tailored for university students and working professionals. Unlike superficial hackathon prototypes or unbounded LLM chatbots, Mentor AI enforces **strict architectural separation between non-deterministic language understanding and deterministic scheduling algorithms**. 

The system leverages:
1. **Natural Language Understanding (NLU) & AI Tool Calling** to extract structured intents, tasks, and constraints from text or voice.
2. **Deterministic Constraint-Satisfaction Scheduling Engine** in pure Python to eliminate hallucinations, enforce hard calendar constraints, calculate buffers, and respect user working hours.
3. **Model Context Protocol (MCP)** server architecture exposing typed, validated tools with fine-grained access control and an explicit human-in-the-loop approval workflow for consequential mutations.
4. **Supabase PostgreSQL with Row-Level Security (RLS)** and **Supabase Auth** for multi-tenant data isolation.
5. **FastAPI Backend** and **Next.js (TypeScript + Tailwind CSS) Frontend** designed for modular monorepo maintainability.
6. **Strict Zero-Budget Strategy** utilizing perpetually free tiers (Gemini API Free Tier / Groq / Ollama, Supabase Free Tier, Vercel Hobby, Render/Koyeb/Local container) with 100% deterministic offline fallback modes for CI/CD and local development.

---

## 1. Requirements Specification

### 1.1 Product Purpose & Target Audience
- **Target Audience:** University students balancing classes, labs, assignments, and study sessions; and working professionals managing meetings, deep-work blocks, and project deliverables.
- **Value Proposition:** Transform unstructured natural language thoughts (e.g., *"Mentor, plan my day tomorrow. I have two classes, a team meeting, and an assignment that needs two hours"*) into an optimal, conflict-free, realistic time-blocked schedule with automated synchronization and verification.

### 1.2 Explicit Exclusions (Out of Scope)
- No What-If Simulations: No speculative alternate reality simulations.
- No Unsolicited "Life Coaching" or Generic Recommendations.
- No Mock / Fake Integrations: No simulated dummy buttons claiming to sync external tools. Every integration must either be a real, authenticated API call or transparently stated as not configured.
- No Unnecessary Microservices or Distributed Queues: Single modular monorepo. No Kafka, Redis clusters, or Kubernetes.

### 1.3 Functional Requirements (FR)
- **FR-01 (Authentication & Multi-Tenancy):** Email/password and OAuth authentication via Supabase Auth. Every database query, API route, and tool execution must enforce user identity verification.
- **FR-02 (Natural Language Understanding):** Accept text and voice transcripts; parse into typed structured objects (`TaskDraft`, `EventDraft`, `ScheduleIntent`) using schema validation.
- **FR-03 (Missing Information Clarification):** If user requests scheduling a task without specifying a required duration or deadline, the system prompts for missing parameters rather than fabricating assumptions.
- **FR-04 (Deterministic Scheduling):** A mathematical interval scheduler that places tasks into free time windows, respects fixed calendar events, avoids working-hour violations, and adds buffer times.
- **FR-05 (Conflict Detection & Reporting):** If an oversubscription occurs (e.g., 6 hours of tasks to fit into 3 hours of available time), the system detects the exact conflict and reports it with specific options (reschedule, shorten, drop).
- **FR-06 (Task Lifecycle Management):** Full CRUD for tasks: Create, Read, Update, Delete, Complete, Reschedule, Prioritize (`P1` Urgent/Important, `P2` Important, `P3` Normal, `P4` Low).
- **FR-07 (Calendar Integration):** Bi-directional or uni-directional sync with Google Calendar and universal read-only iCal (.ics) subscription feeds. Fixed events are immutable to the scheduler.
- **FR-08 (Action Approval & Execution):** Consequential mutations (e.g., modifying external calendar events, batch-rescheduling tasks, bulk deletion) require explicit user confirmation.
- **FR-09 (State Verification):** Every executed action runs post-condition checks (e.g., confirming the event ID exists on Google Calendar or the task record status is updated in PostgreSQL).
- **FR-10 (Model Context Protocol):** Expose core capabilities as standardized MCP tools so external agents or internal orchestrators can query context, generate schedules, and propose tasks.
- **FR-11 (Truthful Error Reporting):** Failure modes (rate limits, network timeout, auth expiry) must be communicated with exact root causes; never emit false positive confirmations.

### 1.4 Non-Functional Requirements (NFR)
- **NFR-01 (Performance):** Scheduling solver execution time <= 100ms for up to 100 tasks/events per day. API latency (excluding LLM inference) <= 200ms.
- **NFR-02 (Security):** Zero client-side API secret leakage. Supabase Row Level Security (RLS) on all user tables. Strict Pydantic input sanitization.
- **NFR-03 (Reliability & Offline Fallback):** When external LLM APIs fail or hit rate limits, the system provides a deterministic regex/rule-based parser mode for essential task creation and schedule generation.
- **NFR-04 (Accessibility & Responsiveness):** WCAG 2.1 AA compliant UI, keyboard navigation, high contrast support, full mobile responsiveness.

---

## 2. Architecture & Modular Monorepo Design

### Directory Structure
```
mentor-ai/
├── apps/
│   ├── web/                         # Next.js 15 (React 19, TypeScript, Tailwind CSS)
│   │   ├── app/
│   │   │   ├── (auth)/login, signup
│   │   │   ├── dashboard/           # Overview & Daily Schedule Timeline
│   │   │   ├── tasks/               # Task management & filtering
│   │   │   ├── calendar/            # Calendar view & sync settings
│   │   │   ├── chat/                # Natural language chat & voice assistant
│   │   │   ├── history/             # Action audit & verification history
│   │   │   └── settings/            # User preferences, working hours, API keys
│   │   ├── components/              # Accessible Radix/Tailwind components
│   │   ├── lib/                     # Supabase browser client, API fetchers
│   │   └── package.json
│   └── api/                         # FastAPI Backend Application (Python 3.12+)
│       ├── app/
│       │   ├── api/v1/              # Versioned API routes
│       │   ├── core/                # Config, security, database session, logging
│       │   ├── db/                  # SQLAlchemy 2.0 async models, Alembic migrations
│       │   ├── models/              # Pydantic v2 schemas & domain models
│       │   ├── services/            # Business logic
│       │   │   ├── scheduler/       # Pure deterministic interval scheduling engine
│       │   │   ├── ai/              # Provider-agnostic LLM adapter & fallback
│       │   │   ├── calendar/        # Google Calendar & iCal sync adapters
│       │   │   └── actions/         # Approval workflow & verification engine
│       │   └── mcp/                 # MCP Server (FastMCP / stdio & SSE transports)
│       ├── tests/                   # Pytest suite (unit, integration, scheduler, mcp)
│       ├── alembic/                 # Database migrations
│       ├── requirements.txt
│       └── Dockerfile
├── docs/                            # Architecture specs, user manuals, deployment runbooks
├── scripts/                         # Local development setup and DB seeding
├── .env.example
├── docker-compose.yml               # Optional local PostgreSQL + API testing
└── README.md
```

---

## 3. Database Schema & Row-Level Security (PostgreSQL / Supabase)

- **`profiles`:** Matches `auth.users.id`. Stores email, full name, timezone, timestamps.
- **`user_preferences`:** Stores `work_start_time`, `work_end_time`, `buffer_minutes`, `default_task_duration`, `max_focus_hours_per_day`, `available_days`, `auto_schedule_breaks`.
- **`tasks`:** Stores `title`, `description`, `status` (`pending`, `in_progress`, `completed`, `cancelled`), `priority` (`P1`-`P4`), `duration_minutes`, `deadline`, `energy_level`, `tags`.
- **`calendar_events`:** Stores `title`, `start_time`, `end_time`, `is_all_day`, `is_fixed`, `source` (`internal`, `google_calendar`, `ical`), `external_id`, `location`.
- **`schedules` & `schedule_blocks`:** Stores generated time-blocked days with allocated tasks, fixed events, breaks, and buffers.
- **`action_history` & `audit_logs`:** Stores two-phase approval records, payloads, status (`pending_approval`, `executing`, `completed`, `failed`), and verification outputs.
- **RLS:** All tables enforce `USING (auth.uid() = user_id)`.

---

## 4. API Contract (OpenAPI 3.1)

All endpoints reside at `/api/v1`:
- `GET /health` - Liveness & readiness probe
- `GET /auth/me` - Authenticated profile & preferences
- `PUT /preferences` - Update user scheduling rules
- `GET, POST /tasks` - List and create tasks
- `GET, PATCH, DELETE /tasks/{id}` - Fetch, update, delete task
- `GET, POST /calendar/events` - List and add fixed calendar commitments
- `POST /calendar/sync` - Trigger Google Calendar or iCal sync
- `POST /schedule/generate` - Run deterministic interval scheduler
- `GET /schedule/{date}` - Retrieve generated schedule blocks
- `POST /chat/message` - Natural language parser (voice/text)
- `GET /actions/pending` - Pending consequential mutations
- `POST /actions/{id}/confirm` - Human-in-the-loop approval or rejection
- `GET /actions/history` - Verification and execution audit log

---

## 5. MCP Tool Catalog

1. `get_user_context` (Safe, Read-only): User preferences, active timezone, high-priority tasks.
2. `list_tasks` (Safe, Read-only): Filtered task queries.
3. `create_task` (Safe, Mutation): Structured task creation.
4. `update_task` (Safe, Mutation): Task modifications.
5. `get_calendar_events` (Safe, Read-only): Retrieve fixed commitments in time window.
6. `create_calendar_event` (Consequential, Mutation): Calendar event addition with approval workflow.
7. `generate_schedule` (Safe, Algorithmic): Deterministic scheduling solver execution.
8. `verify_action` (Safe, Verification): Post-condition state checking.

---

## 6. Threat Model (STRIDE)

- **Spoofing:** Mitigated by cryptographic Supabase JWT verification on every route.
- **Tampering (IDOR):** Mitigated by database-level Row Level Security and mandatory user ID filtering in backend queries.
- **Repudiation:** Mitigated by immutable audit logs and action history entries.
- **Information Disclosure:** Mitigated by zero secrets in prompt context, strict CORS, and clean server-side configuration.
- **Denial of Service:** Mitigated by Pydantic bounds, solver runtime caps, and token bucket rate limits.
- **Elevation of Privilege:** Mitigated by non-executable LLM outputs, strict JSON validation, and human-in-the-loop approvals for external mutations.

---

## 7. Free-Tier Assessment (Zero-Budget Policy)

- **LLM:** Google Gemini API Free Tier (15 RPM, 1M TPM, free without credit card) + Groq Free Tier (Llama 3.3 70B) + 100% Deterministic Rule-Based Fallback.
- **Database & Auth:** Supabase Free Tier (500 MB DB, 50k MAU, RLS, free without credit card).
- **Frontend Hosting:** Vercel Hobby Free Tier (100 GB bandwidth, zero cost).
- **Backend Hosting:** Render Free Web Service / Fly.io / local container with zero cost.
- **External Calendar:** Google Calendar API Free Tier (1M requests/day) + universal iCal (.ics) reader.

---

## 8. 12-Day Roadmap Summary

- Day 1: Requirements, architecture, database design, threat model, acceptance criteria.
- Day 2: Repository, environment configuration, code quality tools, CI.
- Day 3: Authentication, migrations, database schema, row-level security.
- Day 4: Task CRUD and API validation.
- Day 5: Deterministic scheduling and conflict detection.
- Day 6: Natural-language parsing and AI tool calling.
- Day 7: MCP tools, approval workflow, idempotency, verification.
- Day 8: Real calendar integration and other feasible integrations.
- Day 9: Complete frontend and backend integration.
- Day 10: Security review, automated testing, and critical bug fixes.
- Day 11: Deployment, environment configuration, health checks, and monitoring.
- Day 12: Live production verification, documentation, recovery procedures, and release checklist.
