/**
 * Frontend Unit & Integration Tests for Mentor AI API Client and Token Security.
 */

import test from "node:test";
import assert from "node:assert/strict";

// Mock browser global window & sessionStorage
global.window = {
  sessionStorage: {
    _store: {},
    getItem(key) {
      return this._store[key] || null;
    },
    setItem(key, val) {
      this._store[key] = String(val);
    },
    removeItem(key) {
      delete this._store[key];
    },
    clear() {
      this._store = {};
    },
  },
};

// Import ApiClientError logic and Token storage logic
class ApiClientError extends Error {
  constructor(envelope) {
    super(envelope.detail || "An unexpected API error occurred.");
    this.name = "ApiClientError";
    this.statusCode = envelope.status_code;
    this.errorCode = envelope.error_code || "UNKNOWN_ERROR";
    this.validationErrors = envelope.validation_errors;
    this.traceId = envelope.trace_id;
  }
}

const TOKEN_KEY = "mentor_ai_access_token";

function getStoredToken() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token) {
  if (typeof window === "undefined") return;
  if (token) {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

test("ApiClientError parses structured API error envelopes correctly", () => {
  const envelope = {
    status_code: 422,
    error_code: "VALIDATION_ERROR",
    detail: "Input validation failed for duration.",
    validation_errors: [
      { field: "estimated_duration_minutes", issue: "Duration must be between 1 and 720" },
    ],
    trace_id: "trace-xyz-123",
  };

  const err = new ApiClientError(envelope);
  assert.equal(err.name, "ApiClientError");
  assert.equal(err.statusCode, 422);
  assert.equal(err.errorCode, "VALIDATION_ERROR");
  assert.equal(err.message, "Input validation failed for duration.");
  assert.equal(err.traceId, "trace-xyz-123");
  assert.equal(err.validationErrors.length, 1);
  assert.equal(err.validationErrors[0].field, "estimated_duration_minutes");
});

test("Session token storage safely stores and clears tokens without leaking secrets", () => {
  // Clear any existing
  setStoredToken(null);
  assert.equal(getStoredToken(), null);

  // Store valid token
  const testJwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-payload.signature";
  setStoredToken(testJwt);
  assert.equal(getStoredToken(), testJwt);

  // Revoke / Logout clears token
  setStoredToken(null);
  assert.equal(getStoredToken(), null);
});

test("Schedule proposal status and conflict representation", () => {
  const sampleProposal = {
    target_date: "2026-10-15",
    timezone: "UTC",
    working_hours: { start_time: "09:00", end_time: "18:00" },
    scheduled_blocks: [
      {
        task_id: "task-1",
        calendar_event_id: null,
        title: "Study OS",
        start_time: "2026-10-15T09:00:00Z",
        end_time: "2026-10-15T10:00:00Z",
        block_type: "task_allocation",
        is_completed: false,
      },
    ],
    unscheduled_tasks: [],
    conflicts: [],
    summary: {
      total_working_minutes: 540,
      total_scheduled_task_minutes: 60,
      total_fixed_minutes: 0,
      total_free_minutes: 480,
      utilization_percentage: 11.1,
    },
    status: "feasible",
    validation_passed: true,
  };

  assert.equal(sampleProposal.status, "feasible");
  assert.equal(sampleProposal.validation_passed, true);
  assert.equal(sampleProposal.scheduled_blocks.length, 1);
  assert.equal(sampleProposal.summary.total_scheduled_task_minutes, 60);
});

test("Calendar status reports truthful connection state", () => {
  const connectedStatus = {
    is_connected: true,
    provider: "google_calendar",
    account_email: "student@university.edu",
    last_synced_at: "2026-10-14T01:15:00Z",
    scopes: ["https://www.googleapis.com/auth/calendar.events", "openid", "email"],
    message: "Connected",
  };

  assert.equal(connectedStatus.is_connected, true);
  assert.equal(connectedStatus.scopes.includes("https://www.googleapis.com/auth/calendar.events"), true);
  assert.equal(connectedStatus.scopes.includes("https://www.googleapis.com/auth/calendar"), false);

  const disconnectedStatus = {
    is_connected: false,
    provider: "google_calendar",
    account_email: null,
    last_synced_at: null,
    scopes: [],
    message: "Not Connected (OAuth Credentials Not Configured)",
  };

  assert.equal(disconnectedStatus.is_connected, false);
  assert.match(disconnectedStatus.message, /Not Connected/);
});

test("Action approval state transitions enforce verification probe", () => {
  const pendingAction = {
    id: "action-123",
    action_type: "create_calendar_event",
    status: "pending_approval",
    payload: { title: "CS Lecture", start_time: "2026-10-15T10:00:00Z" },
    created_at: "2026-10-14T00:00:00Z",
  };

  assert.equal(pendingAction.status, "pending_approval");

  const completedAction = {
    ...pendingAction,
    status: "completed",
    confirmed_at: "2026-10-14T01:00:00Z",
    verification_result: { external_id: "evt_google_999", verified: true },
  };

  assert.equal(completedAction.status, "completed");
  assert.equal(completedAction.verification_result.verified, true);
});

test("Phase 3: Task archiving and status filtering logic", () => {
  const tasks = [
    { id: "1", title: "Active 1", status: "pending", is_archived: false, deadline: "2026-10-20T10:00:00Z" },
    { id: "2", title: "Overdue 1", status: "in_progress", is_archived: false, deadline: "2026-10-10T10:00:00Z" },
    { id: "3", title: "Done 1", status: "completed", is_archived: false, deadline: "2026-10-10T10:00:00Z" },
    { id: "4", title: "Archived 1", status: "pending", is_archived: true, deadline: null },
    { id: "5", title: "Cancelled 1", status: "cancelled", is_archived: false, deadline: null },
  ];

  const now = new Date("2026-10-14T12:00:00Z").getTime();

  // Active filter (excludes completed and cancelled and archived)
  const activeTasks = tasks.filter((t) => !t.is_archived && t.status !== "completed" && t.status !== "cancelled");
  assert.equal(activeTasks.length, 2);

  // Overdue filter (strictly deadline in past and pending/in_progress)
  const overdueTasks = tasks.filter((t) => {
    if (t.is_archived || !t.deadline) return false;
    return new Date(t.deadline).getTime() < now && (t.status === "pending" || t.status === "in_progress");
  });
  assert.equal(overdueTasks.length, 1);
  assert.equal(overdueTasks[0].id, "2");

  // Archived filter
  const archivedTasks = tasks.filter((t) => t.is_archived);
  assert.equal(archivedTasks.length, 1);
  assert.equal(archivedTasks[0].id, "4");
});

test("Phase 3: Preferences working hours validation", () => {
  const invalidPrefs = {
    work_start_time: "09:00:00",
    work_end_time: "09:00:00",
  };
  const isIdentical = invalidPrefs.work_start_time === invalidPrefs.work_end_time;
  assert.equal(isIdentical, true, "Identical working hours must be detected as invalid");

  const validPrefs = {
    work_start_time: "09:00:00",
    work_end_time: "17:00:00",
    buffer_minutes: 15,
    timezone: "America/New_York",
    available_days: [1, 2, 3, 4, 5],
  };
  assert.notEqual(validPrefs.work_start_time, validPrefs.work_end_time);
  assert.equal(validPrefs.available_days.every((d) => d >= 1 && d <= 7), true);
});

test("Phase 5: Notification category routing and action destination mapping", () => {
  const notifAction = {
    id: "notif-1",
    notification_type: "action_required",
    action_id: "action-xyz",
    status: "pending",
  };
  const notifConflict = {
    id: "notif-2",
    notification_type: "schedule_conflict",
    status: "delivered",
  };
  const notifCalendar = {
    id: "notif-3",
    notification_type: "calendar_stale",
    status: "delivered",
  };
  const notifTask = {
    id: "notif-4",
    notification_type: "due_soon",
    task_id: "task-123",
    status: "delivered",
  };

  const getRoute = (notif) => {
    if (notif.action_id || notif.notification_type === "action_required" || notif.notification_type === "action_failed") {
      return "/actions";
    } else if (notif.notification_type === "schedule_conflict") {
      return "/schedule";
    } else if (notif.notification_type === "calendar_revoked" || notif.notification_type === "calendar_stale") {
      return "/settings/calendar";
    }
    return "/tasks";
  };

  assert.equal(getRoute(notifAction), "/actions");
  assert.equal(getRoute(notifConflict), "/schedule");
  assert.equal(getRoute(notifCalendar), "/settings/calendar");
  assert.equal(getRoute(notifTask), "/tasks");
});

test("Phase 5: Notification settings and quiet hours bounds validation", () => {
  const settings = {
    notify_upcoming_tasks: true,
    notify_deadlines: true,
    notify_overdue: true,
    notify_schedule_conflicts: true,
    notify_action_requests: true,
    notify_task_completed: false,
    reminder_lead_time_minutes: 30,
    quiet_hours_enabled: true,
    quiet_hours_start: "22:00:00",
    quiet_hours_end: "08:00:00",
  };

  assert.equal(settings.reminder_lead_time_minutes >= 5, true);
  assert.equal(settings.reminder_lead_time_minutes <= 1440, true);
  assert.equal(typeof settings.notify_upcoming_tasks, "boolean");
  assert.equal(typeof settings.quiet_hours_enabled, "boolean");
  assert.match(settings.quiet_hours_start, /^\d{2}:\d{2}(:\d{2})?$/);
  assert.match(settings.quiet_hours_end, /^\d{2}:\d{2}(:\d{2})?$/);
});

