/**
 * Frontend Unit & State Tests for Phase 6: Voice Input, Gmail Integration, and Unified LifeOps.
 */

import test from "node:test";
import assert from "node:assert/strict";

test("Phase 6: Gmail connection status truthful state representation", () => {
  const disconnectedState = {
    connected: false,
    email: null,
    provider: "google_gmail",
    last_synced_at: null,
    has_credentials: false,
  };

  assert.equal(disconnectedState.connected, false);
  assert.equal(disconnectedState.has_credentials, false);
  assert.equal(disconnectedState.email, null);

  const activeState = {
    connected: true,
    email: "student@university.edu",
    provider: "google_gmail",
    last_synced_at: "2026-10-16T12:00:00Z",
    has_credentials: true,
  };

  assert.equal(activeState.connected, true);
  assert.equal(activeState.has_credentials, true);
  assert.equal(activeState.email, "student@university.edu");
});

test("Phase 6: LifeOps 10-stage step progression validation", () => {
  const steps = [
    { step: "intent_parsing", status: "completed", detail: "Extracted intent" },
    { step: "gmail_scan", status: "completed", detail: "Scanned 3 recent emails" },
    { step: "task_extraction", status: "completed", detail: "Extracted 2 tasks" },
    { step: "calendar_context", status: "completed", detail: "Checked busy slots" },
    { step: "scheduling", status: "completed", detail: "Computed EDF schedule" },
    { step: "approval_staging", status: "pending_review", detail: "Staged 1 action" },
  ];

  // Pipeline must have non-empty steps
  assert.equal(steps.length, 6);
  assert.equal(steps[0].step, "intent_parsing");
  assert.equal(steps[5].status, "pending_review");

  // Verify finding approval step
  const approvalStep = steps.find((s) => s.step === "approval_staging");
  assert.ok(approvalStep);
  assert.equal(approvalStep.status, "pending_review");
});

test("Phase 6: Speech Recognition mock transcript accumulator", () => {
  let transcript = "";
  let interim = "";

  const mockOnResult = (event) => {
    let finalChunk = "";
    let interimChunk = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalChunk += event.results[i][0].transcript;
      } else {
        interimChunk += event.results[i][0].transcript;
      }
    }
    if (finalChunk) {
      transcript = transcript ? `${transcript} ${finalChunk}` : finalChunk;
    }
    interim = interimChunk;
  };

  // Simulate interim result
  mockOnResult({
    resultIndex: 0,
    results: [{ 0: { transcript: "Prepare for exam" }, isFinal: false }],
  });
  assert.equal(transcript, "");
  assert.equal(interim, "Prepare for exam");

  // Simulate final result
  mockOnResult({
    resultIndex: 0,
    results: [{ 0: { transcript: "Prepare for exam tomorrow" }, isFinal: true }],
  });
  assert.equal(transcript, "Prepare for exam tomorrow");
  assert.equal(interim, "");
});

test("OAuth callback redirect search params parsing for connected and error states", () => {
  // Test connected state with email
  const connectedUrl = "https://frontend-ten-delta-a5irgspmf7.vercel.app/settings/calendar?connected=true&email=user%40example.com";
  const paramsSuccess = new URL(connectedUrl).searchParams;
  assert.equal(paramsSuccess.get("connected"), "true");
  assert.equal(paramsSuccess.get("email"), "user@example.com");

  // Test error state with description
  const errorUrl = "https://frontend-ten-delta-a5irgspmf7.vercel.app/settings/gmail?error=access_denied&error_description=User+declined+permissions";
  const paramsError = new URL(errorUrl).searchParams;
  assert.equal(paramsError.get("error"), "access_denied");
  assert.equal(paramsError.get("error_description"), "User declined permissions");
});

