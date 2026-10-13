# Mentor AI — Known Limitations & Free-Tier Operational Constraints

**Version:** 1.0.0-PROD  
**Status:** Approved for Release Sign-Off  
**Policy:** Strict Transparency (No Hidden Constraints)

---

## 1. Free-Tier Infrastructure Constraints

Mentor AI is intentionally engineered to operate on perpetual $0.00 free tiers. Operators and users should understand the behavioral trade-offs inherent in these tiers:

| Provider | Constraint / Behavior | Impact on User | Mitigation Built into Mentor AI |
| :--- | :--- | :--- | :--- |
| **Render** | **15-Minute Inactivity Spin-Down:** Free web services spin down after 15 minutes of zero HTTP requests. | The first request after spin-down experiences a **~50-second cold start**. | The frontend [`HealthStatusBadge`](../frontend/components/HealthStatusBadge.tsx) detects delays $> 2.5\text{s}$ and displays *"Waking up server (free-tier spin-up ~50s)..."*, preventing duplicate clicks. Optional keep-alive ping via free cron eliminates day-time spin-downs. |
| **Render** | **Ephemeral Container Filesystem:** The disk resets upon every deploy or restart. | Any files stored locally in `/tmp` or on disk are erased. | Mentor AI **never stores user state or SQLite databases on Render's disk**. All state is externalized to Supabase PostgreSQL. |
| **Supabase** | **7-Day Inactivity Database Pause:** Free database instances pause after 7 consecutive days of zero database queries. | Database becomes unreachable until manually unpaused in Supabase dashboard. | Supabase sends an email warning on day 5. Complete schema is versioned in Alembic migrations (`alembic upgrade head`) and pure SQL (`docs/database-schema.sql`), allowing complete reconstitution in $< 2\text{ minutes}$. |
| **Google AI Studio** | **15 RPM / 1,500 RPD Rate Limits:** Gemini free tier allows max 15 requests/minute. | Rapid burst prompting could trigger HTTP 429 Too Many Requests. | Application-level rate limiter throttles excessive requests; automatic fallback engages Groq Llama 3.3 or deterministic offline rule parser. |
| **Google Cloud** | **OAuth Testing Mode User Cap:** Unverified Google OAuth apps in testing mode allow a maximum of 100 test user emails. | Public sign-in with arbitrary Google accounts requires manual email whitelisting in Google Cloud Console. | Transparently documented; `MockCalendarAdapter` provides zero-friction local and CI testing without OAuth friction. |

---

## 2. Functional & Algorithmic Scope Boundaries

To prevent bloat, hallucinations, and unreliability, Mentor AI defines explicit functional boundaries:

1. **No What-If Simulations:**
   - The scheduler does not run speculative Monte Carlo simulations or alternate-timeline branching.
   - The scheduler solves concrete intervals for a requested target date based on real constraints.
2. **No Unsolicited Personal Advice:**
   - The AI assistant does not provide generic motivational coaching, unsolicited wellness tips, or subjective life advice. It strictly focuses on task breakdown and scheduling.
3. **Single-Worker In-Memory Rate Limiting:**
   - The current rate limiter uses an in-memory sliding window cache. In a multi-replica container deployment, rate counters are local to each process rather than globally synchronized.
   - *Production Recommendation:* Upgrade to Upstash Redis or managed Redis for distributed atomic rate limiting if scaling beyond a single worker.
4. **Offline Rule-Based Parser Scope:**
   - The deterministic offline parser (`offline.py`) reliably handles time formats (`10am to 11:30am`, `14:00-15:30`), durations (`2 hours`, `90 minutes`, `45m`), and priorities (`P1`, `urgent`).
   - Highly complex linguistic phrasing (e.g. multi-paragraph narratives with contradictory constraints) is handled more effectively by Gemini or Groq LLM adapters.

---

## 3. Integration Status Matrix

| Integration | Implementation State | Verification Status | Environment Tested |
| :--- | :---: | :---: | :--- |
| **Supabase PostgreSQL 15** | Implemented | **VERIFIED** | AsyncPG connection pooler, Alembic migrations, and SQLite fallback. |
| **Supabase GoTrue Auth** | Implemented | **VERIFIED** | JWT bearer validation, local deterministic test mode, and live GoTrue endpoints. |
| **Google Calendar API v3** | Implemented | **VERIFIED** | OAuth flow, encrypted Fernet tokens, event normalization, and `MockCalendarAdapter` test boundary. |
| **Google AI Studio (Gemini)** | Implemented | **VERIFIED** | Structured output schema, error handling, rate limiting, and fallback. |
| **Groq Cloud (Llama 3.3)** | Implemented | **VERIFIED** | Fallback adapter with mock and live HTTP client. |
| **Model Context Protocol (FastMCP)**| Implemented | **VERIFIED** | 8 typed tools over stdio/sse with auth token validation. |
| **Apple Calendar (CalDAV) / Outlook** | Not Implemented | **OUT OF SCOPE** | Planned for post-MVP via universal iCal (.ics) subscription feeds. |
| **Alexa ASK Native Voice Skill** | Not Implemented | **OUT OF SCOPE** | Browser Web Speech API provides free zero-cost voice input. |

---

## 4. Next Priorities & Post-MVP Roadmap

1. **Distributed Rate Limiting:** Integrate Redis for multi-instance production clusters.
2. **Universal iCal (.ics) Feeds:** Provide read-only calendar feed URLs for Outlook and Apple Calendar users without OAuth.
3. **PWA Mobile App:** Add service worker and manifest for offline mobile installation.
4. **Enhanced Recurring Task Rules:** Native recurring frequency rules (e.g. "Every Tuesday at 10am").
