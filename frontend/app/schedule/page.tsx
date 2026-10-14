"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coffee,
  Layers,
  Lock,
  RefreshCw,
  Sparkles,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  SavedSchedule,
  ScheduleBlockProposal,
  ScheduleProposal,
} from "@/lib/types";

export default function SchedulePage() {
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [savedSchedule, setSavedSchedule] = useState<SavedSchedule | null>(null);
  const [proposal, setProposal] = useState<ScheduleProposal | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  const loadScheduleForDate = useCallback(async (dateStr: string) => {
    setLoading(true);
    setError(null);
    setProposal(null);
    setSuccessBanner(null);
    try {
      const data = await apiClient.getScheduleForDate(dateStr);
      setSavedSchedule(data);
    } catch (err) {
      if (err instanceof ApiClientError && err.statusCode === 404) {
        setSavedSchedule(null);
      } else {
        setError(err instanceof Error ? err.message : "Failed to load schedule.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadScheduleForDate(selectedDate);
  }, [selectedDate, loadScheduleForDate]);

  const handleDateChange = (daysDelta: number) => {
    const current = new Date(selectedDate);
    current.setDate(current.getDate() + daysDelta);
    setSelectedDate(current.toISOString().split("T")[0]);
  };

  const handleGenerateProposal = async () => {
    setGenerating(true);
    setError(null);
    setSuccessBanner(null);
    try {
      const prop = await apiClient.generateSchedule({
        target_date: selectedDate,
        enforce_buffer: true,
      });
      setProposal(prop);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to generate schedule proposal.");
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleApproveProposal = async () => {
    if (!proposal) return;
    setApproving(true);
    setError(null);
    try {
      await apiClient.approveSchedule(proposal);
      setSuccessBanner("Schedule successfully approved, validated, and persisted.");
      setProposal(null);
      await loadScheduleForDate(selectedDate);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to approve schedule.");
      }
    } finally {
      setApproving(false);
    }
  };

  const activeBlocks = proposal
    ? (proposal.scheduled_blocks || (proposal as any).blocks || [])
    : savedSchedule
    ? savedSchedule.blocks.map((b) => ({
        task_id: b.task_id,
        calendar_event_id: b.calendar_event_id,
        title: b.title,
        start_time: b.start_time,
        end_time: b.end_time,
        block_type: b.block_type as ScheduleBlockProposal["block_type"],
        is_completed: b.is_completed,
      }))
    : [];

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Top Control Bar: Date Navigation & Actions */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Deterministic Schedule
            </h1>
            <p className="text-xs text-zinc-400">
              Mathematically verified interval algebra. Zero overlapping commitments.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Date Navigator */}
            <div className="flex items-center rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
              <button
                onClick={() => handleDateChange(-1)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                title="Previous Day"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="border-0 bg-transparent px-2 text-xs font-semibold text-white focus:outline-none"
              />
              <button
                onClick={() => handleDateChange(1)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                title="Next Day"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            <button
              onClick={() => setSelectedDate(new Date().toISOString().split("T")[0])}
              className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white"
            >
              Today
            </button>

            {/* Recompute Solver Button */}
            <button
              onClick={handleGenerateProposal}
              disabled={generating}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 disabled:opacity-50 transition-colors"
            >
              {generating ? (
                <>
                  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  <span>Computing Slots...</span>
                </>
              ) : (
                <>
                  <Zap className="h-3.5 w-3.5" />
                  <span>Compute Schedule</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Global Alert Notices */}
        {error && (
          <div className="flex items-center gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {successBanner && (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{successBanner}</span>
          </div>
        )}

        {/* Unsaved Proposal Banner */}
        {proposal && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase text-amber-300">
                  <Sparkles className="h-3 w-3" />
                  <span>Proposed Schedule Preview (Unsaved)</span>
                </div>
                <p className="text-xs text-amber-200">
                  Review the solver&apos;s proposed blocks below. Click approve to commit and replace existing schedule blocks for {proposal.target_date}.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setProposal(null)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white"
                >
                  Discard
                </button>
                <button
                  onClick={handleApproveProposal}
                  disabled={approving}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white shadow-md hover:bg-emerald-500 disabled:opacity-50"
                >
                  {approving ? (
                    <span>Validating & Persisting...</span>
                  ) : (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Approve & Persist</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Summary metrics if available in proposal */}
            {proposal.summary && (
              <div className="grid grid-cols-2 gap-2 border-t border-amber-500/20 pt-2 text-[11px] text-amber-300 sm:grid-cols-4 font-mono">
                <div>Task Minutes: {proposal.summary.total_scheduled_task_minutes ?? 0}m</div>
                <div>Fixed Minutes: {proposal.summary.total_fixed_minutes ?? 0}m</div>
                <div>Free Minutes: {proposal.summary.total_free_minutes ?? 0}m</div>
                <div>Utilization: {(proposal.summary.utilization_percentage ?? 0).toFixed(1)}%</div>
              </div>
            )}
            {proposal.scheduling_explanation && (
              <div className="border-t border-brand-500/20 pt-2 text-xs text-brand-300">
                💡 <strong>Agent Recommendation:</strong> {proposal.scheduling_explanation}
              </div>
            )}
          </div>
        )}

        {/* Conflicts Alert */}
        {proposal && proposal.conflicts.length > 0 && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 space-y-2">
            <div className="flex items-center gap-2 text-rose-300">
              <AlertTriangle className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-wider">
                Conflicts Detected ({proposal.conflicts.length})
              </span>
            </div>
            <div className="space-y-1.5">
              {proposal.conflicts.map((c, i) => (
                <div key={i} className="text-xs text-rose-200">
                  ⚠️ Overlap between <strong>{c.block_a_title}</strong> and{" "}
                  <strong>{c.block_b_title}</strong> from{" "}
                  {new Date(c.overlap_start).toLocaleTimeString()} to{" "}
                  {new Date(c.overlap_end).toLocaleTimeString()} ({c.conflict_type})
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Unscheduled Tasks Alert */}
        {proposal && proposal.unscheduled_tasks.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-2">
            <div className="flex items-center gap-2 text-amber-400">
              <Clock className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-wider">
                Unscheduled Backlog Tasks ({proposal.unscheduled_tasks.length})
              </span>
            </div>
            <div className="space-y-1.5 text-xs text-zinc-300">
              {proposal.unscheduled_tasks.map((u, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded bg-zinc-800/40 p-2"
                >
                  <span className="font-medium text-white">{u.task_title || u.title || "Task"}</span>
                  <span className="text-[11px] text-zinc-400">
                    {u.required_minutes ?? u.estimated_duration_minutes ?? 0}m • Reason: {u.reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Main Schedule Timeline Rendering */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-brand-400" />
              <h2 className="text-sm font-semibold text-white">
                {proposal ? "Proposed Timeline" : "Active Timeline"} — {selectedDate}
              </h2>
            </div>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                proposal
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                  : savedSchedule
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-zinc-800 text-zinc-400"
              }`}
            >
              {proposal ? "Proposal Mode" : savedSchedule ? "Persisted Active" : "Empty"}
            </span>
          </div>

          {loading ? (
            <div className="py-16 text-center text-xs text-zinc-500">
              Loading schedule data...
            </div>
          ) : activeBlocks.length > 0 ? (
            <div className="relative pl-6 space-y-4 before:absolute before:bottom-2 before:left-2.5 before:top-2 before:w-0.5 before:bg-zinc-800">
              {activeBlocks
                .sort(
                  (a, b) =>
                    new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
                )
                .map((block, idx) => {
                  const startTime = new Date(block.start_time).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                  const endTime = new Date(block.end_time).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  });

                  const isFixed = block.block_type === "fixed_commitment";
                  const isBreak = block.block_type === "break";
                  const isBuffer = block.block_type === "buffer";
                  const isTask = block.block_type === "task_allocation";

                  return (
                    <div key={idx} className="relative group">
                      {/* Timeline dot */}
                      <div
                        className={`absolute -left-[1.8rem] top-3.5 h-3 w-3 rounded-full border-2 border-zinc-950 ${
                          isFixed
                            ? "bg-purple-500"
                            : isBreak
                            ? "bg-amber-500"
                            : isBuffer
                            ? "bg-zinc-500"
                            : "bg-brand-500"
                        }`}
                      />

                      <div
                        className={`rounded-lg border p-4 transition-all ${
                          isFixed
                            ? "border-purple-500/30 bg-purple-950/20"
                            : isBreak
                            ? "border-amber-500/30 bg-amber-950/20"
                            : isBuffer
                            ? "border-zinc-800 bg-zinc-900/20 text-zinc-400"
                            : "border-brand-500/30 bg-brand-950/20"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            {isFixed && <Lock className="h-3.5 w-3.5 text-purple-400" />}
                            {isBreak && <Coffee className="h-3.5 w-3.5 text-amber-400" />}
                            <span className="text-sm font-semibold text-white">
                              {block.title}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-zinc-400">
                              {startTime} - {endTime}
                            </span>
                            <span
                              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                                isFixed
                                  ? "bg-purple-500/20 text-purple-300"
                                  : isBreak
                                  ? "bg-amber-500/20 text-amber-300"
                                  : isBuffer
                                  ? "bg-zinc-800 text-zinc-400"
                                  : "bg-brand-500/20 text-brand-300"
                              }`}
                            >
                              {block.block_type.replace("_", " ")}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-zinc-800 p-12 text-center space-y-3">
              <Calendar className="mx-auto h-8 w-8 text-zinc-600" />
              <p className="text-sm font-medium text-zinc-300">
                No schedule computed for {selectedDate} yet.
              </p>
              <p className="text-xs text-zinc-500 max-w-sm mx-auto">
                Click &ldquo;Compute Schedule&rdquo; above to run the deterministic solver
                over your active tasks and fixed commitments, or use the Natural-Language
                Planner.
              </p>
              <button
                onClick={handleGenerateProposal}
                disabled={generating}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
              >
                <Zap className="h-3.5 w-3.5" />
                <span>Run Solver for Today</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
