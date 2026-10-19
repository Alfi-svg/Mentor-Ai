import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("Code ArenaX Team Data Model and Members Verification", () => {
  const teamDataPath = path.resolve(__dirname, "../lib/team-data.ts");
  assert.equal(fs.existsSync(teamDataPath), true, "frontend/lib/team-data.ts must exist");

  const content = fs.readFileSync(teamDataPath, "utf-8");
  assert.equal(content.includes('name: "Code ArenaX"'), true, "Must have team name Code ArenaX");
  assert.equal(content.includes("Code. Compete. Conquer."), true, "Must include tagline 'Code. Compete. Conquer.'");
  
  // Alfi Shahrin Talukder
  assert.equal(content.includes("Alfi Shahrin Talukder"), true, "Must include Alfi Shahrin Talukder");
  assert.equal(content.includes("https://github.com/Alfi-svg"), true, "Must include Alfi's exact GitHub URL");
  assert.equal(
    content.includes("https://www.linkedin.com/in/alfi-shahrin-talukder-a68450370/?isSelfProfile=true"),
    true,
    "Must include Alfi's exact LinkedIn URL"
  );

  // Samiul Islam
  assert.equal(content.includes("Samiul Islam"), true, "Must include Samiul Islam");
  assert.equal(content.includes("https://github.com/samiulxr2"), true, "Must include Samiul's exact GitHub URL");
  assert.equal(
    content.includes("https://www.linkedin.com/in/samiulxr2/"),
    true,
    "Must include Samiul's exact LinkedIn URL"
  );
});

test("Code ArenaX Team Asset Files Exist", () => {
  const alfiImg = path.resolve(__dirname, "../public/team/alfi.jpg");
  const samiulImg = path.resolve(__dirname, "../public/team/samiul.png");
  const logoImg = path.resolve(__dirname, "../public/team/codearenax-logo.png");

  assert.equal(fs.existsSync(alfiImg), true, "Alfi avatar image must exist");
  assert.equal(fs.existsSync(samiulImg), true, "Samiul avatar image must exist");
  assert.equal(fs.existsSync(logoImg), true, "Code ArenaX logo must exist");

  assert.ok(fs.statSync(alfiImg).size > 10000, "Alfi avatar file must be non-empty");
  assert.ok(fs.statSync(samiulImg).size > 10000, "Samiul avatar file must be non-empty");
  assert.ok(fs.statSync(logoImg).size > 10000, "Code ArenaX logo file must be non-empty");
});

test("Sidebar Navigation and AppShell Footer Integration", () => {
  const appShellPath = path.resolve(__dirname, "../components/AppShell.tsx");
  assert.equal(fs.existsSync(appShellPath), true, "frontend/components/AppShell.tsx must exist");

  const content = fs.readFileSync(appShellPath, "utf-8");
  // Navigation item
  assert.equal(content.includes('href: "/team"'), true, "AppShell nav must link to /team");
  assert.equal(content.includes('label: "Developer Team"'), true, "AppShell nav item must be labeled 'Developer Team'");
  
  // Footer credit
  assert.equal(content.includes("Built with care by"), true, "AppShell must include 'Built with care by' footer credit");
  assert.equal(content.includes("Code ArenaX"), true, "AppShell footer must mention 'Code ArenaX'");
});

test("Landing Page Footer Integration", () => {
  const landingPagePath = path.resolve(__dirname, "../app/page.tsx");
  assert.equal(fs.existsSync(landingPagePath), true, "frontend/app/page.tsx must exist");

  const content = fs.readFileSync(landingPagePath, "utf-8");
  assert.equal(content.includes("Built with care by"), true, "Landing page footer must include credit");
  assert.equal(content.includes('href="/team"'), true, "Landing page footer must link to /team");
  assert.equal(content.includes("Code ArenaX"), true, "Landing page footer must credit Code ArenaX");
});

test("Developer Team Page /team Component Structure", () => {
  const teamPagePath = path.resolve(__dirname, "../app/team/page.tsx");
  assert.equal(fs.existsSync(teamPagePath), true, "frontend/app/team/page.tsx must exist");

  const content = fs.readFileSync(teamPagePath, "utf-8");
  assert.equal(content.includes("Meet Our Team"), true, "Team page must have heading 'Meet Our Team'");
  assert.equal(content.includes("Meet the people behind Mentor AI"), true, "Team page must have subtitle");
  assert.equal(content.includes("AppShell"), true, "Team page must be wrapped in AppShell");
  assert.equal(content.includes("MemberCard"), true, "Team page must render member cards");
  assert.equal(content.includes("target=\"_blank\""), true, "External social links must open in new tab");
  assert.equal(content.includes("rel=\"noopener noreferrer\""), true, "External links must have noopener noreferrer");
  assert.equal(content.includes("aria-label="), true, "External links must have accessible aria-labels");
});
