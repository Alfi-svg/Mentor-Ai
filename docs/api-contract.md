# Mentor AI — API Contract (OpenAPI 3.1 / REST)

All endpoints are versioned under `/api/v1`. Authentication requires a standard HTTP Bearer token:
`Authorization: Bearer <Supabase_JWT_Token>`

---

## 1. System & Authentication Endpoints

### `GET /api/v1/health`
- **Description:** Liveness probe and database connectivity readiness check.
- **Auth:** None (Public)
- **Response 200 OK:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "ai_provider": "gemini-flash", // or "offline-fallback"
  "timestamp": "2026-10-13T23:15:00Z"
}
```

### `GET /api/v1/auth/me`
- **Description:** Retrieve authenticated user profile and configuration.
- **Auth:** Bearer Token
- **Response 200 OK:**
```json
{
  "id": "e4b2d308-4e89-4876-9289-46700c926df9",
  "email": "student@university.edu",
  "full_name": "Alfi",
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

### `PUT /api/v1/preferences`
- **Description:** Update working hours, buffer duration, or availability.
- **Auth:** Bearer Token
- **Request Body:**
```json
{
  "work_start_time": "08:30:00",
  "work_end_time": "17:30:00",
  "buffer_minutes": 20,
  "max_focus_hours_per_day": 7,
  "auto_schedule_breaks": true
}
```
- **Response 200 OK:** Updated preferences object.

---

## 2. Tasks API

### `GET /api/v1/tasks`
- **Query Params:**
  - `status`: `pending` | `in_progress` | `completed` | `cancelled`
  - `priority`: `P1` | `P2` | `P3` | `P4`
  - `limit`: int (default: 50)
  - `offset`: int (default: 0)
- **Response 200 OK:**
```json
{
  "tasks": [
    {
      "id": "7fa69a4c-5353-4ff5-a92c-5b7ef89dc721",
      "title": "Complete Operating Systems Lab 2",
      "description": "Implement multi-threaded process scheduler in C",
      "status": "pending",
      "priority": "P1",
      "duration_minutes": 120,
      "deadline": "2026-10-15T23:59:59Z",
      "energy_level": "high",
      "tags": ["academics", "systems"],
      "created_at": "2026-10-13T10:00:00Z",
      "updated_at": "2026-10-13T10:00:00Z"
    }
  ],
  "total": 1
}
```

### `POST /api/v1/tasks`
- **Request Body:**
```json
{
  "title": "Study Linear Algebra Chapter 4",
  "description": "Focus on Eigenvectors and Diagonalization",
  "priority": "P2",
  "duration_minutes": 90,
  "deadline": "2026-10-16T18:00:00Z",
  "energy_level": "high",
  "tags": ["math", "exam-prep"]
}
```
- **Response 201 Created:** Task entity with allocated ID.

### `PATCH /api/v1/tasks/{id}`
- **Request Body (partial fields):**
```json
{
  "status": "completed"
}
```
- **Response 200 OK:** Updated task object.

### `DELETE /api/v1/tasks/{id}`
- **Response 204 No Content**

---

## 3. Calendar Events API

### `GET /api/v1/calendar/events`
- **Query Params:** `start_time` (ISO), `end_time` (ISO)
- **Response 200 OK:**
```json
{
  "events": [
    {
      "id": "9368d447-e179-44be-b333-e18e3a29ec62",
      "title": "CS301 Lecture: Distributed Consensus",
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

### `POST /api/v1/calendar/events`
- **Request Body:**
```json
{
  "title": "Team Sprint Standup",
  "start_time": "2026-10-14T14:00:00Z",
  "end_time": "2026-10-14T14:30:00Z",
  "is_fixed": true,
  "location": "Google Meet"
}
```
- **Response 201 Created**

---

## 4. Deterministic Scheduling API

### `POST /api/v1/schedule/generate`
- **Description:** Runs the interval constraint solver for a target date.
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
      "id": "block-1",
      "calendar_event_id": "9368d447-e179-44be-b333-e18e3a29ec62",
      "title": "CS301 Lecture: Distributed Consensus",
      "start_time": "2026-10-14T10:00:00Z",
      "end_time": "2026-10-14T11:30:00Z",
      "block_type": "fixed_event",
      "is_fixed": true
    },
    {
      "id": "block-2",
      "title": "Buffer",
      "start_time": "2026-10-14T11:30:00Z",
      "end_time": "2026-10-14T11:45:00Z",
      "block_type": "buffer",
      "is_fixed": false
    },
    {
      "id": "block-3",
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

## 5. Natural Language & Chat Orchestration API

### `POST /api/v1/chat/message`
- **Request Body:**
```json
{
  "message": "Plan tomorrow: I have algorithms lecture at 10am to 11:30am and need 2 hours to code my compiler assignment.",
  "client_timezone": "America/New_York"
}
```
- **Response 200 OK:**
```json
{
  "intent": "plan_day",
  "extracted_data": {
    "target_date": "2026-10-14",
    "detected_events": [
      {
        "title": "Algorithms Lecture",
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
  "proposed_schedule_summary": "1 lecture (1.5 hrs), 1 task (2.0 hrs) scheduled safely between 09:00 and 18:00.",
  "requires_approval": true,
  "pending_action_id": "action-99",
  "clarification_needed": null
}
```

---

## 6. Action Approval & Verification API

### `GET /api/v1/actions/pending`
- **Description:** List actions waiting for explicit user confirmation.
- **Response 200 OK:** Array of pending action objects.

### `POST /api/v1/actions/{id}/confirm`
- **Request Body:**
```json
{
  "confirmed": true // or false to reject
}
```
- **Response 200 OK:**
```json
{
  "action_id": "action-99",
  "status": "completed",
  "verified": true,
  "verification_details": {
    "tasks_created": 1,
    "events_created": 1,
    "schedule_saved": true
  }
}
```

### `GET /api/v1/actions/history`
- **Description:** Audit trail of all staged, confirmed, completed, or failed operations.
- **Response 200 OK:** Paginated history list.
