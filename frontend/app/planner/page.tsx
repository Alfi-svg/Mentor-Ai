"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Compass,
  Edit2,
  HelpCircle,
  Inbox,
  Info,
  Layers,
  ListPlus,
  Mail,
  Mic,
  RotateCcw,
  Shield,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { VoiceInputButton } from "@/components/VoiceInputButton";
import { useToast } from "@/components/ui/ToastProvider";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  ActionRecord,
  DetectedFixedEvent,
  EmailTaskCandidate,
  LifeOpsWorkflowResponse,
  PlanConfirmResponse,
  PlanProposalResponse,
  TaskCreatePayload,
  TaskPriority,
} from "@/lib/types";

export default function PlannerPage() {
  const tomorrowDateStr = new Date(Date.now() + 86400000).toISOString().split("T")[0];
  const clientTz =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC";

  // Mode: Standard Day Planner vs Executive LifeOps Agent
  const [plannerMode, setPlannerMode] = useState<"standard" | "lifeops">("standard");
  const toast = useToast();

  // Form State
  const [prompt, setPrompt] = useState("");
  const [targetDate, setTargetDate] = useState(tomorrowDateStr);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Standard Planner State
  const [proposal, setProposal] = useState<PlanProposalResponse | null>(null);
  const [editableTasks, setEditableTasks] = useState<TaskCreatePayload[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState<PlanConfirmResponse | null>(null);

  // LifeOps Pipeline State
  const [lifeopsResult, setLifeopsResult] = useState<LifeOpsWorkflowResponse | null>(null);
  const [actionProcessing, setActionProcessing] = useState<string | null>(null);

  const samplePrompts = [
    {
      title: "End-to-End LifeOps Workflow",
      text: "Read my important emails, identify my upcoming assignments, prepare a study plan for tomorrow, and remind me before each deadline.",
      mode: "lifeops" as const,
    },
    {
      title: "Student Day Plan",
      text: "Plan my day tomorrow: Operating Systems lecture from 10:00 to 11:30, Algorithms lab from 14:00 to 15:30, and 2 hours to study for Database Midterm.",
      mode: "standard" as const,
    },
    {
      title: "Deep Work Session",
      text: "Schedule a 90-minute deep work block for Compiler Code Review before 17:00 with priority P1.",
      mode: "standard" as const,
    },
  ];

  const handleVoiceTranscript = (transcript: string) => {
    setPrompt((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript));
  };

  const handleExecuteLifeOps = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please enter or speak an instruction.");
      return;
    }

    setLoading(true);
    setError(null);
    setLifeopsResult(null);
    setProposal(null);

    try {
      const res = await apiClient.executeLifeOpsWorkflow({
        prompt,
        target_date: targetDate,
        client_timezone: clientTz,
        auto_extract_emails: true,
        stage_calendar_action: true,
        stage_email_action: false,
        stage_notifications: true,
      });
      setLifeopsResult(res);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("LifeOps workflow execution failed. Please verify your connection.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please enter a natural-language scheduling instruction.");
      return;
    }

    setLoading(true);
    setError(null);
    setConfirmResult(null);
    setLifeopsResult(null);

    try {
      const data = await apiClient.generateDraft(prompt, clientTz, targetDate);
      setProposal(data);

      const initialEditableTasks: TaskCreatePayload[] = data.tasks.map((t) => ({
        title: t.title,
        estimated_duration_minutes: t.duration_minutes || 60,
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

  const handleAddTask = () => {
    setEditableTasks((prev) => [
      ...prev,
      {
        title: "New Study Task",
        estimated_duration_minutes: 45,
        duration_minutes: 45,
        priority: "P3",
        energy_level: "medium",
        deadline: null,
      },
    ]);
  };

  const handleResetPlan = () => {
    setPrompt("");
    setProposal(null);
    setConfirmResult(null);
    setEditableTasks([]);
    setError(null);
  };

  const handleConfirmPlan = async () => {
    if (!proposal) return;

    if (editableTasks.length === 0) {
      setError("Please add at least one task to confirm the plan.");
      return;
    }

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

      setConfirmResult(result);
      setProposal(null);
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

  const handleActionDecision = async (actionId: string, confirmed: boolean) => {
    setActionProcessing(actionId);
    try {
      await apiClient.confirmAction(actionId, confirmed);
      // Update local state
      if (lifeopsResult) {
        setLifeopsResult({
          ...lifeopsResult,
          staged_actions: lifeopsResult.staged_actions.filter((a) => a.id !== actionId),
        });
      }
      toast.success(
        confirmed ? "Action Approved" : "Action Rejected",
        `Successfully ${confirmed ? "approved" : "rejected"} action record.`
      );
    } catch (err) {
      toast.error(
        "Action Processing Failed",
        err instanceof Error ? err.message : String(err)
      );
    } finally {
      setActionProcessing(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-400">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Autonomous LifeOps & Planner</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Command Center
          </h1>
          <p className="text-xs text-zinc-400">
            Coordinate emails, assignments, calendar commitments, deterministic scheduling, and persistent deadline alerts via text or voice.
          </p>
        </div>

        {/* Mode Selector Tabs */}
        <div className="flex items-center gap-2 border-b border-zinc-800/80 pb-3">
          <button
            onClick={() => {
              setPlannerMode("lifeops");
              setProposal(null);
              setConfirmResult(null);
            }}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all ${
              plannerMode === "lifeops"
                ? "bg-indigo-600 text-white shadow-sm border border-indigo-400/30"
                : "bg-zinc-900/60 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800/60"
            }`}
          >
            <Compass className="h-4 w-4" />
            Executive LifeOps Workflow
          </button>
          <button
            onClick={() => {
              setPlannerMode("standard");
              setLifeopsResult(null);
            }}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all ${
              plannerMode === "standard"
                ? "bg-indigo-600 text-white shadow-sm border border-indigo-400/30"
                : "bg-zinc-900/60 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800/60"
            }`}
          >
            <Calendar className="h-4 w-4" />
            Day Planner Mode
          </button>
        </div>

        {/* Global Error Notice */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">Action Required</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Command Input Form with Voice Button */}
        <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-5 backdrop-blur-md">
          <form onSubmit={plannerMode === "lifeops" ? handleExecuteLifeOps : handleGenerateDraft} className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label htmlFor="prompt" className="block text-xs font-semibold uppercase tracking-wider text-zinc-300">
                  {plannerMode === "lifeops" ? "LifeOps Goal & Command" : "Your Scheduling Instruction"}
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-zinc-400">Speak instruction:</span>
                  <VoiceInputButton onTranscriptReady={handleVoiceTranscript} disabled={loading} />
                </div>
              </div>

              <textarea
                id="prompt"
                rows={4}
                required
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={
                  plannerMode === "lifeops"
                    ? "Read my important emails, identify my upcoming assignments, prepare a study plan for tomorrow, and remind me before each deadline."
                    : "Plan my day tomorrow: 2 classes from 10am to 11:30am and 2pm to 3:30pm, team sync at 4pm, and 2 hours for compiler lab."
                }
                className="block w-full rounded-xl border border-zinc-700/80 bg-zinc-950/80 p-3.5 text-sm text-white placeholder-zinc-500 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 leading-relaxed font-sans transition-all"
              />
              <p className="text-[11px] text-zinc-400">
                You can speak naturally using the microphone icon above. Voice transcripts are editable before submission.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="targetDate" className="block text-xs font-semibold uppercase tracking-wider text-zinc-300">
                  Target Date
                </label>
                <input
                  id="targetDate"
                  type="date"
                  required
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className="mt-1 block w-full rounded-xl border border-zinc-700/80 bg-zinc-950/80 px-3.5 py-2.5 text-sm text-white shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-300">
                  Detected Timezone
                </label>
                <div className="mt-1 flex items-center gap-2 rounded-xl border border-zinc-800/80 bg-zinc-950/60 px-3.5 py-2.5 text-sm text-zinc-400">
                  <Clock className="h-4 w-4 text-zinc-500" />
                  <span className="font-mono text-xs">{clientTz}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-zinc-800/60">
              <div className="flex items-center gap-2 text-[11px] text-zinc-400">
                <Shield className="h-3.5 w-3.5 text-zinc-400" />
                <span>Deterministic solver & two-phase approval active.</span>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-indigo-500 disabled:opacity-50 transition-all border border-indigo-400/30"
              >
                {loading ? (
                  <>
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <span>Processing Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>{plannerMode === "lifeops" ? "Run LifeOps Workflow" : "Generate Plan Proposal"}</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Quick Examples */}
          <div className="space-y-2 pt-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Quick Suggestions
            </h2>
            <div className="grid gap-2 sm:grid-cols-3">
              {samplePrompts.map((sample, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    setPrompt(sample.text);
                    setPlannerMode(sample.mode);
                  }}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 text-left hover:border-brand-500/50 hover:bg-zinc-800/40 transition"
                >
                  <p className="text-xs font-semibold text-zinc-200">{sample.title}</p>
                  <p className="mt-1 line-clamp-2 text-[11px] text-zinc-400">{sample.text}</p>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* LifeOps Workflow Results Panel */}
        {lifeopsResult && (
          <div className="space-y-6">
            {/* Step Progression Timeline */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Compass className="h-4 w-4 text-brand-400" />
                LifeOps Execution Pipeline
              </h2>
              <div className="grid gap-2 sm:grid-cols-2">
                {lifeopsResult.workflow_steps.map((st, i) => (
                  <div key={i} className="flex items-start gap-2.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5">
                    {st.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
                    ) : st.status === "requires_clarification" ? (
                      <HelpCircle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                    ) : st.status === "pending_review" ? (
                      <Clock className="h-4 w-4 shrink-0 text-sky-400 mt-0.5" />
                    ) : (
                      <Info className="h-4 w-4 shrink-0 text-zinc-500 mt-0.5" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-zinc-200 capitalize">
                          {st.step.replace(/_/g, " ")}
                        </span>
                        <span className={`text-[10px] font-bold uppercase rounded px-1.5 py-0.2 ${
                          st.status === "completed"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : st.status === "requires_clarification"
                            ? "bg-amber-500/10 text-amber-400"
                            : "bg-zinc-800 text-zinc-400"
                        }`}>
                          {st.status}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-zinc-400">{st.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Ambiguous Deadlines Clarification Banner */}
            {lifeopsResult.has_ambiguous_deadlines && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 space-y-2">
                <div className="flex items-center gap-2 text-amber-400">
                  <HelpCircle className="h-5 w-5" />
                  <h3 className="text-sm font-bold text-white">Clarification Needed on Email Deadlines</h3>
                </div>
                <ul className="list-disc pl-5 text-xs text-amber-200 space-y-1">
                  {lifeopsResult.clarification_questions.map((q, idx) => (
                    <li key={idx}>{q}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Extracted Assignment Candidates */}
            {lifeopsResult.extracted_candidates.length > 0 && (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Inbox className="h-4 w-4 text-brand-400" />
                    Extracted Email Tasks ({lifeopsResult.extracted_candidates.length})
                  </h3>
                  <span className="text-[11px] text-zinc-400">Source referenced & sanitized</span>
                </div>
                <div className="divide-y divide-zinc-800/60 rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950/40">
                  {lifeopsResult.extracted_candidates.map((cand, idx) => (
                    <div key={idx} className="p-3 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{cand.title}</span>
                        <span className="rounded bg-brand-500/20 px-2 py-0.5 text-[10px] text-brand-300 font-bold">
                          {cand.priority} • {cand.estimated_duration_minutes}m
                        </span>
                      </div>
                      <p className="text-zinc-400">{cand.description}</p>
                      <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-zinc-500">
                        <span>Source: {cand.source_sender}</span>
                        <span>
                          Deadline:{" "}
                          {cand.proposed_deadline
                            ? new Date(cand.proposed_deadline).toLocaleString()
                            : "Tentative"}
                          {cand.is_deadline_ambiguous && (
                            <span className="ml-1 text-amber-400 font-medium">(Ambiguous)</span>
                          )}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Staged Consequential Actions Awaiting Approval */}
            {lifeopsResult.staged_actions.length > 0 && (
              <div className="rounded-xl border border-sky-500/30 bg-sky-950/20 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sky-400">
                    <ShieldAlert className="h-5 w-5" />
                    <h3 className="text-sm font-bold text-white">
                      Actions Awaiting Approval ({lifeopsResult.staged_actions.length})
                    </h3>
                  </div>
                  <Link href="/actions" className="text-xs text-sky-400 hover:text-sky-300">
                    View in Actions Hub →
                  </Link>
                </div>
                <p className="text-xs text-zinc-300">
                  External actions (calendar writes or email sending) are held in staged state until you explicitly approve them.
                </p>

                <div className="space-y-3">
                  {lifeopsResult.staged_actions.map((act) => (
                    <div key={act.id} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-xs capitalize">
                          {act.action_type.replace(/_/g, " ")}
                        </span>
                        <span className="text-[10px] rounded bg-amber-500/10 text-amber-400 px-2 py-0.5 border border-amber-500/20 font-bold uppercase">
                          Pending Approval
                        </span>
                      </div>
                      <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950 p-2 rounded overflow-x-auto">
                        {JSON.stringify(act.payload, null, 2)}
                      </pre>
                      <div className="flex items-center gap-2 pt-2">
                        <button
                          onClick={() => handleActionDecision(act.id, true)}
                          disabled={actionProcessing === act.id}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition"
                        >
                          <Check className="h-3.5 w-3.5" />
                          Approve Action
                        </button>
                        <button
                          onClick={() => handleActionDecision(act.id, false)}
                          disabled={actionProcessing === act.id}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-400 hover:bg-red-500/20 transition"
                        >
                          <X className="h-3.5 w-3.5" />
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Generated Schedule Timeline Preview */}
            {lifeopsResult.schedule_proposal && (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <div className="flex items-center gap-2 text-white">
                    <Clock className="h-4 w-4 text-sky-400" />
                    <h3 className="text-sm font-semibold">Deterministic Timeline Proposal</h3>
                  </div>
                  <span className="rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-0.5 text-xs font-bold uppercase">
                    Status: {lifeopsResult.schedule_proposal.status}
                  </span>
                </div>

                <div className="divide-y divide-zinc-800/60 rounded-lg border border-zinc-800 bg-zinc-950/40 overflow-hidden">
                  {lifeopsResult.schedule_proposal.scheduled_blocks?.map((blk: any, i: number) => (
                    <div key={i} className="p-3 text-xs flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-white">{blk.task_title}</p>
                        <p className="text-[11px] text-zinc-400">
                          {new Date(blk.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} -{" "}
                          {new Date(blk.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} • {blk.duration_minutes}m
                        </p>
                      </div>
                      <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 font-medium">
                        {blk.block_type || "task"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bottom summary and Navigation */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <span className="text-xs text-zinc-400">
                🔔 {lifeopsResult.notifications_created_count} persistent deadline alerts staged in database.
              </span>
              <div className="flex items-center gap-2">
                <Link
                  href="/schedule"
                  className="rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500 transition"
                >
                  Open Schedule View →
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Standard Proposal Confirmation Screen (Preserved) */}
        {proposal && (
          <div className="space-y-6">
            {/* Clarification & Suggestions Banner */}
            {(proposal.clarification_question || (proposal.missing_information && proposal.missing_information.length > 0)) && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 space-y-3">
                <div className="flex items-center gap-2 text-amber-400">
                  <HelpCircle className="h-5 w-5" />
                  <h3 className="text-sm font-bold text-white">Clarification & Suggestions</h3>
                </div>
                {proposal.clarification_question && (
                  <p className="text-xs text-amber-200 leading-relaxed">
                    {proposal.clarification_question}
                  </p>
                )}
                {proposal.missing_information && proposal.missing_information.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-semibold text-amber-300 uppercase tracking-wider">
                      Missing Information Noted:
                    </span>
                    <ul className="list-disc pl-5 text-xs text-amber-200/90 space-y-1">
                      {proposal.missing_information.map((info, idx) => (
                        <li key={idx}>{info}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <ListPlus className="h-4 w-4 text-brand-400" />
                  <h2 className="text-sm font-semibold text-white">
                    Proposed Tasks ({editableTasks.length})
                  </h2>
                  <span className="text-xs text-zinc-400">Target Date: {proposal.target_date}</span>
                </div>
                <button
                  type="button"
                  onClick={handleAddTask}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-brand-500/30 bg-brand-500/10 px-3 py-1.5 text-xs font-semibold text-brand-300 hover:bg-brand-500/20 transition"
                >
                  <ListPlus className="h-3.5 w-3.5" />
                  Add Task Step
                </button>
              </div>

              <div className="space-y-3">
                {editableTasks.map((t, idx) => (
                  <div key={idx} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <input
                        type="text"
                        value={t.title}
                        onChange={(e) => handleTaskChange(idx, "title", e.target.value)}
                        className="w-full bg-transparent font-semibold text-white text-sm focus:outline-none border-b border-transparent focus:border-brand-500"
                      />
                      <button
                        onClick={() => handleRemoveTask(idx)}
                        className="text-zinc-500 hover:text-red-400 p-1"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 font-bold">Duration (min)</label>
                        <input
                          type="number"
                          value={t.estimated_duration_minutes || t.duration_minutes || 60}
                          onChange={(e) =>
                            handleTaskChange(idx, "estimated_duration_minutes", Number(e.target.value))
                          }
                          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 font-bold">Priority</label>
                        <select
                          value={t.priority || "P3"}
                          onChange={(e) => handleTaskChange(idx, "priority", e.target.value as TaskPriority)}
                          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white"
                        >
                          <option value="P1">P1 (Urgent)</option>
                          <option value="P2">P2 (High)</option>
                          <option value="P3">P3 (Medium)</option>
                          <option value="P4">P4 (Low)</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] uppercase text-zinc-500 font-bold">Deadline</label>
                        <input
                          type="datetime-local"
                          value={t.deadline ? t.deadline.slice(0, 16) : ""}
                          onChange={(e) => handleTaskChange(idx, "deadline", e.target.value)}
                          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-white"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setProposal(null)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-xs font-semibold text-zinc-300 hover:text-white"
                >
                  Cancel / Re-enter
                </button>
                <button
                  type="button"
                  onClick={handleConfirmPlan}
                  disabled={confirming}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white hover:bg-emerald-500"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  <span>{confirming ? "Confirming..." : "Confirm & Persist Schedule"}</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Confirmed Plan Persisted Card */}
        {confirmResult && (
          <div className="space-y-6">
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-emerald-500/20 pb-4">
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-emerald-500/20 p-2 text-emerald-400">
                    <CheckCircle2 className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white">Plan Confirmed & Persisted!</h2>
                    <p className="text-xs text-zinc-300">
                      Successfully saved {confirmResult.created_tasks.length} task{confirmResult.created_tasks.length === 1 ? "" : "s"} for{" "}
                      <span className="font-semibold text-emerald-300">{confirmResult.target_date}</span>
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-bold text-emerald-300 uppercase">
                    Status: {confirmResult.status}
                  </span>
                  <button
                    type="button"
                    onClick={handleResetPlan}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800/80 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:text-white hover:bg-zinc-700 transition"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Plan Another Day
                  </button>
                </div>
              </div>

              {/* Created Tasks List */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Persisted Tasks ({confirmResult.created_tasks.length})
                </h3>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {confirmResult.created_tasks.map((task) => (
                    <div
                      key={task.id}
                      className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3.5 space-y-2 flex flex-col justify-between"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-xs font-semibold text-white leading-snug">
                          {task.title}
                        </span>
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            task.priority === "P1"
                              ? "bg-red-500/20 text-red-400 border border-red-500/30"
                              : task.priority === "P2"
                              ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                              : "bg-zinc-800 text-zinc-300"
                          }`}
                        >
                          {task.priority}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-400 pt-1 border-t border-zinc-900">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3 text-sky-400" />
                          {task.estimated_duration_minutes || task.duration_minutes || 60}m
                        </span>
                        {task.deadline && (
                          <span className="flex items-center gap-1 text-zinc-300">
                            <Calendar className="h-3 w-3 text-emerald-400" />
                            {new Date(task.deadline).toLocaleDateString([], {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Unscheduled Tasks Warning If Any */}
              {confirmResult.schedule?.unscheduled_tasks && confirmResult.schedule.unscheduled_tasks.length > 0 && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-2">
                  <div className="flex items-center gap-2 text-amber-400">
                    <AlertTriangle className="h-4 w-4" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-amber-300">
                      Unscheduled Task Notice ({confirmResult.schedule.unscheduled_tasks.length})
                    </h4>
                  </div>
                  <p className="text-xs text-amber-200/90">
                    The following tasks were successfully persisted to your Task list, but could not fit in the target day&apos;s working hours without exceeding time limits:
                  </p>
                  <ul className="list-disc pl-5 text-xs text-amber-200/90 space-y-1">
                    {confirmResult.schedule.unscheduled_tasks.map((un, idx) => (
                      <li key={idx}>
                        <span className="font-semibold text-white">{un.task_title || un.title || "Task"}</span>: {un.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Scheduled Timeline Blocks If Available */}
              {confirmResult.schedule?.scheduled_blocks && confirmResult.schedule.scheduled_blocks.length > 0 && (
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                      <Clock className="h-3.5 w-3.5 text-sky-400" />
                      Generated Schedule Timeline
                    </h3>
                    <span className="text-[11px] text-zinc-400">
                      {confirmResult.schedule.scheduled_blocks.length} allocated block{confirmResult.schedule.scheduled_blocks.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="divide-y divide-zinc-800/60 rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden">
                    {confirmResult.schedule.scheduled_blocks.map((blk, i) => (
                      <div key={i} className="p-3 text-xs flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-white">{blk.title}</p>
                          <p className="text-[11px] text-zinc-400">
                            {new Date(blk.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} -{" "}
                            {new Date(blk.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </p>
                        </div>
                        <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 font-medium capitalize">
                          {blk.block_type.replace(/_/g, " ")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Navigation Action Links */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-emerald-500/20">
                <span className="text-xs text-zinc-400">
                  Tasks are active and ready in your workspace.
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href="/tasks"
                    className="rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-semibold text-zinc-200 hover:text-white hover:bg-zinc-700 transition"
                  >
                    View in Tasks
                  </Link>
                  <Link
                    href="/calendar"
                    className="rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-semibold text-zinc-200 hover:text-white hover:bg-zinc-700 transition"
                  >
                    View in Calendar
                  </Link>
                  <Link
                    href="/schedule"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 transition"
                  >
                    <span>View Schedule</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
