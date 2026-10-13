# Mentor AI — Threat Model (STRIDE Methodology)

**Application Type:** Multi-Tenant Web & API Scheduling Agent  
**Compliance Target:** OWASP Top 10, WCAG 2.1 AA, Least Privilege Security

---

## 1. System Asset Classification
1. **User Personal Identifiable Information (PII):** Email, full name, calendar entries, location, study schedule.
2. **Third-Party Credentials:** Google Calendar OAuth 2.0 refresh tokens, Supabase service keys, Gemini API keys.
3. **Application State:** Tasks, historical action audit records, schedule blocks.

---

## 2. Threat Analysis & Mitigations

### 2.1 Spoofing (Identity Deception)
- **Threat:** Malicious actor invokes API routes presenting forged claims or spoofed user identifiers.
- **Vulnerability:** Relying on client-supplied `user_id` query params or JSON body fields.
- **Mitigation:**
  - Mandatory Supabase JWT verification on every non-public route.
  - User identity is extracted *exclusively* from the validated JWT payload (`sub` claim).
  - Client-supplied `user_id` values in request bodies are ignored and overwritten with the authenticated identity.

### 2.2 Tampering (Data Modification)
- **Threat:** Insecure Direct Object Reference (IDOR) — User A attempts to edit or delete User B's tasks or calendar events (`DELETE /api/v1/tasks/{user_b_task_id}`).
- **Mitigation:**
  - Multi-layer defense:
    1. **Application Layer:** Backend queries always filter by `WHERE id = :task_id AND user_id = :current_user_id`.
    2. **Database Layer:** PostgreSQL Row-Level Security (RLS) policies enforce `USING (auth.uid() = user_id)`. Even if application code has a bug, the database rejects unauthorized access.

### 2.3 Repudiation (Denial of Action)
- **Threat:** User or automated agent triggers a calendar modification or task deletion and claims the system malfunctioned.
- **Mitigation:**
  - Immutable `action_history` records every mutation with:
    - Initiator user ID
    - Action type and structured payload
    - Timestamp of proposal
    - Timestamp of explicit confirmation
    - Post-condition verification status
  - Audit logging of all security-sensitive events.

### 2.4 Information Disclosure (Data Leakage)
- **Threats:**
  1. API keys leaking through browser bundles or git commits.
  2. Prompt injection coaxing the LLM into revealing system prompts or backend secrets.
  3. Sensitive error stack traces returned to the client.
- **Mitigations:**
  - Server secrets (`SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`) are loaded via environment variables and never exposed to Next.js public client bundles (`NEXT_PUBLIC_*`).
  - System prompts contain strictly domain instructions without confidential keys or database passwords.
  - Production error responses return sanitized messages with correlation `trace_id` rather than raw Python stack traces.

### 2.5 Denial of Service (DoS & Resource Exhaustion)
- **Threats:**
  1. Excessive task scheduling requests overloading the interval constraint solver.
  2. Malicious user entering astronomical task durations (e.g. 1,000,000 minutes) to induce arithmetic overflow.
  3. LLM API quota exhaustion from rapid burst requests.
- **Mitigations:**
  - Pydantic v2 validation enforces hard constraints: `duration_minutes <= 720` (max 12 hours), `title <= 200` chars.
  - Scheduling engine operates in $O(N \log N)$ time and enforces a hard execution timeout (100ms max).
  - Token-bucket rate limiting applied to `/api/v1/chat/message` and `/api/v1/schedule/generate`.

### 2.6 Elevation of Privilege
- **Threat:** Natural language prompt injection commanding the AI to execute arbitrary bash commands, SQL updates, or unauthorized tool executions.
- **Mitigations:**
  - The LLM has zero direct execution capabilities: no shell tools, no raw SQL execution, no arbitrary HTTP tools.
  - The LLM only emits typed structured JSON against defined Pydantic schemas.
  - Consequential mutations (e.g., mutating external calendars) require two-phase human confirmation in the UI.

---

## 3. Secret Management & Storage Policy
- **Development:** Local `.env` files added to `.gitignore`.
- **Production:** Injected via Vercel and Render/Koyeb dashboard secrets.
- **OAuth Scopes:** Google Calendar requested with minimal required scope: `https://www.googleapis.com/auth/calendar.events` (events only, not full account access).
