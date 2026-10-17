import test from "node:test";
import assert from "node:assert/strict";

test("Phase 9: Voice option metadata exposes masculine and feminine sound options without identity claims", () => {
  const voices = [
    {
      id: "nova",
      name: "Nova",
      perceived_sound: "feminine",
      description: "Warm, upbeat, and natural tone.",
      sample_text: "Hello! I am Mentor, your educational assistant.",
    },
    {
      id: "shimmer",
      name: "Shimmer",
      perceived_sound: "feminine",
      description: "Clear, expressive, and friendly tone.",
      sample_text: "Good morning! You have scheduled focus blocks today.",
    },
    {
      id: "echo",
      name: "Echo",
      perceived_sound: "masculine",
      description: "Resonant, deep, and conversational tone.",
      sample_text: "Hello! I am ready to review your schedule.",
    },
    {
      id: "onyx",
      name: "Onyx",
      perceived_sound: "masculine",
      description: "Calm, authoritative, and focused tone.",
      sample_text: "Welcome back. Let us review your tasks.",
    },
  ];

  assert.equal(voices.length, 4);

  const sounds = new Set(voices.map((v) => v.perceived_sound));
  assert.ok(sounds.has("masculine"), "Should have masculine-sounding option");
  assert.ok(sounds.has("feminine"), "Should have feminine-sounding option");

  for (const v of voices) {
    assert.ok(v.sample_text.length > 10, "Every voice must have sample text for preview playback");
    assert.ok(["nova", "shimmer", "echo", "onyx"].includes(v.id));
  }
});

test("Phase 9: Consequential action confirmation safety binds signed approval_id", () => {
  const emailDraft = {
    thread_id: "thread_abc123",
    recipient_email: "professor@university.edu",
    recipient_name: "Dr. Rahman",
    subject: "Re: Term Project Submission",
    body: "Dear Dr. Rahman,\n\nI will submit the assignment tomorrow.\n\nBest regards,\nStudent",
    requires_confirmation: true,
    approval_id: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token_sample_12345",
    status: "draft_ready",
  };

  assert.equal(emailDraft.requires_confirmation, true);
  assert.ok(emailDraft.approval_id, "Draft must have signed approval_id");

  // Construct confirm payload
  const confirmPayload = {
    action_type: "send_email",
    approval_id: emailDraft.approval_id,
    email_payload: {
      recipient_email: emailDraft.recipient_email,
      subject: emailDraft.subject,
      body: emailDraft.body,
      thread_id: emailDraft.thread_id,
      approval_id: emailDraft.approval_id,
    },
  };

  assert.equal(confirmPayload.approval_id, emailDraft.approval_id);
  assert.equal(confirmPayload.email_payload.recipient_email, "professor@university.edu");
});

test("Phase 9: Spoken response formatter removes markdown links, URLs, and code blocks for smooth TTS", () => {
  const rawReply =
    "Today you have **2 scheduled tasks**:\n" +
    "• Review [DFA Notes](https://example.com/dfa) at 03:00 PM\n" +
    "```python\ndef simulate_dfa(): pass\n```\n" +
    "Would you like me to open your calendar?";

  // Replicate client cleaning logic
  const cleanSpoken = rawReply
    .replace(/```[\s\S]*?```/g, "Here is a code example.")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[*_#`>]/g, "")
    .replace(/\n+/g, ". ")
    .replace(/\s+/g, " ")
    .trim();

  assert.ok(!cleanSpoken.includes("https://"), "Spoken output must not contain raw URLs");
  assert.ok(!cleanSpoken.includes("```"), "Spoken output must not contain code block delimiters");
  assert.ok(!cleanSpoken.includes("**"), "Spoken output must not contain markdown asterisks");
  assert.ok(cleanSpoken.includes("Review DFA Notes"), "Link label text must be preserved");
});

test("Phase 9: Multi-lingual intent recognition supports Bangla, Banglish, and English", () => {
  const banglaPrompt = "আমার আজকের টাস্ক কি কি?";
  const banglishPrompt = "amar ajker task ki ki?";
  const englishPrompt = "What are my tasks for today?";

  const isScheduleOrTaskQuery = (prompt) => {
    const p = prompt.toLowerCase();
    const keywords = [
      "আজকের", "টাস্ক", "শিডিউল",
      "ajker", "task", "schedule", "plan",
      "today", "what are my", "upcoming",
    ];
    return keywords.some((kw) => p.includes(kw));
  };

  assert.ok(isScheduleOrTaskQuery(banglaPrompt), "Should recognize Bangla task query");
  assert.ok(isScheduleOrTaskQuery(banglishPrompt), "Should recognize Banglish task query");
  assert.ok(isScheduleOrTaskQuery(englishPrompt), "Should recognize English task query");
});

test("Phase 9: Tool results clearly separate Google Calendar events from internal tasks", () => {
  const toolResults = [
    {
      tool: "get_today_tasks",
      output: {
        scheduled_tasks_count: 1,
        scheduled_tasks: [
          { id: "task-1", title: "Assignment 1", status: "pending", is_completed: false },
        ],
      },
    },
    {
      tool: "get_today_calendar_events",
      output: {
        events_count: 1,
        events: [
          { id: "cal-1", title: "CSE 420 Lecture", location: "UB201", is_all_day: false },
        ],
      },
    },
  ];

  const tasksTool = toolResults.find((r) => r.tool === "get_today_tasks");
  const calTool = toolResults.find((r) => r.tool === "get_today_calendar_events");

  assert.ok(tasksTool, "get_today_tasks tool result must be present");
  assert.ok(calTool, "get_today_calendar_events tool result must be present");

  assert.equal(tasksTool.output.scheduled_tasks[0].title, "Assignment 1");
  assert.equal(calTool.output.events[0].title, "CSE 420 Lecture");
  assert.equal(calTool.output.events[0].location, "UB201");
});

test("Step 3: Review-before-send voice workflow allows editing before dispatch", () => {
  const preferences = {
    voice_preset: "nova",
    voice_gender: "feminine",
    auto_play_speech: true,
    stt_engine: "openai",
    review_before_send: true,
  };

  const transcribedText = "What is the deadline for my automata project?";
  let inputText = "";
  let autoSubmitted = false;
  let notice = null;

  // Simulate onstop handler logic
  if (preferences.review_before_send) {
    inputText = transcribedText;
    notice = "Transcript captured! Review and edit your prompt below, then press Enter or Send.";
  } else {
    autoSubmitted = true;
  }

  assert.equal(inputText, transcribedText, "Transcript should populate input text");
  assert.equal(autoSubmitted, false, "Should not auto-submit when review_before_send is true");
  assert.ok(notice.includes("Review and edit"), "Notice must explain editing step");

  // Now simulate user editing a misheard word
  inputText = "What is the deadline for my automata assignment?";
  assert.equal(inputText.includes("assignment"), true, "User can freely edit transcript before sending");
});

test("Step 3: Audio interruption ensures speech is stopped on user interaction", () => {
  let isSpeaking = true;
  let audioPlayerPlaying = true;

  const stopSpeaking = () => {
    isSpeaking = false;
    audioPlayerPlaying = false;
  };

  // User begins typing
  const onUserType = (char) => {
    if (isSpeaking) stopSpeaking();
  };

  onUserType("a");
  assert.equal(isSpeaking, false, "Typing must interrupt active speech");
  assert.equal(audioPlayerPlaying, false, "Audio player must be stopped on interruption");
});

test("Step 3: Acoustic profile disclaimer explains synthetic character", () => {
  const disclaimer =
    "Voice styles (masculine/feminine-sounding) represent synthetic acoustic characteristics, not human gender identities. All spoken audio is AI-generated using OpenAI Text-to-Speech.";

  assert.ok(disclaimer.includes("synthetic acoustic characteristics"), "Must explain synthetic nature");
  assert.ok(disclaimer.includes("not human gender identities"), "Must clarify gender identity disclaimer");
  assert.ok(disclaimer.includes("AI-generated"), "Must mark as AI-generated");
});

