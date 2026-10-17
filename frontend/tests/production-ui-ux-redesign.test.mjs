import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Phase 5A: Absence of Gemini Free Tier labels in user-facing Copilot UI", () => {
  const copilotDrawerPath = path.resolve("frontend/components/copilot/CopilotDrawer.tsx");
  const content = fs.readFileSync(copilotDrawerPath, "utf-8");

  assert.equal(
    content.includes("Gemini Free Tier"),
    false,
    "CopilotDrawer must never display 'Gemini Free Tier' badge"
  );
  assert.equal(
    content.includes("Zero Cost Free Voice"),
    false,
    "CopilotDrawer must not display 'Zero Cost Free Voice' badge"
  );
  assert.equal(
    content.includes("Free Tier Mode"),
    false,
    "CopilotDrawer must not display 'Free Tier Mode'"
  );
});

test("Phase 3: Brand Logo component existence and product name consistency", () => {
  const logoPath = path.resolve("frontend/components/MentorLogo.tsx");
  assert.equal(fs.existsSync(logoPath), true, "MentorLogo.tsx component must exist");

  const logoContent = fs.readFileSync(logoPath, "utf-8");
  assert.equal(logoContent.includes("Mentor"), true, "Must include Mentor brand name");
  assert.equal(logoContent.includes("AI"), true, "Must include AI badge");
});

test("Phase 5B: CopilotMarkdown colorful hierarchy and bold text emphasis", () => {
  const markdownPath = path.resolve("frontend/components/copilot/CopilotMarkdown.tsx");
  const content = fs.readFileSync(markdownPath, "utf-8");

  assert.equal(content.includes("text-indigo-300"), true, "H1 must feature indigo brand accent");
  assert.equal(content.includes("text-sky-300"), true, "H2 must feature sky accent");
  assert.equal(content.includes("text-violet-300"), true, "H3 must feature violet accent");
  assert.equal(content.includes("font-semibold text-white"), true, "Bold text must have high-contrast white text");
});

test("Phase 7: Five-Form-Factor responsive design and dedicated Smartwatch mode", () => {
  const watchPath = path.resolve("frontend/app/watch/page.tsx");
  assert.equal(fs.existsSync(watchPath), true, "Watch companion page /watch must exist");

  const watchContent = fs.readFileSync(watchPath, "utf-8");
  assert.equal(watchContent.includes("Smartwatch Web Companion Mode"), true, "Must explain smartwatch companion role");
  assert.equal(watchContent.includes("bg-black"), true, "Must utilize battery-saving OLED black");
  assert.equal(watchContent.includes("safeFormatTime"), true, "Must format timestamps safely");
});
