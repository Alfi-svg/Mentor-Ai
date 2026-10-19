import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

// Support running both from root and from within frontend/
const REPO_ROOT = process.cwd().endsWith("frontend") ? path.resolve(process.cwd(), "..") : process.cwd();
const FRONTEND_DIR = path.join(REPO_ROOT, "frontend");

test("Task-to-Calendar Sync: Types schema includes is_deadline field", () => {
  const typesContent = fs.readFileSync(path.join(FRONTEND_DIR, "lib/types.ts"), "utf-8");
  assert.equal(
    typesContent.includes("is_deadline?: boolean"),
    true,
    "CalendarEvent interface must include is_deadline?: boolean"
  );
});

test("API Client: Dynamic base URL supports local and cloud Render URL", () => {
  const apiClientContent = fs.readFileSync(path.join(FRONTEND_DIR, "lib/api-client.ts"), "utf-8");
  assert.equal(
    apiClientContent.includes("mentor-ai-api-onzd.onrender.com"),
    true,
    "apiClient must include cloud production fallback for hosted Vercel deployments"
  );
  assert.equal(
    apiClientContent.includes("getUnscheduledTasks()"),
    true,
    "apiClient must expose getUnscheduledTasks() method"
  );
});

test("Zero Native Popups: No window.confirm() in active pages", () => {
  const pages = [
    "app/calendar/page.tsx",
    "app/tasks/page.tsx",
    "app/gmail/page.tsx",
    "app/planner/page.tsx",
  ];

  for (const pageRel of pages) {
    const pageContent = fs.readFileSync(path.join(FRONTEND_DIR, pageRel), "utf-8");
    assert.equal(
      pageContent.includes("confirm("),
      false,
      `Native confirm() must be removed from ${pageRel}`
    );
    assert.equal(
      pageContent.includes("alert("),
      false,
      `Native alert() must be removed from ${pageRel}`
    );
  }
});

test("Accessible UI Dialogs: Modal component has accessibility attributes and Escape key handling", () => {
  const modalContent = fs.readFileSync(path.join(FRONTEND_DIR, "components/ui/Modal.tsx"), "utf-8");
  assert.equal(modalContent.includes('role="dialog"'), true, "Modal must define role='dialog'");
  assert.equal(modalContent.includes('aria-modal="true"'), true, "Modal must define aria-modal='true'");
  assert.equal(modalContent.includes('e.key === "Escape"'), true, "Modal must close on Escape key");
  assert.equal(modalContent.includes("document.body.style.overflow"), true, "Modal must lock body scroll");
});

test("Accessible UI Dialogs: ConfirmDialog provides danger/warning/primary variants", () => {
  const confirmContent = fs.readFileSync(path.join(FRONTEND_DIR, "components/ui/ConfirmDialog.tsx"), "utf-8");
  assert.equal(confirmContent.includes("ConfirmDialogProps"), true, "ConfirmDialog must export props interface");
  assert.equal(confirmContent.includes("variant"), true, "ConfirmDialog must support variants");
  assert.equal(confirmContent.includes("isLoading"), true, "ConfirmDialog must support loading state");
});

test("Toast Notifications: ToastProvider exports useToast with success, error, warning, info", () => {
  const toastContent = fs.readFileSync(path.join(FRONTEND_DIR, "components/ui/ToastProvider.tsx"), "utf-8");
  assert.equal(toastContent.includes("export function useToast"), true, "Must export useToast hook");
  assert.equal(toastContent.includes("aria-live="), true, "Toast container must have aria-live region");
  assert.equal(toastContent.includes("success"), true, "Must support success toast");
  assert.equal(toastContent.includes("error"), true, "Must support error toast");
});

test("Error State: ErrorState component provides retry action and diagnostic toggle", () => {
  const errorContent = fs.readFileSync(path.join(FRONTEND_DIR, "components/ui/ErrorState.tsx"), "utf-8");
  assert.equal(errorContent.includes("onRetry"), true, "ErrorState must accept onRetry callback");
  assert.equal(errorContent.includes("details"), true, "ErrorState must support diagnostic details");
  assert.equal(errorContent.includes("compact"), true, "ErrorState must support compact inline variant");
});

test("Calendar Workspace: Integrates Backlog drawer, Deadline tags, and ErrorState", () => {
  const calContent = fs.readFileSync(path.join(FRONTEND_DIR, "app/calendar/page.tsx"), "utf-8");
  assert.equal(calContent.includes("unscheduledDrawerOpen"), true, "Calendar must support Unscheduled Backlog drawer");
  assert.equal(calContent.includes("is_deadline"), true, "Calendar must handle is_deadline property");
  assert.equal(calContent.includes("[DUE]"), true, "Calendar must render [DUE] indicator for deadline tasks");
  assert.equal(calContent.includes("ErrorState"), true, "Calendar must render ErrorState on connection failure");
  assert.equal(calContent.includes("ConfirmDialog"), true, "Calendar must use ConfirmDialog for delete & disconnect");
});
