"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  Edit2,
  HelpCircle,
  Info,
  Layers,
  ListPlus,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  PlanProposalResponse,
  PlanConfirmResponse,
  TaskCreatePayload,
  TaskPriority,
  DetectedFixedEvent,
} from "@/lib/types";

export default function PlannerPage() {
  const tomorrowDateStr = new Date(Date.now() + 86400000).toISOString().split("T")[0];
  const clientTz =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC";

  // Form State
  const [prompt, setPrompt] = useState("");
  const [targetDate, setTargetDate] = useState(tomorrowDateStr);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Review & Confirmation State
  const [proposal, setProposal] = useState<PlanProposalResponse | null>(null);
  const [editableTasks, setEditableTasks] = useState<TaskCreatePayload[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState<PlanConfirmResponse | null>(null);

  const samplePrompts = [
    {
      title: "Student Day Plan",
      text: "Plan my day tomorrow: Operating Systems lecture from 10:00 to 11:30, Algorithms lab from 14:00 to 15:30, and 2 hours to study for Database Midterm.",
    },
    {
      title: "Deep Work Session",
      text: "Schedule a 90-minute deep work block for Compiler Code Review before 17:00 with priority P1.",
    },
    {
      title: "Work Day with Meetings",
      text: "Organize tomorrow: Client sync at 09:30 for 1 hour, Team standup at 11:30 for 30 minutes, and 3 hours to build the authentication microservice.",
    },
  ];

  const handleGenerateDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please enter a natural-language scheduling instruction.");
      return;
    }

    setLoading(true);
    setError(null);
    setConfirmResult(null);

    try {
      const data = await apiClient.generateDraft(prompt, clientTz, targetDate);
      setProposal(data);

      // Pre-fill editable tasks
      const initialEditableTasks: TaskCreatePayload[] = data.tasks.map((t) => ({
        title: t.title,
        estimated_duration_minutes: t.duration_minutes || 60, // fallback for editing if missing
        priority: t.priority,
        deadline: t.deadline,
        energy_level: t.energy_level,
      }));
      setEditableTasks(initialEditableTasks);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to generate plan proposal. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTaskChange = (
    index: number,
    field: keyof TaskCreatePayload,
    value: string | number
  ) => {
    const updated = [...editableTasks];
    updated[index] = {
      ...updated[index],
      [field]: value,
      ...(field === "estimated_duration_minutes"
        ? { duration_minutes: Number(value) || 0 }
        : {}),
    };
    setEditableTasks(updated);
  };

  const handleRemoveTask = (index: number) => {
    const updated = editableTasks.filter((_, i) => i !== index);
    setEditableTasks(updated);
  };

  const isClarificationResolved =
    editableTasks.length > 0 &&
    editableTasks.every(
      (t) => (t.duration_minutes || t.estimated_duration_minutes || 0) > 0
    );

  const handleConfirmPlan = async () => {
    if (!proposal) return;

    // Validate that all tasks have positive duration
    const invalidTask = editableTasks.find(
      (t) => (t.duration_minutes || t.estimated_duration_minutes || 0) <= 0
    );
    if (invalidTask) {
      setError(`Task "${invalidTask.title}" must have an estimated duration greater than 0.`);
      return;
    }

    setConfirming(true);
    setError(null);

    try {
      const normalizedTasks = editableTasks.map((t) => ({
        ...t,
        duration_minutes: t.duration_minutes || t.estimated_duration_minutes || 60,
        energy_level: t.energy_level || "medium",
        deadline:
          t.deadline && typeof t.deadline === "string" && t.deadline.trim() !== ""
            ? t.deadline
            : null,
      }));

      const result = await apiClient.confirmPlan({
        proposal_id: proposal.proposal_id,
        target_date: proposal.target_date,
        tasks: normalizedTasks,
        fixed_events: proposal.fixed_events,
        persist_tasks: true,
        generate_schedule: true,
      });

      // Never report success before server confirms
      setConfirmResult(result);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to confirm and persist plan.");
      }
    } finally {
      setConfirming(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="space-y-1">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-400">
            <Sparkles className="h-3.5 w-3.5" />
            <span>AI Planning Pipeline</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Natural-Language Command Center
          </h1>
          <p className="text-xs text-zinc-400">
            Describe your day or task in plain text. Mentor AI extracts structured intent, validates constraints, and shows a proposed plan for your review before committing.
          </p>
        </div>

        {/* Global Error Notice */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">Action Required</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Success Banner when plan is confirmed */}
        {confirmResult && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-6 space-y-4">
            <div className="flex items-center gap-3 text-emerald-400">
              <CheckCircle2 className="h-6 w-6" />
              <div>
                <h2 className="text-base font-bold text-white">Plan Confirmed & Persisted!</h2>
                <p className="text-xs text-emerald-300">
                  {confirmResult.created_tasks.length} tasks and{" "}
                  {confirmResult.created_events.length} fixed events were saved.
                  Deterministic schedule computed.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                href="/schedule"
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
              >
                <span>View Generated Schedule</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
              <Link
                href="/tasks"
                className="inline-flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-xs font-semibold text-zinc-300 hover:text-white transition-colors"
              >
                <span>View Backlog Tasks</span>
              </Link>
              <button
                onClick={() => {
                  setProposal(null);
                  setConfirmResult(null);
                  setPrompt("");
                }}
                className="text-xs text-zinc-400 hover:text-white underline ml-auto"
              >
                Plan Another Day
              </button>
            </div>
          </div>
        )}

        {/* Screen 4: Natural-Language Command Input Form */}
        {!proposal && (
          <div className="space-y-6">
            <form
              onSubmit={handleGenerateDraft}
              className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-5"
            >
              <div className="space-y-2">
                <label
                  htmlFor="prompt"
                  className="block text-xs font-medium uppercase tracking-wider text-zinc-300"
                >
                  Your Instruction / Goals
                </label>
                <textarea
                  id="prompt"
                  rows={4}
                  required
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Mentor, plan my day tomorrow: 2 classes from 10am to 11:30am and 2pm to 3:30pm, team sync at 4pm, and 2 hours for my compiler lab."
                  className="block w-full rounded-lg border border-zinc-700 bg-zinc-800/80 p-3 text-sm text-white placeholder-zinc-500 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 leading-relaxed font-sans"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="targetDate"
                    className="block text-xs font-medium uppercase tracking-wider text-zinc-300"
                  >
                    Target Date
                  </label>
                  <input
                    id="targetDate"
                    type="date"
                    required
                    value={targetDate}
                    onChange={(e) => setTargetDate(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800/80 px-3 py-2 text-sm text-white shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-zinc-300">
                    Detected Timezone
                  </label>
                  <div className="mt-1 flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-800/40 px-3 py-2 text-sm text-zinc-400">
                    <Clock className="h-4 w-4 text-zinc-500" />
                    <span className="font-mono text-xs">{clientTz}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-zinc-800/60">
                <div className="flex items-center gap-2 text-[11px] text-zinc-400">
                  <ShieldAlert className="h-3.5 w-3.5 text-zinc-400" />
                  <span>Dry-run preview only. Requires your approval before saving.</span>
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-brand-500 disabled:opacity-50 transition-colors"
                >
                  {loading ? (
                    <>
                      <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Extracting Plan...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>Generate Plan Proposal</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Clear Examples Card */}
            <div className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Quick Example Instructions
              </h2>
              <div className="grid gap-3 sm:grid-cols-3">
                {samplePrompts.map((sample, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setPrompt(sample.text)}
                    className="text-left rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3.5 hover:border-zinc-700 hover:bg-zinc-900/80 transition-all space-y-1.5"
                  >
                    <p className="text-xs font-semibold text-white">{sample.title}</p>
                    <p className="text-[11px] text-zinc-400 line-clamp-3 leading-relaxed">
                      &ldquo;{sample.text}&rdquo;
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Screen 5: Plan Review Screen (showing extracted tasks, assumptions, editable fields) */}
        {proposal && !confirmResult && (
          <div className="space-y-6">
            {/* Review Header Banner */}
            <div className="rounded-xl border border-brand-500/30 bg-brand-950/20 p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="rounded-full bg-brand-500/20 px-2.5 py-0.5 text-[10px] uppercase font-bold tracking-wider text-brand-300">
                  Intent: {proposal.intent.replace("_", " ")}
                </span>
                <span className="text-xs font-mono text-zinc-400">
                  Target Date: {proposal.target_date}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium ${
                    proposal.parser_used === "deterministic_offline"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                  }`}
                >
                  Parser: {proposal.parser_used}
                </span>
              </div>
              <p className="text-sm font-medium text-white">{proposal.explanation}</p>
              <div className="text-xs text-zinc-400 flex items-center gap-2">
                <Info className="h-3.5 w-3.5 text-zinc-500" />
                <span>
                  Original prompt: &ldquo;{proposal.original_prompt}&rdquo;
                </span>
              </div>
            </div>

            {/* Missing Information / Clarification Alert */}
            {proposal.clarification_question && (
              <div
                className={`rounded-xl border p-4 space-y-2 ${
                  isClarificationResolved
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-300"
                }`}
              >
                <div className="flex items-center gap-2">
                  {isClarificationResolved ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span className="text-xs font-bold uppercase tracking-wider text-emerald-300">
                        Clarification Resolved
                      </span>
                    </>
                  ) : (
                    <>
                      <HelpCircle className="h-4 w-4 text-amber-400" />
                      <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                        Clarification Needed
                      </span>
                    </>
                  )}
                </div>
                <p className="text-xs">
                  {proposal.clarification_question}
                </p>
                {isClarificationResolved ? (
                  <p className="text-[11px] text-emerald-400 font-medium">
                    ✓ All task durations are now set. You can review and confirm your schedule below.
                  </p>
                ) : (
                  proposal.missing_information.length > 0 && (
                    <p className="text-[11px] text-amber-400 font-mono">
                      Missing parameters: {proposal.missing_information.join(", ")}
                    </p>
                  )
                )}
              </div>
            )}

            {/* Extracted Tasks (Editable Table) */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <ListPlus className="h-4 w-4 text-brand-400" />
                  <h2 className="text-sm font-semibold text-white">
                    Extracted Tasks ({editableTasks.length}) — Editable Fields
                  </h2>
                </div>
                <span className="text-[11px] text-zinc-400">
                  Adjust duration or priority before saving
                </span>
              </div>

              {editableTasks.length === 0 ? (
                <p className="py-4 text-center text-xs text-zinc-400">
                  No actionable tasks detected in prompt.
                </p>
              ) : (
                <div className="space-y-3">
                  {editableTasks.map((task, idx) => (
                    <div
                      key={idx}
                      className="rounded-lg border border-zinc-800 bg-zinc-800/40 p-3.5 space-y-3 sm:space-y-0 sm:flex sm:items-center sm:gap-4"
                    >
                      <div className="flex-1 space-y-1">
                        <label className="text-[10px] uppercase font-bold text-zinc-400">
                          Task Title
                        </label>
                        <input
                          type="text"
                          value={task.title}
                          onChange={(e) => handleTaskChange(idx, "title", e.target.value)}
                          className="w-full rounded border border-zinc-700 bg-zinc-900/80 px-2.5 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                        />
                      </div>

                      <div className="w-28 space-y-1">
                        <label className="text-[10px] uppercase font-bold text-zinc-400">
                          Duration (min)
                        </label>
                        <input
                          type="number"
                          min={5}
                          max={720}
                          value={task.estimated_duration_minutes || ""}
                          onChange={(e) =>
                            handleTaskChange(
                              idx,
                              "estimated_duration_minutes",
                              parseInt(e.target.value) || 0
                            )
                          }
                          className="w-full rounded border border-zinc-700 bg-zinc-900/80 px-2.5 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none font-mono"
                        />
                      </div>

                      <div className="w-28 space-y-1">
                        <label className="text-[10px] uppercase font-bold text-zinc-400">
                          Priority
                        </label>
                        <select
                          value={task.priority}
                          onChange={(e) =>
                            handleTaskChange(idx, "priority", e.target.value as TaskPriority)
                          }
                          className="w-full rounded border border-zinc-700 bg-zinc-900/80 px-2 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                        >
                          <option value="P1">P1 (Urgent)</option>
                          <option value="P2">P2 (High)</option>
                          <option value="P3">P3 (Medium)</option>
                          <option value="P4">P4 (Low)</option>
                        </select>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleRemoveTask(idx)}
                        className="self-end sm:self-center p-1.5 text-zinc-500 hover:text-rose-400 rounded transition-colors"
                        title="Remove task"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Extracted Fixed Events */}
            {proposal.fixed_events.length > 0 && (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
                <div className="flex items-center gap-2 border-b border-zinc-800 pb-3">
                  <Calendar className="h-4 w-4 text-purple-400" />
                  <h2 className="text-sm font-semibold text-white">
                    Fixed Commitments ({proposal.fixed_events.length})
                  </h2>
                </div>
                <div className="space-y-2">
                  {proposal.fixed_events.map((ev, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-lg border border-zinc-800/60 bg-zinc-800/30 p-2.5 text-xs"
                    >
                      <div className="space-y-0.5">
                        <p className="font-semibold text-white">{ev.title}</p>
                        <p className="text-[11px] text-zinc-400 font-mono">
                          {new Date(ev.start_time).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}{" "}
                          -{" "}
                          {new Date(ev.end_time).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                      <span className="rounded bg-purple-500/10 px-2 py-0.5 text-[10px] font-bold text-purple-400 border border-purple-500/20">
                        Fixed Event
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Dry-Run Deterministic Schedule Preview */}
            {proposal.preview_schedule && (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-sky-400" />
                    <h2 className="text-sm font-semibold text-white">
                      Deterministic Solver Preview (Dry-Run)
                    </h2>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                      proposal.preview_schedule.status === "feasible"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    }`}
                  >
                    Status: {proposal.preview_schedule.status}
                  </span>
                </div>
                <div className="text-xs text-zinc-400 space-y-1">
                  <p>
                    Working hours: {proposal.preview_schedule.working_hours.start_time} -{" "}
                    {proposal.preview_schedule.working_hours.end_time} • Scheduled task time:{" "}
                    {proposal.preview_schedule.summary?.total_scheduled_task_minutes ?? 0} mins •
                    Utilization:{" "}
                    {(proposal.preview_schedule.summary?.utilization_percentage ?? 0).toFixed(1)}%
                  </p>
                  {proposal.preview_schedule.scheduling_explanation && (
                    <p className="text-brand-300 font-medium">
                      💡 {proposal.preview_schedule.scheduling_explanation}
                    </p>
                  )}
                  {proposal.preview_schedule.unscheduled_tasks.length > 0 && (
                    <p className="text-amber-400 font-medium">
                      ⚠️ {proposal.preview_schedule.unscheduled_tasks.length} task(s) could
                      not fit in the available window.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Approval / Rejection Actions */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              <button
                type="button"
                onClick={() => setProposal(null)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-xs font-semibold text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Edit Prompt</span>
              </button>

              <button
                type="button"
                onClick={handleConfirmPlan}
                disabled={confirming}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-2.5 text-xs font-bold text-white shadow-lg hover:bg-emerald-500 disabled:opacity-50 transition-colors"
              >
                {confirming ? (
                  <>
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <span>Persisting Plan & Running Solver...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4" />
                    <span>Confirm & Persist Plan</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
