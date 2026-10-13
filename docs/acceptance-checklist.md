# Mentor AI — Acceptance Checklist & Test Strategy

**Project Quality Standard:** Production-grade MVP with automated verification  
**Release Criteria:** Zero unverified features, zero mock masquerading, 100% passing tests

---

## 1. Acceptance Checklist by Module

### Module 1: Authentication & User Profiles
- [ ] User can sign up and sign in using Supabase Auth (email/password).
- [ ] User profile and scheduling preferences are automatically created upon initial signup.
- [ ] User can update working hours, default buffer, and focus limits.
- [ ] Requests without valid Bearer tokens are rejected with HTTP 401 Unauthorized.
- [ ] User A cannot view or update User B's profile (HTTP 403 / 404).

### Module 2: Task Lifecycle & Data Validation
- [ ] User can create, list, update, and delete tasks.
- [ ] Invalid durations (e.g. `<= 0` or `> 720` minutes) are rejected with HTTP 422 Unprocessable Entity.
- [ ] Priority validation ensures only `P1`, `P2`, `P3`, `P4` are accepted.
- [ ] Task completion updates the task status and sets completion timestamps.
- [ ] Cross-tenant access attempts return 404; database RLS verifies isolation.

### Module 3: Deterministic Scheduling Engine
- [ ] Engine schedules tasks within user's configured working hours (e.g. 09:00 - 18:00).
- [ ] Fixed calendar events are treated as hard barriers and never overwritten or split.
- [ ] Configured buffers (e.g. 15 minutes) are enforced before and after tasks/events.
- [ ] Higher priority tasks (`P1`, `P2`) are scheduled before lower priority ones.
- [ ] If available time is insufficient, engine detects oversubscription, flags status `conflict_detected`, leaves commitments intact, and lists unscheduled tasks.
- [ ] Solver executes in `< 100ms` for a typical daily load.

### Module 4: Natural Language Understanding & AI Orchestration
- [ ] User instruction (e.g. *"Plan my day tomorrow. I have 2 classes and need 2 hours for physics"*) produces valid structured output.
- [ ] Missing critical information (e.g. task without duration or deadline) triggers a clarification question rather than a hallucinated assumption.
- [ ] Provider adapter supports Google Gemini API free tier and Groq free tier.
- [ ] Deterministic fallback parser functions 100% offline without network or API keys.
- [ ] Rate limits and network timeouts fail gracefully with clear explanations.

### Module 5: Model Context Protocol (MCP) Server
- [ ] FastMCP server initializes with all 8 core tools (`get_user_context`, `list_tasks`, `create_task`, `update_task`, `get_calendar_events`, `create_calendar_event`, `generate_schedule`, `verify_action`).
- [ ] Tool input schemas strictly validate inputs with typed JSON schemas.
- [ ] Private tools require session authentication.
- [ ] Consequential tools return a staged action ID awaiting user approval.

### Module 6: Action Approval & Verification
- [ ] Consequential actions (e.g. external calendar creation, batch reschedule) are queued in `action_history` with status `pending_approval`.
- [ ] Unapproved actions cannot execute automatically.
- [ ] Upon user approval, action executes and runs state verification (checks database or external API).
- [ ] Action execution history provides a full audit trail.
- [ ] If an action fails, the system reports the exact reason and never falsely reports success.

### Module 7: Frontend Interface & Accessibility
- [ ] Clean, professional responsive dashboard with daily timeline view.
- [ ] Interactive task management board (filter by priority/status).
- [ ] Natural language chat interface with optional Web Speech API voice input.
- [ ] Visible pending approvals modal with clear diff of proposed changes.
- [ ] Accessible components (keyboard navigable, WCAG 2.1 AA compliant).
- [ ] Informative empty, loading, success, and error states.

### Module 8: Deployment & Operational Readiness
- [ ] Live deployment accessible over HTTPS with zero console errors.
- [ ] Health probe `/api/v1/health` returns status `healthy`.
- [ ] Zero API keys exposed in browser source bundles.
- [ ] Complete documentation: setup guide, `.env.example`, migration instructions.

---

## 2. Multi-Tier Testing Strategy

```
          / \
         / E2E \       Playwright / Manual End-to-End User Journeys
        /-------\
       /  API    \     FastAPI TestClient + Auth & DB Integration
      /-----------\
     / Unit Tests  \   Pytest: Deterministic Scheduler & Interval Math (100% coverage)
    /---------------\
```

1. **Unit Tests (Scheduler & Logic):**
   - Interval mathematics and collision checks.
   - Buffer insertion logic and working hour boundary handling.
   - Pydantic schema validation.
2. **Integration Tests (API & Database):**
   - Route authorization and multi-tenant RLS checks.
   - Task CRUD lifecycle.
   - Action staging and state verification.
   - Deterministic offline fallback mode.
3. **MCP Tool Tests:**
   - JSON-RPC protocol compliance and error handling.
