"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Flame,
  ListTodo,
  RefreshCw,
  Sparkles,
  Watch,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { SavedSchedule, Task } from "@/lib/types";
import { MentorLogo } from "@/components/MentorLogo";

function safeFormatTime(isoString: string | null | undefined): string {
  if (!isoString) return "--:--";
  try {
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? "--:--" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "--:--";
  }
}

export default function WatchCompanionPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [todaySchedule, setTodaySchedule] = useState<SavedSchedule | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<string>("");
  const [frameMode, setFrameMode] = useState<boolean>(true); // Frame preview toggle on desktop

  const todayStr = new Date().toISOString().split("T")[0];

  // Update clock every second
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const loadWatchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tasksRes, schedRes] = await Promise.allSettled([
        apiClient.getTasks(),
        apiClient.getScheduleForDate(todayStr),
      ]);

      if (tasksRes.status === "fulfilled") {
        const val = tasksRes.value;
        setTasks(Array.isArray(val) ? val : []);
      }
      if (schedRes.status === "fulfilled") {
        setTodaySchedule(schedRes.value);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load watch companion data.");
    } finally {
      setLoading(false);
    }
  }, [todayStr]);

  useEffect(() => {
    loadWatchData();
  }, [loadWatchData]);

  // Identify next focus commitment or task
  const scheduleBlocks = Array.isArray(todaySchedule?.blocks) ? todaySchedule.blocks : [];
  const nextCommitment = scheduleBlocks
    .filter((b) => b && !b.is_completed)
    .sort((a, b) => {
      const ta = a.start_time ? new Date(a.start_time).getTime() : 0;
      const tb = b.start_time ? new Date(b.start_time).getTime() : 0;
      return ta - tb;
    })[0];

  const pendingTasks = tasks.filter((t) => t.status === "pending" || t.status === "in_progress");
  const urgentTask = pendingTasks.find((t) => t.priority === "P1") || pendingTasks[0];

  // Watch Screen Component
  const WatchScreen = (
    <div className="flex h-full w-full flex-col justify-between bg-black text-white p-5 select-none font-sans overflow-y-auto scrollbar-none rounded-[42px] border border-zinc-800 shadow-2xl">
      {/* Watch Top Bar: Clock & Status */}
      <div className="flex items-center justify-between border-b border-zinc-900 pb-2">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">Mentor</span>
        </div>
        <span className="text-sm font-bold font-mono tracking-tight text-white">{currentTime}</span>
      </div>

      {/* Main Focus Area */}
      <div className="my-auto py-2 space-y-2.5">
        {loading ? (
          <div className="py-6 text-center text-xs text-zinc-500">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-indigo-400" />
            <span>Syncing...</span>
          </div>
        ) : error ? (
          <div className="py-4 text-center text-xs text-rose-400">
            <AlertCircle className="h-5 w-5 mx-auto mb-1 text-rose-400" />
            <span className="text-[10px] leading-tight block">{error}</span>
          </div>
        ) : nextCommitment ? (
          <div className="space-y-1.5 rounded-2xl bg-zinc-900/90 border border-indigo-500/30 p-3">
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-indigo-400">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Next Commitment
              </span>
              <span className="font-mono text-zinc-400">{safeFormatTime(nextCommitment.start_time)}</span>
            </div>
            <p className="text-xs font-bold text-white line-clamp-2 leading-tight">
              {nextCommitment.title}
            </p>
            <span className="inline-block text-[9px] px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 capitalize">
              {nextCommitment.block_type.replace(/_/g, " ")}
            </span>
          </div>
        ) : urgentTask ? (
          <div className="space-y-1.5 rounded-2xl bg-zinc-900/90 border border-amber-500/30 p-3">
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-amber-400">
              <span className="flex items-center gap-1">
                <Flame className="h-3 w-3" />
                Focus Task
              </span>
              <span className="font-bold">{urgentTask.priority}</span>
            </div>
            <p className="text-xs font-bold text-white line-clamp-2 leading-tight">
              {urgentTask.title}
            </p>
            <p className="text-[10px] text-zinc-400">
              {urgentTask.estimated_duration_minutes ?? urgentTask.duration_minutes ?? 45} mins
            </p>
          </div>
        ) : (
          <div className="py-6 text-center space-y-1.5">
            <CheckCircle2 className="h-6 w-6 text-emerald-400 mx-auto" />
            <p className="text-xs font-bold text-white">All Clear Today</p>
            <p className="text-[10px] text-zinc-500">Zero pending commitments</p>
          </div>
        )}

        {/* Quick Compact Stats */}
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          <div className="rounded-xl bg-zinc-900/60 p-2 text-center border border-zinc-800/80">
            <span className="block text-xs font-bold text-indigo-400">{pendingTasks.length}</span>
            <span className="text-[9px] text-zinc-500 uppercase">Tasks</span>
          </div>
          <div className="rounded-xl bg-zinc-900/60 p-2 text-center border border-zinc-800/80">
            <span className="block text-xs font-bold text-emerald-400">
              {scheduleBlocks.length}
            </span>
            <span className="text-[9px] text-zinc-500 uppercase">Blocks</span>
          </div>
        </div>
      </div>

      {/* Watch Bottom Action Pill */}
      <div className="pt-2">
        <button
          onClick={loadWatchData}
          disabled={loading}
          className="w-full flex items-center justify-center gap-1.5 rounded-xl bg-zinc-800/90 hover:bg-zinc-700 py-2 text-[11px] font-semibold text-white transition-colors border border-zinc-700/60"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin text-indigo-400" : ""}`} />
          <span>Sync</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-4 sm:p-8 flex flex-col items-center justify-center selection:bg-indigo-500 selection:text-white">
      {/* Top Navigation */}
      <div className="w-full max-w-2xl flex items-center justify-between mb-8">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3.5 py-1.5 text-xs font-semibold text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all backdrop-blur-md"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Dashboard</span>
        </Link>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setFrameMode(!frameMode)}
            className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-white transition-colors"
          >
            {frameMode ? "Fit to Viewport" : "Show Watch Bezel"}
          </button>
        </div>
      </div>

      {/* Watch Preview Container */}
      {frameMode ? (
        <div className="relative flex flex-col items-center">
          {/* Hardware Watch Case Simulation (44mm Apple Watch / Wear OS form factor) */}
          <div className="relative h-[360px] w-[260px] rounded-[52px] bg-gradient-to-b from-zinc-700 via-zinc-800 to-zinc-900 p-3.5 shadow-2xl ring-1 ring-white/10 border-4 border-zinc-800">
            {/* Digital Crown */}
            <div className="absolute -right-2.5 top-16 h-10 w-2 rounded-r-md bg-zinc-600 shadow-sm" />
            {/* Side Button */}
            <div className="absolute -right-2 top-32 h-14 w-1.5 rounded-r-md bg-zinc-700" />

            {/* Display screen */}
            {WatchScreen}
          </div>

          <div className="mt-8 text-center max-w-md space-y-2">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-3 py-0.5 text-xs text-emerald-400 font-semibold">
              <Watch className="h-3.5 w-3.5" />
              <span>Smartwatch Web Companion Mode</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Provides an ultra-compact, high-contrast, OLED-optimized companion view designed for watch displays.
              Displays today&apos;s next commitment, priority task, and one-tap manual sync.
            </p>
          </div>
        </div>
      ) : (
        <div className="h-[340px] w-[240px]">
          {WatchScreen}
        </div>
      )}
    </div>
  );
}
