import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("Daily Briefing: Quick suggestion sample prompts include briefing triggers", () => {
  const drawerPath = path.resolve(__dirname, "../components/copilot/CopilotDrawer.tsx");
  const content = fs.readFileSync(drawerPath, "utf-8");

  assert.ok(
    content.includes('"Brief me on my day"'),
    "CopilotDrawer must include 'Brief me on my day' in samplePrompts"
  );
  assert.ok(
    content.includes('"What should I focus on first?"'),
    "CopilotDrawer must include 'What should I focus on first?' in samplePrompts"
  );
});

test("Daily Briefing: CopilotDrawer renders dedicated Daily Briefing Card and Recommended Focus", () => {
  const drawerPath = path.resolve(__dirname, "../components/copilot/CopilotDrawer.tsx");
  const content = fs.readFileSync(drawerPath, "utf-8");

  assert.ok(
    content.includes("msg.response?.daily_briefing"),
    "CopilotDrawer must check msg.response?.daily_briefing for rendering"
  );
  assert.ok(
    content.includes("Recommended First Focus"),
    "CopilotDrawer must render 'Recommended First Focus' section"
  );
  assert.ok(
    content.includes("Focus in Daily Planner"),
    "CopilotDrawer must offer quick button to Focus in Daily Planner (/planner)"
  );
  assert.ok(
    content.includes("Study Sessions") && content.includes("Overdue Tasks"),
    "CopilotDrawer must render metrics grid with Study Sessions and Overdue Tasks"
  );
});

test("Daily Briefing: TypeScript types include CopilotDailyBriefing and CopilotRecommendedFocus", () => {
  const typesPath = path.resolve(__dirname, "../lib/types.ts");
  const content = fs.readFileSync(typesPath, "utf-8");

  assert.ok(
    content.includes("export interface CopilotDailyBriefing"),
    "types.ts must export CopilotDailyBriefing"
  );
  assert.ok(
    content.includes("export interface CopilotRecommendedFocus"),
    "types.ts must export CopilotRecommendedFocus"
  );
  assert.ok(
    content.includes("daily_briefing?: CopilotDailyBriefing | null;"),
    "CopilotResponse interface must include optional daily_briefing field"
  );
});

test("Daily Briefing: Deterministic recommendation priority simulation", () => {
  function computeRecommendedFocus({ overdueTasks, scheduledBlocks, upcomingDeadlines, unscheduledTasks }) {
    // 1. Critical Overdue
    const criticalOverdue = overdueTasks.filter(
      (t) => t.priority === "P1" || t.priority === "P2"
    );
    if (criticalOverdue.length > 0) {
      criticalOverdue.sort((a, b) => (a.priority === "P1" ? -1 : 1));
      const top = criticalOverdue[0];
      return {
        action_type: "overdue",
        title: top.title,
        priority: top.priority,
        reason: `Overdue critical task ${top.title}`,
      };
    }

    // 2. Scheduled Block
    if (scheduledBlocks.length > 0) {
      const first = scheduledBlocks[0];
      return {
        action_type: "scheduled_block",
        title: first.title,
        priority: first.priority || "P2",
        reason: `Scheduled study session ${first.title}`,
      };
    }

    // 3. Upcoming Deadline
    if (upcomingDeadlines.length > 0) {
      const first = upcomingDeadlines[0];
      return {
        action_type: "upcoming_deadline",
        title: first.title,
        priority: first.priority || "P2",
        reason: `Approaching deadline ${first.title}`,
      };
    }

    // 4. Backlog
    if (unscheduledTasks.length > 0) {
      const first = unscheduledTasks[0];
      return {
        action_type: "backlog",
        title: first.title,
        priority: first.priority || "P3",
        reason: `Backlog item ${first.title}`,
      };
    }

    return {
      action_type: "all_clear",
      title: "All caught up!",
      reason: "No pending tasks or deadlines.",
    };
  }

  // Case A: P1 Overdue Task present -> picks overdue
  const recA = computeRecommendedFocus({
    overdueTasks: [{ title: "Lab Report", priority: "P1" }],
    scheduledBlocks: [{ title: "Math Session", priority: "P2" }],
    upcomingDeadlines: [{ title: "Essay", priority: "P1" }],
    unscheduledTasks: [],
  });
  assert.equal(recA.action_type, "overdue");
  assert.equal(recA.title, "Lab Report");

  // Case B: No overdue, but scheduled block present -> picks scheduled block
  const recB = computeRecommendedFocus({
    overdueTasks: [],
    scheduledBlocks: [{ title: "Math Session", priority: "P2" }],
    upcomingDeadlines: [{ title: "Essay", priority: "P1" }],
    unscheduledTasks: [],
  });
  assert.equal(recB.action_type, "scheduled_block");
  assert.equal(recB.title, "Math Session");

  // Case C: No overdue, no scheduled block, but upcoming deadline -> picks deadline
  const recC = computeRecommendedFocus({
    overdueTasks: [],
    scheduledBlocks: [],
    upcomingDeadlines: [{ title: "Essay", priority: "P1" }],
    unscheduledTasks: [],
  });
  assert.equal(recC.action_type, "upcoming_deadline");
  assert.equal(recC.title, "Essay");

  // Case D: Everything empty -> all clear
  const recD = computeRecommendedFocus({
    overdueTasks: [],
    scheduledBlocks: [],
    upcomingDeadlines: [],
    unscheduledTasks: [],
  });
  assert.equal(recD.action_type, "all_clear");
  assert.equal(recD.title, "All caught up!");
});
