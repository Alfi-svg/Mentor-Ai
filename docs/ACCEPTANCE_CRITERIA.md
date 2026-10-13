# Master Acceptance Criteria & Verification Matrix — Mentor AI

**Standard:** Given-When-Then Specification by Example  
**Zero-Defect Policy:** No feature is considered complete until verified against these test specifications.

---

## 1. Concrete Behavioral Scenarios

### Scenario 1: Natural Language Plan Generation with Clean Feasibility
- **Given** an authenticated student with configured working hours 09:00 to 18:00, a 15-minute buffer preference, and an existing calendar lecture from 10:00 to 11:30.
- **When** the student submits: *"Plan my day tomorrow. I have an operating systems lab that needs 2 hours."*
- **Then:**
  1. The AI engine extracts a task `Operating Systems Lab` with `duration_minutes: 120`.
  2. The deterministic solver identifies available intervals: `[09:00, 10:00 - 15m buffer]` (45m gap) and `[11:30 + 15m buffer, 18:00]` (375m gap).
  3. The solver places the 120m lab in the contiguous afternoon window (e.g. 11:45 to 13:45).
  4. The returned schedule status is `feasible`.
  5. The existing lecture is untouched and buffered by 15 minutes.

### Scenario 2: Missing Information Triggers Clarification (No Hallucinations)
- **Given** an authenticated user.
- **When** the user inputs: *"Mentor, schedule my physics homework for tomorrow."*
- **Then:**
  1. The NLU parser recognizes that the task title is `Physics homework`, but `duration_minutes` is missing.
  2. The system **does not fabricate** an arbitrary duration.
  3. The API responds with `intent: "clarification_needed"` and `clarification_question: "How much time do you anticipate needing for your physics homework?"`.
  4. Zero tasks or schedule blocks are persisted until the user responds with the required duration.

### Scenario 3: Overbooking & Conflict Detection
- **Given** an authenticated user with only 90 minutes of total available free time remaining before the end of the workday (18:00).
- **When** the user requests: *"Schedule a 3-hour deep work coding session today."*
- **Then:**
  1. The deterministic scheduler computes that required duration ($180\text{ min}$) exceeds maximum contiguous free interval ($90\text{ min}$).
  2. The schedule status is flagged as `conflict_detected`.
  3. The response details: `required_minutes: 180`, `max_available_gap: 90`.
  4. Suggested actions are provided: `["Shorten task duration", "Schedule on next available day", "Reschedule lower-priority tasks"]`.
  5. No fixed commitments are moved or modified.

### Scenario 4: Dynamic Re-Scheduling After Deadline Modification
- **Given** a generated schedule with 3 tasks: Task A (P3, 60m), Task B (P2, 60m), Task C (P1, 60m).
- **When** the user edits Task B's priority to `P1` and sets a deadline 2 hours earlier.
- **Then:**
  1. `PATCH /api/v1/tasks/{id}` updates the task record in Supabase PostgreSQL.
  2. The user requests schedule regeneration via `POST /api/v1/schedule/generate`.
  3. The deterministic scheduler reprioritizes Task B, placing it in an earlier morning focus slot ahead of lower-priority tasks.
  4. The UI timeline updates to reflect the new optimal schedule.

### Scenario 5: Two-Phase Approval for Consequential External Actions
- **Given** an authenticated user with Google Calendar sync enabled.
- **When** the user instructs: *"Schedule a 1-hour team sync on my Google Calendar for Friday at 3pm."*
- **Then:**
  1. The system creates a staged record in `action_history` with `status: "pending_approval"`, `action_type: "create_calendar_event"`, and a unique `idempotency_key`.
  2. The Google Calendar API is **not invoked** at this stage.
  3. The web dashboard renders an **Action Approval Banner** with exact proposed parameters.
  4. When the user clicks **[Approve]**, `POST /api/v1/actions/{id}/confirm` is sent.
  5. The backend executes the Google Calendar API call with the idempotency key.
  6. The `VerificationService` queries Google Calendar to verify the event exists.
  7. The action status transitions to `completed`, and verified details are saved.

### Scenario 6: Truthful Reporting on Integration Failures
- **Given** a staged action to update an external calendar where the user's OAuth token has expired.
- **When** the user confirms the action.
- **Then:**
  1. The Google Calendar API call returns HTTP 401 Unauthorized.
  2. The backend transitions `action_history.status` to `failed`.
  3. `error_message` records: `"Google Calendar authorization expired. Please reconnect your account."`
  4. The UI displays an explicit error message prompting re-authentication.
  5. The system **never** marks the action as succeeded or fakes a success confirmation.

### Scenario 7: Multi-Tenant Security & Row-Level Security Isolation
- **Given** User A (UUID `aaa-111`) and User B (UUID `bbb-222`) with active accounts.
- **When** User A attempts to read or mutate User B's task: `GET /api/v1/tasks/bbb-task-uuid` or `DELETE /api/v1/tasks/bbb-task-uuid`.
- **Then:**
  1. The API endpoint checks the authenticated JWT (`sub = aaa-111`).
  2. The SQLAlchemy query automatically scopes by `user_id == 'aaa-111'`.
  3. The database Row-Level Security policy `USING (auth.uid() = user_id)` returns zero rows.
  4. The API returns HTTP 404 Not Found.
  5. User A cannot view, modify, or infer the existence of User B's data.

### Scenario 8: Zero-Cost Offline Fallback Mode
- **Given** an environment without internet access or valid `GEMINI_API_KEY` (e.g., automated CI test runner).
- **When** `POST /api/v1/chat/message` is invoked in `AI_PROVIDER=offline` mode with input: *"Add task CS301 lab duration 90 minutes priority P1"*.
- **Then:**
  1. The deterministic regex parser extracts: title `CS301 lab`, duration `90`, priority `P1`.
  2. The task is created via the standard validation pipeline.
  3. Zero external API calls are made, incurring $0.00 cost with 100% test pass rate.

### Scenario 9: Model Context Protocol (MCP) Tool Calling
- **Given** an external MCP agent connected to the Mentor AI FastMCP server over `stdio` or `sse`.
- **When** the agent invokes tool `generate_schedule` with argument `{"target_date": "2026-10-14"}`.
- **Then:**
  1. The MCP server validates the JSON schema of the input.
  2. The request is routed to the Python deterministic scheduling engine.
  3. A compliant JSON-RPC response is returned containing the schedule blocks and feasibility status.

---

## 2. Release Sign-Off Checklist (Definition of Done)

- [ ] All 10 architectural specification documents completed and approved.
- [ ] No what-if simulations, personal recommendations, or fake integrations present in code.
- [ ] Supabase Auth and PostgreSQL RLS verified with multi-tenant isolation tests.
- [ ] Deterministic interval scheduling engine passes 100% of unit tests.
- [ ] Natural language parser validates against Pydantic `DraftPlan` schema with clarification triggers.
- [ ] Two-phase action approval and post-condition state verification proven end-to-end.
- [ ] MCP Server implements all 8 typed tools with validated input/output schemas.
- [ ] Frontend interface is responsive, accessible (WCAG 2.1 AA), and displays live schedule timelines.
- [ ] Health endpoints (`/api/v1/health` and `/api/v1/health/ready`) return HTTP 200.
- [ ] Zero API keys or secrets exposed to client bundles or repository commits.
- [ ] All software runs strictly within \$0.00 USD verified free-tier limits.
