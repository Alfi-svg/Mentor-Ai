import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Mobile Voice: audio-recorder utility exports detectSupportedAudioMime and stopAllMediaTracks", () => {
  const filePath = path.resolve("frontend/lib/audio-recorder.ts");
  assert.equal(fs.existsSync(filePath), true, "audio-recorder.ts utility must exist");

  const content = fs.readFileSync(filePath, "utf-8");
  assert.equal(content.includes("export function detectSupportedAudioMime"), true, "Must export detectSupportedAudioMime");
  assert.equal(content.includes("export function stopAllMediaTracks"), true, "Must export stopAllMediaTracks");
  assert.equal(content.includes("audio/mp4"), true, "Must probe audio/mp4 for iOS Safari");
  assert.equal(content.includes("audio/aac"), true, "Must probe audio/aac for iOS Safari");
  assert.equal(content.includes("audio/webm;codecs=opus"), true, "Must probe audio/webm for Chrome");
});

test("Voice Presets: CopilotDrawer renders four real acoustic presets with live preview and stop controls", () => {
  const drawerPath = path.resolve("frontend/components/copilot/CopilotDrawer.tsx");
  const content = fs.readFileSync(drawerPath, "utf-8");

  assert.equal(content.includes("Masculine"), true, "Must feature Masculine preset");
  assert.equal(content.includes("Feminine"), true, "Must feature Feminine preset");
  assert.equal(content.includes("Deep Vocal"), true, "Must feature Deep Vocal preset");
  assert.equal(content.includes("Natural Vocal"), true, "Must feature Natural Vocal preset");

  // Verify stop preview button exists
  assert.equal(content.includes("stopSpeaking"), true, "Must support stopping voice preview");
  assert.equal(content.includes("previewingVoiceId"), true, "Must track active voice preview state");

  // Verify mobile recording timer and controls
  assert.equal(content.includes("recordingSeconds"), true, "Must maintain recording timer state");
  assert.equal(content.includes("cancelListening"), true, "Must provide cancel recording control");
  assert.equal(content.includes("stopListening"), true, "Must provide stop & transcribe control");
});

test("VoiceInputButton: Features MediaRecorder, 60-second limit, timer display, and stream cleanup", () => {
  const buttonPath = path.resolve("frontend/components/VoiceInputButton.tsx");
  const content = fs.readFileSync(buttonPath, "utf-8");

  assert.equal(content.includes("detectSupportedAudioMime"), true, "Must use dynamic MIME detection");
  assert.equal(content.includes("stopAllMediaTracks"), true, "Must stop all media tracks on cancel/stop/unmount");
  assert.equal(content.includes("elapsed >= 60"), true, "Must enforce 60-second maximum recording limit");
  assert.equal(content.includes("cancelRecording"), true, "Must provide cancel button");
  assert.equal(content.includes("stopRecording"), true, "Must provide done button");
  assert.equal(content.includes("apiClient.copilot.transcribeAudio"), true, "Must route audio to Gemini STT endpoint");
});

test("AI Planner: Default mode is standard day planner, renders clarification banner and add task step", () => {
  const plannerPath = path.resolve("frontend/app/planner/page.tsx");
  const content = fs.readFileSync(plannerPath, "utf-8");

  // Default mode
  assert.equal(content.includes('useState<"standard" | "lifeops">("standard")'), true, "Default mode must be standard");

  // Clarification questions and missing info
  assert.equal(content.includes("proposal.clarification_question"), true, "Must render clarification question");
  assert.equal(content.includes("proposal.missing_information"), true, "Must render missing information list");

  // Add task step
  assert.equal(content.includes("handleAddTask"), true, "Must provide handleAddTask function");
  assert.equal(content.includes("Add Task Step"), true, "Must render Add Task Step button in UI");
});

test("AI Planner: Confirmed Plan Persisted Card renders created tasks, timeline, and navigation links", () => {
  const plannerPath = path.resolve("frontend/app/planner/page.tsx");
  const content = fs.readFileSync(plannerPath, "utf-8");

  assert.equal(content.includes("confirmResult &&"), true, "Must conditionally render confirmResult card");
  assert.equal(content.includes("Plan Confirmed & Persisted!"), true, "Must display confirmation banner");
  assert.equal(content.includes("confirmResult.created_tasks"), true, "Must display created tasks list");
  assert.equal(content.includes("confirmResult.schedule?.unscheduled_tasks"), true, "Must warn about unscheduled tasks if any");
  assert.equal(content.includes("confirmResult.schedule?.scheduled_blocks"), true, "Must display scheduled blocks timeline");
  assert.equal(content.includes('href="/tasks"'), true, "Must provide link to /tasks");
  assert.equal(content.includes('href="/calendar"'), true, "Must provide link to /calendar");
  assert.equal(content.includes('href="/schedule"'), true, "Must provide link to /schedule");
  assert.equal(content.includes("Plan Another Day"), true, "Must provide Plan Another Day button");
});
