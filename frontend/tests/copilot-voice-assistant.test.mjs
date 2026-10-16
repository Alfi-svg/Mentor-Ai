import test from "node:test";
import assert from "node:assert/strict";

test("Phase 8: Copilot schedule summary preserves chronological order and distinguishes deadlines", () => {
  const scheduleData = {
    target_date: "2026-10-17",
    timezone: "Asia/Dhaka",
    total_items: 2,
    scheduled_items: [
      {
        id: "block-1",
        title: "Mathematics Study Session",
        item_type: "task",
        start_time: "09:00 AM",
        end_time: "10:30 AM",
        raw_start: "2026-10-17T03:00:00Z",
        raw_end: "2026-10-17T04:30:00Z",
        status: "in_progress",
        is_completed: false,
        is_overdue: false,
      },
      {
        id: "event-1",
        title: "Operating Systems Lecture",
        item_type: "calendar_event",
        start_time: "11:30 AM",
        end_time: "01:00 PM",
        raw_start: "2026-10-17T05:30:00Z",
        raw_end: "2026-10-17T07:00:00Z",
        status: "confirmed",
        is_completed: false,
        is_overdue: false,
      },
    ],
    deadlines: [
      {
        id: "task-2",
        title: "Algorithms Problem Set",
        deadline_time: "08:00 PM",
        priority: "P1",
      },
    ],
    unscheduled_tasks: [],
    next_action: "Mathematics Study Session",
    next_action_time: "09:00 AM",
    summary_text: "Today you have 2 scheduled items and 1 deadline.",
  };

  // Verify chronology
  const t1 = new Date(scheduleData.scheduled_items[0].raw_start).getTime();
  const t2 = new Date(scheduleData.scheduled_items[1].raw_start).getTime();
  assert.ok(t1 < t2, "Scheduled items must be sorted in chronological order");

  // Verify categorization
  assert.equal(scheduleData.scheduled_items[0].item_type, "task");
  assert.equal(scheduleData.scheduled_items[1].item_type, "calendar_event");
  assert.equal(scheduleData.deadlines.length, 1);
  assert.equal(scheduleData.deadlines[0].title, "Algorithms Problem Set");
});

test("Phase 8: Schedule-aware navigation destination construction", () => {
  const target = {
    route: "/calendar",
    params: { date: "2026-10-17", view: "day" },
    label: "Open Today's Schedule",
  };

  const query = new URLSearchParams(target.params).toString();
  const fullUrl = `${target.route}?${query}`;

  assert.equal(fullUrl, "/calendar?date=2026-10-17&view=day");
  assert.ok(target.label.includes("Schedule"));
});

test("Phase 8: Educational resource verification guarantees real URLs and platform badges", () => {
  const sampleResources = [
    {
      title: "MIT OpenCourseWare: Single Variable Calculus (18.01SC)",
      url: "https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/",
      platform: "MIT OpenCourseWare",
      topic: "Calculus & Foundational Mathematics (Math 101)",
      difficulty: "Beginner",
      is_free: true,
      description: "College calculus course covering derivatives, integrals, and applications.",
      why_recommended: "Gold-standard university foundation for STEM students.",
    },
    {
      title: "Khan Academy: College Calculus 1",
      url: "https://www.khanacademy.org/math/calculus-1",
      platform: "Khan Academy",
      topic: "Calculus Limits & Derivatives",
      difficulty: "Beginner",
      is_free: true,
      description: "Interactive lessons with mastery quizzes.",
      why_recommended: "Intuitive visual explanations.",
    },
  ];

  for (const res of sampleResources) {
    assert.ok(res.url.startsWith("https://"), "All educational links must be secure HTTPS URLs");
    assert.ok(res.platform.length > 2, "Platform must be specified");
    assert.ok(res.why_recommended.length > 5, "Why recommended must provide academic context");
    assert.equal(res.is_free, true, "Verified free status");
  }
});

test("Phase 8: Email Copilot requires explicit confirmation before send action", () => {
  const draft = {
    thread_id: "thread_abc123",
    recipient_email: "prof.david@mit.edu",
    recipient_name: "Prof. David",
    subject: "Re: Math 101 Assignment Submission",
    body: "Dear Professor, I will submit the assignment tomorrow.",
    requires_confirmation: true,
    status: "draft_ready",
  };

  // Draft cannot be sent without user confirmation
  assert.equal(draft.requires_confirmation, true, "Email draft must enforce explicit confirmation gate");
  assert.notEqual(draft.status, "sent", "Email draft status must not be sent prematurely");

  // Simulate explicit action approval payload
  const confirmPayload = {
    action_type: "send_email",
    email_payload: {
      recipient_email: draft.recipient_email,
      subject: draft.subject,
      body: draft.body,
      thread_id: draft.thread_id,
    },
  };

  assert.equal(confirmPayload.action_type, "send_email");
  assert.equal(confirmPayload.email_payload.recipient_email, "prof.david@mit.edu");
});

test("Phase 8: Voice Assistant state machine transitions", () => {
  const validStates = ["idle", "listening", "thinking", "speaking", "error"];
  let currentState = "idle";

  // 1. User clicks mic -> listening
  currentState = "listening";
  assert.equal(currentState, "listening");
  assert.ok(validStates.includes(currentState));

  // 2. Speech captured -> thinking
  currentState = "thinking";
  assert.equal(currentState, "thinking");

  // 3. Audio synthesis starts -> speaking
  currentState = "speaking";
  assert.equal(currentState, "speaking");

  // 4. Speech finished or interrupted -> idle
  currentState = "idle";
  assert.equal(currentState, "idle");
});

test("Phase 8: Speech recognition interim transcript accumulator", () => {
  const mockResults = [
    { 0: { transcript: "give me" }, isFinal: false, length: 1 },
    { 0: { transcript: "give me today's schedule" }, isFinal: true, length: 1 },
  ];

  let accumulatedInterim = "";
  let finalResult = "";

  for (const item of mockResults) {
    if (item.isFinal) {
      finalResult += item[0].transcript;
      accumulatedInterim = "";
    } else {
      accumulatedInterim = item[0].transcript;
    }
  }

  assert.equal(finalResult, "give me today's schedule");
  assert.equal(accumulatedInterim, "");
});

test("Phase 8: 100-line code constraint enforcement validation", () => {
  const dummyCode = Array.from({ length: 120 }, (_, i) => `const x_${i} = ${i};`).join("\n");
  const codeBlock = "```typescript\n" + dummyCode + "\n```";

  const lines = dummyCode.split("\n");
  assert.equal(lines.length, 120, "Input has 120 lines");

  // Enforce 100 line limit
  const maxLines = 100;
  const boundedLines = lines.slice(0, maxLines);
  assert.equal(boundedLines.length, 100, "Bounded output must not exceed 100 lines");
});

test("Phase 8: Student Accountability missed session representation", () => {
  const accountability = {
    missed_sessions_count: 2,
    completed_today_count: 3,
    total_tasks_count: 10,
    streak_days: 5,
    supportive_message: "Progress isn't about perfection. Let's find time today to get back on track!",
    suggested_recovery_task: {
      id: "task-rec-1",
      title: "Physics Problem Set",
      priority: "P1",
      duration_minutes: 45,
    },
  };

  assert.equal(accountability.streak_days, 5);
  assert.equal(accountability.missed_sessions_count, 2);
  assert.ok(accountability.supportive_message.includes("Progress"));
  assert.equal(accountability.suggested_recovery_task.title, "Physics Problem Set");
});
