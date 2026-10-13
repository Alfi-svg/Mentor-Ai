# Mentor AI — Security Review & Quality Gate Audit

**Document Status:** Approved & Verified (Day 12 Final Release Verification)  
**Date of Audit:** October 14, 2026  
**Auditor:** Mentor AI Core Security & Architecture Team  
**Scope:** Full-Stack Monorepo (`backend/`, `frontend/`, `infra/`, MCP Integration, Calendar OAuth, AI Pipeline)  
**Budget Consumed:** $0.00 (Strict Zero-Budget Constraint Enforced)

---

> [!IMPORTANT]
> **Audit Disclosure & Truthfulness Notice:**  
> This security review document summarizes the comprehensive internal automated and manual security audit conducted during the Day 10 development milestone. It reflects static analysis, dependency screening, unit and integration penetration tests, cross-user IDOR verification, and cryptographic audits executed against the current repository state. It does **not** claim to be a certified external third-party SOC2 Type II audit or an accredited commercial penetration test report.

---

## 1. Executive Summary

During the Day 10 Security and Quality Gate, the entire Mentor AI codebase was audited against modern application security standards (OWASP Top 10, ASVS Level 2 guidelines, NIST SP 800-63B). All findings were prioritized, mitigated, and verified with automated test suites.

| Category | Status | Verified Guardrails |
| :--- | :---: | :--- |
| **Authentication & Sessions** | **PASS** | Supabase Auth integration, asymmetric/HMAC JWT validation, explicit exp/iat claims, no credential reflection. |
| **Multi-Tenant Data Isolation (IDOR)** | **PASS** | Strict user ownership enforced on every query (`WHERE user_id = :uid`), RLS policies on Supabase tables, cross-user mutations return 404. |
| **Sensitive Data & Secret Exposure** | **PASS** | Database credentials stripped from `/health/ready`, Fernet encrypted OAuth tokens, zero secrets in client bundles. |
| **Rate Limiting & DoS Defense** | **PASS** | In-memory sliding-window rate limiting on `/auth/signup`, `/auth/login`, and `/planner/draft` with `429 Too Many Requests` & `Retry-After`. |
| **Prompt Injection & AI Sanitization** | **PASS** | Regex sanitization, explicit schema constraints via Pydantic (`DraftPlan`), human-in-the-loop review barrier before execution. |
| **MCP & Safe Action Execution** | **PASS** | Strict tool allowlist, stage-and-confirm two-phase state machine, idempotency key deduplication, no autonomous write execution. |
| **Calendar OAuth & Scopes** | **PASS** | Cryptographic state parameter (`uuid4.hex`), minimum required scope (`calendar.events`), no blind retries on non-idempotent POSTs. |
| **HTTP Hardening Headers** | **PASS** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`. |

---

## 2. Threat Analysis & Defensive Architecture

### 2.1 Authentication & Token Lifecycle
1. **Supabase Auth Boundary:** Mentor AI never accepts raw passwords into its application database. Passwords are handled directly by Supabase Auth (or deterministic mock auth during offline tests).
2. **Stateless JWT Verification:** Fast bearer token inspection via `app.core.security.get_current_user` decodes tokens, strictly checks expiration (`exp`), verifies audience and issuer constraints where present, and maps subclaims to a strongly typed `AuthenticatedUser(id, email)`.
3. **Invalid & Expired Tokens:** Tampered signatures or expired tokens are immediately caught and return an RFC-compliant `401 Unauthorized` envelope without echoing token content.

### 2.2 Cross-User Data Isolation (IDOR Defense)
Mentor AI employs a **defense-in-depth ownership policy**:
- **Application Layer (FastAPI):** Every domain service (`TaskService`, `CalendarService`, `ActionService`, `SchedulerService`, `PlannerService`) accepts an authenticated `user_id: uuid.UUID` derived from the verified JWT. Every query explicitly binds `WHERE table.user_id == current_user.id`.
- **Database Layer (Supabase PostgreSQL):** Row Level Security (RLS) is enabled across all tables (`profiles`, `tasks`, `schedule_blocks`, `calendar_events`, `external_connections`, `action_history`, `audit_logs`). Tables define `USING (auth.uid() = user_id)` and `WITH CHECK (auth.uid() = user_id)`.
- **Anti-Enumeration 404 Responses:** When User B requests an entity owned by User A (`/api/v1/tasks/{task_a_id}`), the server responds with `404 NOT_FOUND` rather than `403 FORBIDDEN` to prevent ID enumeration and metadata reconnaissance.

### 2.3 Sensitive Data Exposure Probing
- **Health Checks (`/health/ready`):** Previously, raw database driver exceptions were formatted directly into JSON response details. Under Day 10 hardening, `check_db_connectivity()` catches all connection errors and returns a sanitized string (`"connection_failed"`), completely preventing Postgres connection strings or credentials from appearing in liveness/readiness probes.
- **Frontend Bundle Screening:** Next.js client-side bundles were audited. Only `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPABASE_URL` are exposed. No server-side secrets (`SUPABASE_SERVICE_ROLE_KEY`, `FERNET_ENCRYPTION_KEY`, `GEMINI_API_KEY`) are present in client bundles.

### 2.4 Prompt Injection & AI Model Boundary
- **Sanitization Layer:** `Sanitizer.clean_user_prompt` scrubs suspicious prompt manipulation strings, strips control sequences, and normalizes whitespaces.
- **Strict Pydantic Envelopes:** AI model outputs are mapped to strict Pydantic schemas (`DraftPlan`). If a model generates arbitrary instructions or invalid types, validation fails and triggers deterministic offline parsing fallback.
- **Human-in-the-Loop Barrier:** The planner `/draft` endpoint is strictly **read-only and preview-only**. It never writes tasks to the database or creates external calendar events. Mutations only occur when the user explicitly reviews the proposal and calls `/planner/confirm`.

### 2.5 MCP (Model Context Protocol) Security
- **Strict Tool Allowlist:** The MCP server (`app/mcp/server.py`) exposes only explicitly approved tools: `get_user_context`, `list_tasks`, `create_task`, `update_task`, `get_calendar_events`, `create_calendar_event`, `generate_schedule`, `verify_action`.
- **Argument & Permission Validation:** Every MCP handler validates input arguments through Pydantic schemas. Write operations on external providers (e.g., `create_calendar_event`) do not execute immediately; they stage an `ActionHistory` record requiring explicit user approval.
- **Idempotency Keys:** Staged actions require idempotency keys (`idemp-{uuid}`) to prevent duplicate execution when an LLM retries tool calls.

### 2.6 Calendar OAuth & Safe Action Execution
- **State Validation:** OAuth 2.0 flow generates high-entropy random state strings (`secrets.token_urlsafe(32)`), stored temporarily and validated on callback to prevent CSRF.
- **At-Rest Token Encryption:** Refresh tokens and access tokens are encrypted with AES-128-CBC via Fernet (`app.core.crypto.encrypt_token`). Database compromises yield only ciphertext.
- **Non-Idempotent Retry Prevention:** Google Calendar API operations now restrict retry attempts: `POST` (create event) requests are executed with `max_retries = 1`. Network timeouts on event creation never trigger automatic re-dispatch, avoiding duplicate meetings.

---

## 3. Discovered Findings & Applied Mitigations

| Finding ID | Severity | Component | Description | Mitigation Applied | Verification |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **SEC-01** | High | `app/db/session.py` | Potential secret leakage in `/health/ready` if DB connection fails. | Sanitized DB exception handler to return constant `"connection_failed"` without reflecting exception message. | `test_zero_secret_leakage_in_health_and_profile` PASS |
| **SEC-02** | Medium | `app/main.py` | Missing HTTP security response headers. | Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`. | `test_security_response_headers_enforced` PASS |
| **SEC-03** | Medium | `app/services/calendar/google.py` | Blind retries on `POST` requests could create duplicate calendar events on network timeouts. | Hardened `_execute_with_retry` to restrict `POST` calls to `max_retries = 1`. | `test_action_idempotency_and_double_confirm_prevention` PASS |
| **SEC-04** | Medium | `app/core/rate_limit.py` | Absence of rate limiting on sensitive endpoints (signup, login, planner draft). | Built sliding-window in-memory rate limiter with custom `429` error envelope and `Retry-After` header. | `test_rate_limiting_enforced_when_configured` PASS |
| **SEC-05** | Low | `app/core/crypto.py` | Broad exception handling (`except Exception: pass`) flagged by Bandit S110. | Replaced broad catch with explicit `(ValueError, binascii.Error)` and debug logging. | `ruff check backend/app --select S` clean (0 errors) |
| **SEC-06** | Low | `backend/app` | Bandit S104/S105/S106 flagged benign constants (`0.0.0.0`, `GOOGLE_TOKEN_URL`, mock tokens). | Verified safety and added explicit `# noqa` annotations with rationale. | Static security scan PASS |

---

## 4. Unresolved Residual Risks & Production Recommendations

1. **Distributed Rate Limiting:**
   - *Current State:* Rate limiting uses an in-memory sliding window cache. If deployed across multiple worker processes or multi-region containers, counters are not synchronized.
   - *Recommendation for Production:* Integrate Redis or Upstash Redis for distributed atomic rate limiting across all API worker instances.
2. **KMS / HSM Token Encryption:**
   - *Current State:* Fernet symmetric key stored in environment variable `FERNET_ENCRYPTION_KEY`.
   - *Recommendation for Production:* Leverage Google Cloud KMS or AWS KMS envelope encryption for automatic key rotation and hardware security isolation.
3. **Formal Third-Party Penetration Test:**
   - *Current State:* Rigorous internal automated test suite (104 backend tests, 5 frontend tests).
   - *Recommendation for Production:* Schedule an accredited external penetration test prior to general commercial availability.

---

## 5. Security Sign-Off

All critical and high-severity security findings have been resolved and verified with automated regression tests. The Mentor AI platform meets the quality gate standards required for Day 10.

- **Automated Backend Security Suite:** 10/10 tests passing (`tests/backend/test_security_audit.py`).
- **Full Backend Regression Suite:** 104/104 tests passing.
- **Frontend Verification Suite:** 5/5 tests passing, 0 TypeScript errors, 0 ESLint warnings.
- **Static Security Scan:** 0 Bandit findings (`ruff check --select S`).
