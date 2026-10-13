# REST API Contract — Mentor AI

**Version:** 1.0.0-OAS  
**Base Path:** `/api/v1`  
**Protocol:** HTTPS / JSON REST  
**Authentication:** HTTP Authorization Bearer Token (`Bearer <Supabase_JWT>`)  

---

## 1. Authentication & Security Headers

All endpoints except `/api/v1/health` require:
```http
Authorization: Bearer <SUPABASE_JWT_ACCESS_TOKEN>
Content-Type: application/json
```

### Standard Error Envelope Format
All non-2xx responses return a consistent, structured JSON envelope:
```json
{
  "status_code": 422,
  "error_code": "VALIDATION_ERROR",
  "detail": "Input validation failed for one or more fields.",
  "validation_errors": [
    {
      "field": "duration_minutes",
      "issue": "Input should be greater than 0 and less than or equal to 720",
      "received": 0
    }
  ],
  "trace_id": "a93f-4e02-861e-128b",
  "timestamp": "2026-10-13T23:19:00Z"
}
```

### Standard Error Codes
| HTTP Status | Error Code | Meaning |
| :--- | :--- | :--- |
| **401** | `UNAUTHORIZED` | Missing, malformed, or expired JWT bearer token. |
| **403** | `FORBIDDEN` | Valid token, but operation forbidden for this user identity. |
| **404** | `NOT_FOUND` | Resource does not exist or belongs to another user. |
| **409** | `CONFLICT` | Schedule conflict or duplicate idempotency key detected. |
| **422** | `VALIDATION_ERROR` | Pydantic payload schema violation. |
| **429** | `RATE_LIMITED` | Token bucket limit exceeded; includes `Retry-After` header. |
| **500** | `INTERNAL_ERROR` | Sanitized server error. Raw trace is logged server-side only. |

---

## 2. API Endpoints Reference

### 2.1 System & Health

#### `GET /api/v1/health`
- **Auth:** Public
- **Response 200 OK:**
```json
{
  "status": "healthy",
  "database": "connected",
  "ai_provider": "gemini-flash",
  "version": "1.0.0",
  "timestamp": "2026-10-13T23:19:00Z"
}
```

---

### 2.2 User Profile & Preferences

#### `GET /api/v1/auth/me`
- **Auth:** Bearer Token
- **Response 200 OK:**
```json
{
  "id": "e4b2d308-4e89-4876-9289-46700c926df9",
  "email": "alex.student@university.edu",
  "full_name": "Alex Chen",
  "timezone": "America/New_York",
  "preferences": {
    "work_start_time": "09:00:00",
    "work_end_time": "18:00:00",
    "buffer_minutes": 15,
    "default_task_duration": 45,
    "max_focus_hours_per_day": 8,
    "available_days": [1, 2, 3, 4, 5],
    "auto_schedule_breaks": true
  }
}
```

#### `PUT /api/v1/preferences`
- **Auth:** Bearer Token
- **Request Body:**
```json
{
  "work_start_time": "08:30:00",
  "work_end_time": "17:30:00",
  "buffer_minutes": 20,
  "default_task_duration": 50,
  "max_focus_hours_per_day": 7,
  "available_days": [1, 2, 3, 4, 5],
  "auto_schedule_breaks": true
}
```
- **Response 200 OK:** Full updated preferences object.

---

### 2.3 Tasks Resource (`/api/v1/tasks`)

#### `GET /api/v1/tasks`
- **Auth:** Bearer Token
- **Query Parameters:**
  - `status` (optional): `pending` | `in_progress` | `completed` | `cancelled`
  - `priority` (optional): `P1` | `P2` | `P3` | `P4`
  - `energy_level` (optional): `high` | `medium` | `low`
  - `search` (optional): string search across title and description
  - `due_before` (optional, ISO-8601): filter tasks with deadline on or before timestamp
  - `due_after` (optional, ISO-8601): filter tasks with deadline on or after timestamp
  - `is_archived` (default: `false`): whether to return archived tasks
  - `sort_by` (default: `created_at`): `created_at` | `updated_at` | `deadline` | `priority` | `duration_minutes`
  - `sort_order` (default: `desc`): `asc` | `desc`
  - `limit` (default: 50, min: 1, max: 100)
  - `offset` (default: 0, min: 0)
- **Response 200 OK:**
```json
{
  "items": [
    {
      "id": "7fa69a4c-5353-4ff5-a92c-5b7ef89dc721",
      "user_id": "11111111-1111-1111-1111-111111111111",
      "title": "Complete Operating Systems Lab 2",
      "description": "Multi-threaded process scheduler in C",
      "status": "pending",
      "priority": "P1",
      "duration_minutes": 120,
      "deadline": "2026-10-15T23:59:59Z",
      "energy_level": "high",
      "tags": ["cs301", "lab"],
      "constraints": {
        "earliest_start": "09:00",
        "latest_end": "17:00",
        "preferred_time_of_day": "morning"
      },
      "is_archived": false,
      "created_at": "2026-10-13T10:00:00Z",
      "updated_at": "2026-10-13T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### `POST /api/v1/tasks`
- **Auth:** Bearer Token
- **Request Body:**
```json
{
  "title": "Study Linear Algebra Chapter 4",
  "description": "Eigenvalues and matrix diagonalization",
  "priority": "P2",
  "duration_minutes": 90,
  "deadline": "2026-10-16T18:00:00Z",
  "energy_level": "high",
  "tags": ["math"],
  "constraints": {
    "earliest_start": "10:00",
    "latest_end": "18:00"
  }
}
```
- **Response 201 Created:** Full task object with assigned UUID.

#### `GET /api/v1/tasks/{id}`
- **Auth:** Bearer Token
- **Response 200 OK:** Full task object.
- **Response 404 Not Found:** If task does not exist or belongs to another user.

#### `PATCH /api/v1/tasks/{id}`
- **Auth:** Bearer Token
- **Request Body (partial update):**
```json
{
  "status": "in_progress",
  "duration_minutes": 105,
  "priority": "P1"
}
```
- **Response 200 OK:** Updated task object.
- **Response 400 Bad Request:** If requested status transition is not permitted.
- **Response 404 Not Found:** If task does not exist or belongs to another user.

#### `DELETE /api/v1/tasks/{id}`
- **Auth:** Bearer Token
- **Response 204 No Content:** Permanently removes task and records atomic audit log entry.
- **Response 404 Not Found:** If task does not exist or belongs to another user.

#### `POST /api/v1/tasks/{id}/complete`
- **Auth:** Bearer Token
- **Response 200 OK:** Marks task as `completed` (transitions from `pending` or `in_progress`).

#### `POST /api/v1/tasks/{id}/reopen`
- **Auth:** Bearer Token
- **Response 200 OK:** Reopens a `completed` or `cancelled` task back to `pending`.

#### `POST /api/v1/tasks/{id}/archive`
- **Auth:** Bearer Token
- **Response 200 OK:** Sets `is_archived: true` without deleting task history.

#### `POST /api/v1/tasks/{id}/unarchive`
- **Auth:** Bearer Token
- **Response 200 OK:** Restores archived task back to active list (`is_archived: false`).

#### Status Transition State Machine Rules
| Current Status | Permitted Target Statuses | Disallowed Target Statuses |
| :--- | :--- | :--- |
| `pending` | `in_progress`, `completed`, `cancelled` | *(None)* |
| `in_progress` | `pending` (pause), `completed`, `cancelled` | *(None)* |
| `completed` | `pending` (reopen), `in_progress` (reopen) | `cancelled` (must reopen first) |
| `cancelled` | `pending` (restore/reopen) | `completed`, `in_progress` (must restore first) |

---

### 2.4 Calendar Events Resource (`/api/v1/calendar`)

#### `GET /api/v1/calendar/events`
- **Query Parameters:**
  - `start_time` (mandatory, ISO-8601): e.g. `2026-10-14T00:00:00Z`
  - `end_time` (mandatory, ISO-8601): e.g. `2026-10-14T23:59:59Z`
- **Response 200 OK:**
```json
{
  "events": [
    {
      "id": "9368d447-e179-44be-b333-e18e3a29ec62",
      "title": "CS301 Lecture",
      "description": "Distributed Consensus Algorithms",
      "start_time": "2026-10-14T10:00:00Z",
      "end_time": "2026-10-14T11:30:00Z",
      "is_all_day": false,
      "is_fixed": true,
      "source": "google_calendar",
      "location": "Auditorium B"
    }
  ]
}
```

#### `POST /api/v1/calendar/events`
- **Request Body:**
```json
{
  "title": "Sprint Planning Meeting",
  "start_time": "2026-10-14T14:00:00Z",
  "end_time": "2026-10-14T15:00:00Z",
  "is_fixed": true,
  "location": "Zoom"
}
```
- **Response 201 Created:** Created event object.

---

### 2.5 Deterministic Schedule Resource (`/api/v1/schedule`)

#### `POST /api/v1/schedule/generate`
- **Request Body:**
```json
{
  "target_date": "2026-10-14",
  "task_ids": ["7fa69a4c-5353-4ff5-a92c-5b7ef89dc721"],
  "enforce_buffer": true
}
```
- **Response 200 OK:**
```json
{
  "schedule_id": "bfd91e60-4357-4189-9a74-9b1654e58b88",
  "target_date": "2026-10-14",
  "status": "feasible",
  "total_scheduled_minutes": 210,
  "blocks": [
    {
      "id": "blk-01",
      "calendar_event_id": "9368d447-e179-44be-b333-e18e3a29ec62",
      "title": "CS301 Lecture",
      "start_time": "2026-10-14T10:00:00Z",
      "end_time": "2026-10-14T11:30:00Z",
      "block_type": "fixed_event",
      "is_fixed": true
    },
    {
      "id": "blk-02",
      "title": "Buffer",
      "start_time": "2026-10-14T11:30:00Z",
      "end_time": "2026-10-14T11:45:00Z",
      "block_type": "buffer",
      "is_fixed": false
    },
    {
      "id": "blk-03",
      "task_id": "7fa69a4c-5353-4ff5-a92c-5b7ef89dc721",
      "title": "Complete Operating Systems Lab 2",
      "start_time": "2026-10-14T11:45:00Z",
      "end_time": "2026-10-14T13:45:00Z",
      "block_type": "task",
      "is_fixed": false
    }
  ],
  "conflicts": [],
  "unscheduled_tasks": []
}
```

---

### 2.6 Natural Language Chat Assistant (`/api/v1/chat`)

#### `POST /api/v1/chat/message`
- **Request Body:**
```json
{
  "message": "Plan tomorrow: I have algorithms class 10am-11:30am and need 2 hours to code my compiler assignment.",
  "client_timezone": "America/New_York"
}
```
- **Response 200 OK:**
```json
{
  "intent": "plan_day",
  "explanation": "Extracted 1 lecture and 1 assignment needing 2 hours. Scheduled safely around your commitments.",
  "extracted_data": {
    "target_date": "2026-10-14",
    "detected_events": [
      {
        "title": "Algorithms Class",
        "start_time": "2026-10-14T10:00:00-04:00",
        "end_time": "2026-10-14T11:30:00-04:00"
      }
    ],
    "detected_tasks": [
      {
        "title": "Code Compiler Assignment",
        "duration_minutes": 120,
        "priority": "P2"
      }
    ]
  },
  "requires_approval": true,
  "pending_action_id": "act-7712",
  "clarification_needed": null
}
```

---

### 2.7 Action Approvals & Verification (`/api/v1/actions`)

#### `GET /api/v1/actions/pending`
- **Response 200 OK:** Array of staged actions awaiting user confirmation.

#### `POST /api/v1/actions/{id}/confirm`
- **Request Body:**
```json
{
  "confirmed": true
}
```
- **Response 200 OK:**
```json
{
  "action_id": "act-7712",
  "status": "completed",
  "verified": true,
  "verification_details": {
    "db_records_inserted": 2,
    "schedule_generated": true
  }
}
```

---

### 2.8 Calendar Integration (`/api/v1/calendar`)

Manages external Google Calendar integration (OAuth 2.0 PKCE/CSRF flow), token security, bidirectional sync with timezone normalization to UTC, and conflict analysis.

#### `GET /api/v1/calendar/status`
- **Auth:** Bearer Token
- **Response 200 OK:**
```json
{
  "is_connected": true,
  "provider": "google_calendar",
  "account_email": "student@university.edu",
  "last_synced_at": "2026-10-14T01:15:00Z",
  "scopes": ["https://www.googleapis.com/auth/calendar.events", "openid", "email"],
  "message": "Connected"
}
```
*Note: If OAuth credentials are not configured on the server, `is_connected` will be `false` and `message` will explicitly state `"Not Connected (OAuth Credentials Not Configured)"`.*

#### `GET /api/v1/calendar/connect`
- **Auth:** Bearer Token
- **Response 200 OK:**
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=...&state=eyJ...",
  "provider": "google_calendar",
  "scopes": ["https://www.googleapis.com/auth/calendar.events", "openid", "email"]
}
```

#### `GET /api/v1/calendar/callback`
- **Auth:** Public redirect callback (requires valid HMAC-signed `state` query parameter containing the user UUID)
- **Query Params:** `code` (string), `state` (signed JWT-like HMAC payload)
- **Response 200 OK:**
```json
{
  "status": "connected",
  "provider": "google_calendar",
  "account_email": "student@university.edu",
  "connected_at": "2026-10-14T01:15:30Z"
}
```

#### `POST /api/v1/calendar/disconnect`
- **Auth:** Bearer Token
- **Response 200 OK:**
```json
{
  "status": "disconnected",
  "provider": "google_calendar",
  "message": "Calendar connection has been successfully disconnected."
}
```

#### `GET /api/v1/calendar/events`
- **Auth:** Bearer Token
- **Query Params:**
  - `start_time` (optional ISO 8601 string, default: start of today)
  - `end_time` (optional ISO 8601 string, default: +7 days)
- **Response 200 OK:**
```json
[
  {
    "id": "e4f8d92a-3b1c-4b52-b883-93f0b2f153a7",
    "external_id": "google_evt_101",
    "title": "CS 450: Operating Systems Lecture",
    "description": "Weekly OS lecture",
    "start_time": "2026-10-14T14:00:00Z",
    "end_time": "2026-10-14T15:30:00Z",
    "is_all_day": false,
    "is_fixed": true,
    "source": "google_calendar",
    "location": "Hall 101"
  }
]
```

#### `POST /api/v1/calendar/sync`
- **Auth:** Bearer Token
- **Query Params:**
  - `days_back` (int, default: 7, range: 0-30)
  - `days_forward` (int, default: 14, range: 1-90)
- **Response 200 OK:**
```json
{
  "synced_count": 4,
  "start_time": "2026-10-07T00:00:00Z",
  "end_time": "2026-10-28T23:59:59Z",
  "provider": "google_calendar",
  "last_synced_at": "2026-10-14T01:16:00Z"
}
```

#### `GET /api/v1/calendar/conflicts`
- **Auth:** Bearer Token
- **Query Params:**
  - `target_date` (required date string: `YYYY-MM-DD`)
- **Response 200 OK:**
```json
{
  "target_date": "2026-10-14",
  "has_conflicts": true,
  "total_busy_minutes": 90,
  "conflicting_events": [
    {
      "title": "CS 450: Operating Systems Lecture",
      "start_time": "2026-10-14T14:00:00Z",
      "end_time": "2026-10-14T15:30:00Z",
      "is_all_day": false
    }
  ],
  "free_slots": [
    {
      "start_time": "2026-10-14T13:00:00Z",
      "end_time": "2026-10-14T14:00:00Z",
      "duration_minutes": 60
    },
    {
      "start_time": "2026-10-14T15:30:00Z",
      "end_time": "2026-10-14T21:00:00Z",
      "duration_minutes": 330
    }
  ]
}
```
