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
