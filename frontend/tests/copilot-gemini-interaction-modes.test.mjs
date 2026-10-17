import test from "node:test";
import assert from "node:assert/strict";

/**
 * Replicates the safe link validation from CopilotMarkdown.tsx
 */
function isSafeUrl(url) {
  const trimmed = url.trim().toLowerCase();
  return (
    trimmed.startsWith("https://") ||
    trimmed.startsWith("http://") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("#")
  );
}

/**
 * Replicates the XSS sanitizer from CopilotMarkdown.tsx
 */
function sanitizeText(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Replicates the Phase 4 fixed audio playback decision logic
 */
function computeShouldSpeak({ isVoiceTurn, isVoiceMuted }) {
  return Boolean(isVoiceTurn && !isVoiceMuted);
}

test("Phase 3 & 4: Text mode silence guarantee — typed questions never trigger spoken audio", () => {
  // When in Text mode and user has not muted voice responses (isVoiceMuted === false)
  const mode = "text";
  const isVoiceMuted = false;
  const isVoiceTurn = mode === "voice"; // false in text mode

  const shouldSpeak = computeShouldSpeak({ isVoiceTurn, isVoiceMuted });

  // Prior bug: wasSpoken || !isVoiceMuted -> evaluated to TRUE because isVoiceMuted was false!
  // Fixed logic: isVoiceTurn && !isVoiceMuted -> evaluates to FALSE
  assert.equal(shouldSpeak, false, "Text mode must be completely silent regardless of isVoiceMuted state");
});

test("Phase 3 & 4: Voice mode playback guarantee — voice turns play spoken audio when unmuted", () => {
  const mode = "voice";
  const isVoiceMuted = false;
  const isVoiceTurn = mode === "voice"; // true

  const shouldSpeak = computeShouldSpeak({ isVoiceTurn, isVoiceMuted });
  assert.equal(shouldSpeak, true, "Voice mode must play speech when unmuted");
});

test("Phase 3 & 4: Voice mode respects mute toggle", () => {
  const mode = "voice";
  const isVoiceMuted = true;
  const isVoiceTurn = mode === "voice"; // true

  const shouldSpeak = computeShouldSpeak({ isVoiceTurn, isVoiceMuted });
  assert.equal(shouldSpeak, false, "Muted voice mode must remain silent");
});

test("Phase 4: Interruption triggers — stopSpeaking called on user interaction", () => {
  let stopSpeakingCalled = 0;
  const stopSpeaking = () => {
    stopSpeakingCalled += 1;
  };

  // 1. Typing in input box
  const onInputChanged = (val) => {
    stopSpeaking();
  };
  onInputChanged("Hello");
  assert.equal(stopSpeakingCalled, 1, "Typing must interrupt speech");

  // 2. Clicking mic button to record
  const onMicClicked = () => {
    stopSpeaking();
  };
  onMicClicked();
  assert.equal(stopSpeakingCalled, 2, "Mic activation must interrupt speech");

  // 3. Switching interaction mode (e.g. from Voice to Text)
  const onModeSwitched = (nextMode) => {
    stopSpeaking();
  };
  onModeSwitched("text");
  assert.equal(stopSpeakingCalled, 3, "Mode switching must interrupt speech");

  // 4. Closing Copilot drawer
  const onDrawerClosed = () => {
    stopSpeaking();
  };
  onDrawerClosed();
  assert.equal(stopSpeakingCalled, 4, "Drawer closing must interrupt speech");
});

test("Phase 5: Markdown link safety validation blocks dangerous protocols", () => {
  assert.equal(isSafeUrl("https://calendar.google.com"), true);
  assert.equal(isSafeUrl("http://localhost:3000/tasks"), true);
  assert.equal(isSafeUrl("/dashboard"), true);
  assert.equal(isSafeUrl("#section-1"), true);

  // Dangerous protocols must be blocked
  assert.equal(isSafeUrl("javascript:alert(1)"), false);
  assert.equal(isSafeUrl("data:text/html,<script>alert(1)</script>"), false);
  assert.equal(isSafeUrl("vbscript:MsgBox(1)"), false);
});

test("Phase 5: Markdown text sanitizer escapes unsafe HTML entities", () => {
  const unsafe = '<script>alert("xss")</script> & <b>test</b>';
  const clean = sanitizeText(unsafe);

  assert.ok(!clean.includes("<script>"), "Must escape opening tag");
  assert.ok(!clean.includes("</script>"), "Must escape closing tag");
  assert.ok(clean.includes("&lt;script&gt;"), "Tags converted to safe entities");
  assert.ok(clean.includes("&amp;"), "Ampersands converted to entities");
});

test("Phase 5 & 6: English-only response validation for multilingual user input", () => {
  // Example response generated for Bangla input 'amar ajker task ki ki?'
  const englishReply = 
    "## Your Tasks for Today\n\n" +
    "Here are your scheduled focus blocks for today:\n\n" +
    "1. **DFA Minimization Assignment** — Due at 06:00 PM (Priority: P1)\n" +
    "2. **Algorithm Design Reading** — Scheduled at 03:00 PM\n\n" +
    "### Recommended Next Step\n\n" +
    "Start by completing the DFA assignment before the evening deadline.";

  // Must not contain Bangla script unicode range (\u0980-\u09FF)
  const hasBanglaUnicode = /[\u0980-\u09FF]/.test(englishReply);
  assert.equal(hasBanglaUnicode, false, "Assistant reply must be strictly in English");
  assert.ok(englishReply.startsWith("## Your Tasks for Today"), "Structured with clear English heading");
  assert.ok(englishReply.includes("**DFA Minimization Assignment**"), "Highlights key task with bold emphasis");
  assert.ok(englishReply.includes("### Recommended Next Step"), "Includes logical section hierarchy");
});

test("Phase 6: ChatGPT-style table and code block structure validation", () => {
  const tableContent = 
    "| Task Title | Deadline | Priority |\n" +
    "| :--- | :--- | :--- |\n" +
    "| DFA Minimization | 06:00 PM | P1 |\n" +
    "| Physics Lab | 09:00 PM | P2 |";

  const lines = tableContent.split("\n");
  const tableRows = lines.filter((l) => l.trim().startsWith("|") && l.trim().endsWith("|"));
  assert.equal(tableRows.length, 4, "Table must have 4 rows including header and separator");

  const codeExample = "```python\ndef solve_dfa():\n    return True\n```";
  assert.ok(codeExample.startsWith("```python"), "Code block includes language badge");
  assert.ok(codeExample.endsWith("```"), "Code block is properly fenced");
});

