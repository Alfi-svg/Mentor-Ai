# Mentor AI — Complete User Guide & Operator Manual

**Version:** 1.0.0-PROD  
**Target Audience:** University Students, Working Professionals, and System Operators  
**Product Tagline:** *Your Goals. Your Plan. Your Next Move.*

---

## 1. Introduction & Architectural Principles

Mentor AI is an intelligent personal scheduling and task-orchestration SaaS platform designed for university students balancing academic deadlines and working professionals managing complex schedules.

Unlike unstructured chatbots or passive digital calendars, Mentor AI enforces strict architectural separation between **natural language intent understanding** and **mathematical scheduling execution**:
- **Deterministic Scheduling:** Tasks are scheduled via interval algebra in pure Python. The system never hallucinates time windows, never moves fixed meetings without consent, and never overlaps commitments.
- **Human-in-the-Loop Action Approval:** External mutations (e.g. creating calendar events) require explicit two-phase review and approval before execution.
- **Truthful Error Reporting:** If an API quota is reached or calendar access is disconnected, the platform reports the exact failure instead of fabricating false confirmations.
- **Strict Scope Boundaries:** Mentor AI does not offer speculative "what-if" simulations or generic lifestyle coaching. It focuses purely on concrete planning and verified execution.

---

## 2. Getting Started: Account Setup & Profile Preferences

### 2.1 Registration & Authentication
1. Navigate to the Mentor AI Web Dashboard (`/signup`).
2. Provide your email, a secure password (minimum 8 characters), and your full name.
3. Session tokens are securely isolated in `sessionStorage` and verified via JWT bearer tokens.

### 2.2 Setting Availability & Scheduling Constraints
Navigate to the **Settings** or Dashboard to configure your working parameters:
- **Work Hours:** Default `09:00` to `18:00`.
- **Buffer Minutes:** Default `15 minutes` inserted between consecutive tasks and meetings to prevent context-switching fatigue.
- **Default Task Duration:** Default `45 minutes`.
- **Max Focus Hours:** Maximum daily capacity (e.g., `8 hours`).
- **Timezone:** IANA timezone string (e.g., `America/New_York`, `Europe/London`, `UTC`).

---

## 3. Core Workflows

### 3.1 Student Workflow: Classes, Labs & Deep Work Sessions
**Scenario:** Alex, a CS student with morning lectures, an afternoon lab, and an urgent Operating Systems report.

1. **Step 1 — Input Natural Language Instruction:**  
   Open the **Natural-Language Command Center** (`/planner`) and submit:
   ```text
   Plan my day tomorrow: Operating Systems lecture from 10am to 11:30am, Algorithms class from 2pm to 3:30pm, and I need 2 hours to complete my OS Lab Report.
   ```
2. **Step 2 — Interactive Plan Review:**  
   The system extracts:
   - Fixed Events: OS Lecture (10:00–11:30), Algorithms Class (14:00–15:30).
   - Tasks: OS Lab Report (120 minutes, Priority P1).
3. **Step 3 — Reviewing the Dry-Run Preview:**  
   The deterministic engine identifies available windows:
   - Morning: 09:00–10:00 (60m — too small for 120m contiguous lab).
   - Mid-day: 11:45–13:45 (120m — perfect fit with 15m buffers).
   - The preview timeline renders the proposed blocks in soft purple.
4. **Step 4 — Confirm Plan:**  
   Click **[Confirm & Generate Schedule]**. The tasks are persisted to PostgreSQL and the schedule is locked into your active calendar view.

---

### 3.2 Working Professional Workflow: Meetings & High-Priority Deliverables
**Scenario:** Priya, an engineering lead with back-to-back client calls and 3 priority backlog tasks.

1. **Step 1 — Connect Google Calendar:**  
   Open **Calendar Settings** (`/settings/calendar`) and connect your Google account. Existing client meetings are imported as immutable fixed blocks.
2. **Step 2 — Add Backlog Tasks:**  
   In **Task Backlog** (`/tasks`), create high-priority items:
   - "Architecture RFC Review" (45m, Priority P1, Deadline 17:00).
   - "Sprint Retrospective Prep" (30m, Priority P2).
3. **Step 3 — Generate Conflict-Free Schedule:**  
   Open **Schedule View** (`/schedule`) and click **"Generate Schedule"**.  
   The solver:
   - Respects client meetings (e.g. 11:00–12:00, 14:00–15:00).
   - Places the P1 RFC Review in the highest-energy morning window (09:00–09:45).
   - Adds 15-minute buffers before and after every meeting.
   - Automatically leaves 12:00–13:00 open for lunch.

---

### 3.3 Dynamic Rescheduling & Conflict Handling
**Scenario:** An unexpected deadline shift makes a 3-hour task impossible to complete within remaining work hours.

1. **Step 1 — Edit Task:**  
   Open `/tasks`, edit "Client Proposal", set duration to `180 minutes` and deadline to `16:00`.
2. **Step 2 — Regenerate Schedule:**  
   Click **"Regenerate Schedule"** on `/schedule`.
3. **Step 3 — Conflict Detection:**  
   If only 120 minutes of free time remain before 16:00, the system:
   - Flags the status as `conflict_detected` or `partial`.
   - Explicitly returns: *"Required 180 min, maximum available contiguous gap before deadline is 120 min."*
   - Suggests actionable options: Shorten duration, move deadline, or reschedule lower-priority items.
   - **Never silently drops tasks or fabricates extra hours.**

---

### 3.4 Two-Phase Action Approval Workflow
**Scenario:** Scheduling an external sync event on Google Calendar.

1. **Step 1 — Action Staged:**  
   When the planner or an MCP tool proposes adding an external event, it is staged in the **Action Inbox** (`/actions`) with status `pending_approval`.
2. **Step 2 — User Review:**  
   The user inspects:
   - Action Type: `create_calendar_event`
   - Parameters: Title, Start Time, End Time, Location.
   - Consequence: *"Will write a new event to your external Google Calendar."*
3. **Step 3 — Approval & Execution:**  
   Click **[Approve Action]**.
4. **Step 4 — Follow-Up Read Verification:**  
   Mentor AI executes the API request with an idempotency key and queries Google Calendar to confirm the remote event ID exists.
5. **Step 5 — Audit Log Record:**  
   The action transitions to `completed` and appears in the immutable Audit Log (`/actions`). Attempting to re-approve a completed action returns an error.

---

## 4. Natural-Language Command Reference

| Intent | Example Prompt Syntax | Expected Outcome |
| :--- | :--- | :--- |
| **Plan Full Day** | `"Plan my day tomorrow: Chemistry lecture from 9am to 10:30am and 90 minutes to review thermodynamics."` | Extracts 1 fixed event (90m) + 1 task (90m). Generates preview schedule. |
| **Missing Info Clarification** | `"Schedule my history paper tomorrow."` | Parser flags missing duration. Prompts: *"How much time do you estimate for 'history paper'?"* |
| **Add Single Task** | `"Add task complete CS lab report duration 60 minutes priority P1 due by 5pm tomorrow."` | Creates structured task with deadline and high priority. |
| **Add Calendar Event** | `"Schedule a sync with mentor on Friday from 3pm to 4pm."` | Stages `create_calendar_event` action in approval inbox. |
| **Offline Fallback** | `"Add task physics homework duration 45 minutes"` | Even with zero internet or API keys, deterministic offline parser creates the task in $< 1\text{ms}$. |

---

## 5. UI Tour: The 10 Core Application Screens

1. **Landing Page (`/`):** Explains system architecture, privacy pillars, and live backend readiness badge.
2. **Authentication (`/login` & `/signup`):** Accessible auth forms with JWT session management.
3. **Workspace Dashboard (`/dashboard`):** Real metrics (backlog count, scheduled blocks, pending approvals, calendar connectivity).
4. **Natural-Language Command Center (`/planner`):** Text prompt interface with real-world examples and timezone detection.
5. **Interactive Plan Review (`/planner`):** Displays extracted items, parser disclosure (`gemini`, `groq`, `deterministic_offline`), and editable fields.
6. **Schedule Timeline View (`/schedule`):** Visual timeline with color-coded blocks (meetings, tasks, breaks, buffers) and conflict banners.
7. **Task Backlog (`/tasks`):** Multi-filter task list (Priority P1–P4, status, search, completion toggles).
8. **Calendar Settings (`/settings/calendar`):** Real connection status, minimum scope transparency (`calendar.events`), and conflict inspector.
9. **Action Approval Inbox (`/actions`):** Consequential external actions staged for human approval.
10. **Audit & Verification History (`/actions`):** Immutable historical record with on-demand post-condition verification probes (`GET /actions/{id}/verify`).

---

## 6. Accessibility & Keyboard Shortcuts

- **WCAG 2.1 AA Compliance:** Minimum 4.5:1 text contrast on all viewports.
- **Focus Rings:** Visible `:focus-visible` outline on all interactive controls (`<button>`, `<input>`, `<select>`).
- **Keyboard Navigation:** Tab-order traversable through entire forms and schedule blocks.
- **Screen Reader Support:** Form validation errors include `role="alert"` and descriptive `aria-label` tags.
