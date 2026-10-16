/**
 * Unit & Contract Tests for Calendar Workspace, Gmail Workspace & Task-to-Calendar Sync.
 */

import test from "node:test";
import assert from "node:assert/strict";

test("Calendar Workspace: Distinguish scheduled tasks from external Google events", () => {
  const events = [
    {
      id: "ev-task-1",
      external_id: "mock_evt_123",
      title: "Write OS Lab Report",
      source: "task",
      start_time: "2026-10-16T10:00:00Z",
      end_time: "2026-10-16T11:30:00Z",
      is_all_day: false,
      is_fixed: true,
      location: null,
    },
    {
      id: "ev-gcal-1",
      external_id: "gcal_evt_456",
      title: "Physics Department Colloquium",
      source: "google_calendar",
      start_time: "2026-10-16T14:00:00Z",
      end_time: "2026-10-16T15:00:00Z",
      is_all_day: false,
      is_fixed: true,
      location: "Room 101, Science Hall",
    },
  ];

  const taskEvents = events.filter((e) => e.source === "task");
  const gcalEvents = events.filter((e) => e.source === "google_calendar");

  assert.equal(taskEvents.length, 1);
  assert.equal(taskEvents[0].title, "Write OS Lab Report");
  assert.equal(gcalEvents.length, 1);
  assert.equal(gcalEvents[0].location, "Room 101, Science Hall");
});

test("Calendar Task Sync: Title mutation to [DONE] on task completion", () => {
  const originalTask = {
    title: "Implement Virtual Memory Paging",
    status: "in_progress",
    scheduled_start: "2026-10-16T09:00:00Z",
    scheduled_end: "2026-10-16T11:00:00Z",
  };

  const getCalendarTitle = (task) => {
    return task.status === "completed" ? `[DONE] ${task.title}` : task.title;
  };

  assert.equal(getCalendarTitle(originalTask), "Implement Virtual Memory Paging");

  const completedTask = { ...originalTask, status: "completed" };
  assert.equal(getCalendarTitle(completedTask), "[DONE] Implement Virtual Memory Paging");
});

test("Calendar Task Sync: Status state machine transitions", () => {
  const allowedStatuses = ["unsynced", "pending", "synced", "failed"];
  
  const validateSyncStatus = (status) => allowedStatuses.includes(status);

  assert.equal(validateSyncStatus("synced"), true);
  assert.equal(validateSyncStatus("failed"), true);
  assert.equal(validateSyncStatus("unknown_status"), false);
});

test("Gmail Workspace: Folder filtering and label evaluation", () => {
  const messages = [
    {
      id: "msg-1",
      subject: "Algorithms Midterm Announcement",
      labels: ["INBOX", "UNREAD"],
      is_starred: true,
    },
    {
      id: "msg-2",
      subject: "Operating Systems Assignment 3 Due",
      labels: ["INBOX"],
      is_starred: false,
    },
    {
      id: "msg-3",
      subject: "Draft: Email to Professor",
      labels: ["DRAFT"],
      is_starred: false,
    },
  ];

  // Filter INBOX
  const inbox = messages.filter((m) => m.labels.includes("INBOX"));
  assert.equal(inbox.length, 2);

  // Filter STARRED
  const starred = messages.filter((m) => m.is_starred);
  assert.equal(starred.length, 1);
  assert.equal(starred[0].id, "msg-1");

  // Filter DRAFTS
  const drafts = messages.filter((m) => m.labels.includes("DRAFT"));
  assert.equal(drafts.length, 1);
  assert.equal(drafts[0].subject, "Draft: Email to Professor");
});

test("Gmail Workspace: Consequential action confirmation safety", () => {
  let confirmationRequired = true;
  let emailTransmitted = false;

  const attemptSendWithoutConfirmation = () => {
    if (confirmationRequired) {
      throw new Error("Consequential action requires explicit human confirmation.");
    }
    emailTransmitted = true;
  };

  assert.throws(attemptSendWithoutConfirmation, /requires explicit human confirmation/);
  assert.equal(emailTransmitted, false);

  // When human confirms:
  confirmationRequired = false;
  attemptSendWithoutConfirmation();
  assert.equal(emailTransmitted, true);
});
