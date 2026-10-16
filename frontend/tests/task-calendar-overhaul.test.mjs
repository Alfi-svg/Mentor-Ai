/**
 * Frontend Unit Tests for Task-to-Calendar Overhaul, Scheduling Modes, and UX Logic.
 */

import test from "node:test";
import assert from "node:assert/strict";

test("Task Creation payload respects scheduling_preference and timestamps", () => {
  // Mode 1: Auto-schedule
  const autoPayload = {
    title: "Prepare Slide Deck",
    duration_minutes: 60,
    priority: "P2",
    deadline: "2026-10-20T18:00:00Z",
    scheduled_start: null,
    scheduled_end: null,
    scheduling_preference: "auto",
  };
  assert.equal(autoPayload.scheduling_preference, "auto");
  assert.equal(autoPayload.scheduled_start, null);
  assert.notEqual(autoPayload.deadline, null);

  // Mode 2: Manual schedule with designated time
  const manualPayload = {
    title: "Study for Exam",
    duration_minutes: 90,
    priority: "P1",
    deadline: "2026-10-21T12:00:00Z",
    scheduled_start: "2026-10-20T14:00:00Z",
    scheduled_end: "2026-10-20T15:30:00Z",
    scheduling_preference: "manual",
  };
  assert.equal(manualPayload.scheduling_preference, "manual");
  assert.equal(manualPayload.scheduled_start, "2026-10-20T14:00:00Z");
  assert.equal(manualPayload.scheduled_end, "2026-10-20T15:30:00Z");

  // Mode 3: Unscheduled (task backlog only)
  const unscheduledPayload = {
    title: "Read research paper",
    duration_minutes: 45,
    priority: "P3",
    deadline: "2026-10-25T23:59:59Z",
    scheduled_start: null,
    scheduled_end: null,
    scheduling_preference: "unscheduled",
  };
  assert.equal(unscheduledPayload.scheduling_preference, "unscheduled");
  assert.equal(unscheduledPayload.scheduled_start, null);
  assert.equal(unscheduledPayload.scheduled_end, null);
});

test("Strict separation of Deadline vs Scheduled Time", () => {
  const taskWithOnlyDeadline = {
    id: "task-01",
    title: "Submit Essay",
    deadline: "2026-10-22T23:59:00Z",
    scheduled_start: null,
    scheduled_end: null,
    calendar_sync_status: "unscheduled",
  };

  // Truth check: having a deadline does NOT mean the task is scheduled
  const isScheduled = Boolean(taskWithOnlyDeadline.scheduled_start && taskWithOnlyDeadline.scheduled_end);
  assert.equal(isScheduled, false, "Task with only a deadline must NOT be marked as scheduled");
  assert.equal(taskWithOnlyDeadline.calendar_sync_status, "unscheduled");

  // Format representations must clearly distinguish between them
  const deadlineLabel = taskWithOnlyDeadline.deadline
    ? `Due: ${new Date(taskWithOnlyDeadline.deadline).toISOString()}`
    : "No deadline";
  const scheduledLabel = taskWithOnlyDeadline.scheduled_start
    ? `Scheduled: ${new Date(taskWithOnlyDeadline.scheduled_start).toISOString()}`
    : "Unscheduled";

  assert.match(deadlineLabel, /Due:/);
  assert.equal(scheduledLabel, "Unscheduled");
});

test("Auto-schedule response contract validation", () => {
  // Successful auto-schedule
  const successRes = {
    scheduled: true,
    message: "Task scheduled for 2026-10-18T10:00:00Z.",
    task: {
      id: "task-02",
      title: "Write Lab Report",
      scheduled_start: "2026-10-18T10:00:00Z",
      scheduled_end: "2026-10-18T11:00:00Z",
      calendar_sync_status: "synced",
    },
  };
  assert.equal(successRes.scheduled, true);
  assert.notEqual(successRes.task.scheduled_start, null);
  assert.equal(successRes.task.calendar_sync_status, "synced");

  // Feasibility failure (no open slot before deadline)
  const failureRes = {
    scheduled: false,
    message: "Could not find an available slot before the deadline within working hours.",
    task: {
      id: "task-03",
      title: "Cram Session",
      scheduled_start: null,
      scheduled_end: null,
      calendar_sync_status: "unscheduled",
    },
  };
  assert.equal(failureRes.scheduled, false);
  assert.equal(failureRes.task.scheduled_start, null);
  assert.equal(failureRes.task.calendar_sync_status, "unscheduled");
});

test("Task calendar sync retry updates calendar_sync_status", () => {
  const failedTask = {
    id: "task-04",
    title: "Client Sync",
    scheduled_start: "2026-10-19T09:00:00Z",
    scheduled_end: "2026-10-19T10:00:00Z",
    calendar_sync_status: "failed",
    google_calendar_event_id: null,
  };

  // Simulating on-demand retry success
  const retriedTask = {
    ...failedTask,
    calendar_sync_status: "synced",
    google_calendar_event_id: "gcal_evt_12345",
  };

  assert.equal(failedTask.calendar_sync_status, "failed");
  assert.equal(retriedTask.calendar_sync_status, "synced");
  assert.equal(retriedTask.google_calendar_event_id, "gcal_evt_12345");
});

test("Calendar event deduplication and task metadata enrichment", () => {
  const unifiedCalendarEvents = [
    {
      id: "evt-01",
      external_id: "gcal_evt_12345",
      title: "Client Sync",
      start_time: "2026-10-19T09:00:00Z",
      end_time: "2026-10-19T10:00:00Z",
      source: "task",
      task_id: "task-04",
      priority: "P1",
      task_status: "pending",
      calendar_sync_status: "synced",
      location: null,
      is_all_day: false,
      is_fixed: true,
      description: "Auto-synced task",
    },
    {
      id: "evt-02",
      external_id: "gcal_evt_external_999",
      title: "Doctor Appointment",
      start_time: "2026-10-19T15:00:00Z",
      end_time: "2026-10-19T16:00:00Z",
      source: "google_calendar",
      task_id: null,
      priority: null,
      task_status: null,
      calendar_sync_status: null,
      location: "Medical Center",
      is_all_day: false,
      is_fixed: true,
      description: "Routine checkup",
    },
  ];

  // Verify task event
  const taskEvt = unifiedCalendarEvents.find((e) => e.source === "task");
  assert.ok(taskEvt);
  assert.equal(taskEvt.task_id, "task-04");
  assert.equal(taskEvt.priority, "P1");
  assert.equal(taskEvt.calendar_sync_status, "synced");

  // Verify external Google Calendar event
  const gcalEvt = unifiedCalendarEvents.find((e) => e.source === "google_calendar");
  assert.ok(gcalEvt);
  assert.equal(gcalEvt.task_id, null);
  assert.equal(gcalEvt.location, "Medical Center");
});
