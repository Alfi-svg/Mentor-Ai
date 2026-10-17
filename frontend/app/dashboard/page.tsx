"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  ListTodo,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  AlertTriangle,
  Watch,
  Plus,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient } from "@/lib/api-client";
import {
  CalendarStatus,
  SavedSchedule,
  Task,
  ActionRecord,
} from "@/lib/types";

function safeFormatTime(isoString: string | null | undefined): string {
  if (!isoString) return "--:--";
  try {
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? "--:--" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "--:--";
  }
}

function safeFormatDate(isoString: string | null | undefined): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString();
  } catch {
    return "";
  }
}

function safeBlockType(blockType: string | null | undefined): string {
  if (!blockType) return "task";
  return blockType.replace(/_/g, " ");
}

export default function DashboardPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionRecord[]>([]);
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus | null>(null);
  const [todaySchedule, setTodaySchedule] = useState<SavedSchedule | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState<boolean>(false);

  const todayStr = new Date().toISOString().split("T")[0];

  useEffect(() => {
    setMounted(true);
  }, []);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tasksRes, actionsRes, calRes, schedRes] = await Promise.allSettled([
        apiClient.getTasks(),
        apiClient.getPendingActions(),
        apiClient.getCalendarStatus(),
        apiClient.getScheduleForDate(todayStr),
      ]);

      if (tasksRes.status === "fulfilled") {
        const val = tasksRes.value;
        setTasks(Array.isArray(val) ? val : (val as unknown as { items?: Task[] })?.items || []);
      }
      if (actionsRes.status === "fulfilled") {
        const val = actionsRes.value;
        setPendingActions(Array.isArray(val) ? val : (val as unknown as { items?: ActionRecord[] })?.items || []);
      }
      if (calRes.status === "fulfilled") {
        setCalendarStatus(calRes.value);
      }
      if (schedRes.status === "fulfilled") {
        setTodaySchedule(schedRes.value);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard metrics.");
    } finally {
      setLoading(false);
    }
  }, [todayStr]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const safeTasks = Array.isArray(tasks) ? tasks : [];
  const pendingTasks = safeTasks.filter((t) => t.status === "pending" || t.status === "in_progress");
  const completedTasks = safeTasks.filter((t) => t.status === "completed");

  const scheduleBlocks = Array.isArray(todaySchedule?.blocks) ? todaySchedule.blocks : [];

  return (
    <AppShell>
      <div className="space-y-8">
        {/* Top Header Banner */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-zinc-800/80 pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Workspace Overview
            </h1>
            <p className="text-xs text-zinc-400 mt-1" suppressHydrationWarning>
              {mounted
                ? `Today is ${new Date().toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}. Deterministic scheduling active.`
                : "Today's Productivity Workspace. Deterministic scheduling active."}
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <Link
              href="/watch"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-all backdrop-blur-md"
              title="Open smartwatch companion preview"
            >
              <Watch className="h-3.5 w-3.5 text-emerald-400" />
              <span className="hidden sm:inline">Watch Companion</span>
            </Link>
            <button
              onClick={loadDashboardData}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-all backdrop-blur-md"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-indigo-400" : ""}`} />
              <span>Refresh</span>
            </button>
            <Link
              href="/tasks"
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 transition-all border border-indigo-400/30"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Add Task</span>
            </Link>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="flex items-center justify-between rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
            <button
              onClick={loadDashboardData}
              className="text-xs underline font-medium hover:text-white"
            >
              Retry
            </button>
          </div>
        )}

        {/* Natural Language Planner Quick Callout */}
        <div className="relative overflow-hidden rounded-2xl border border-indigo-500/20 bg-gradient-to-r from-indigo-950/40 via-zinc-900/50 to-zinc-900/40 p-5 shadow-sm backdrop-blur-md">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-400">
                <Sparkles className="h-3.5 w-3.5" />
                <span>AI Natural-Language Planner</span>
              </div>
              <p className="text-sm font-medium text-zinc-200">
                &ldquo;Plan my day: 2 classes from 10am to 11:30am and 2pm to 3:30pm, team sync at 4pm, and 2 hours for compiler lab.&rdquo;
              </p>
            </div>
            <Link
              href="/planner"
              className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 transition-all border border-indigo-400/30"
            >
              <span>Draft a Plan</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>

        {/* Truthful Metric Cards Grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Card 1: Pending Tasks */}
          <Link
            href="/tasks"
            className="group rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 transition-all hover:border-zinc-700 hover:bg-zinc-900/70 backdrop-blur-md shadow-sm"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Pending Tasks</span>
              <div className="rounded-xl bg-zinc-800/80 p-2 text-zinc-400 group-hover:text-indigo-400 group-hover:bg-indigo-500/10 transition-colors">
                <ListTodo className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {loading ? "..." : pendingTasks.length}
              </span>
              <span className="text-xs text-zinc-400">in backlog</span>
            </div>
          </Link>

          {/* Card 2: Today's Scheduled Blocks */}
          <Link
            href="/schedule"
            className="group rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 transition-all hover:border-zinc-700 hover:bg-zinc-900/70 backdrop-blur-md shadow-sm"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Today&apos;s Schedule</span>
              <div className="rounded-xl bg-zinc-800/80 p-2 text-zinc-400 group-hover:text-indigo-400 group-hover:bg-indigo-500/10 transition-colors">
                <Clock className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {loading
                  ? "..."
                  : todaySchedule?.blocks?.length
                  ? todaySchedule.blocks.length
                  : "0"}
              </span>
              <span className="text-xs text-zinc-400">
                {todaySchedule ? "blocks computed" : "not computed"}
              </span>
            </div>
          </Link>

          {/* Card 3: Action Approvals */}
          <Link
            href="/actions"
            className="group rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 transition-all hover:border-zinc-700 hover:bg-zinc-900/70 backdrop-blur-md shadow-sm"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Action Approvals</span>
              <div className={`rounded-xl p-2 transition-colors ${
                pendingActions.length > 0
                  ? "bg-amber-500/10 text-amber-400 animate-pulse"
                  : "bg-zinc-800/80 text-zinc-400 group-hover:text-indigo-400"
              }`}>
                <ShieldAlert className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span
                className={`text-3xl font-extrabold ${
                  pendingActions.length > 0 ? "text-amber-400" : "text-white"
                }`}
              >
                {loading ? "..." : pendingActions.length}
              </span>
              <span className="text-xs text-zinc-400">awaiting review</span>
            </div>
          </Link>

          {/* Card 4: Calendar Connection */}
          <Link
            href="/settings/calendar"
            className="group rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 transition-all hover:border-zinc-700 hover:bg-zinc-900/70 backdrop-blur-md shadow-sm"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Calendar Integration</span>
              <div className="rounded-xl bg-zinc-800/80 p-2 text-zinc-400 group-hover:text-indigo-400 group-hover:bg-indigo-500/10 transition-colors">
                <Calendar className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span
                className={`text-base font-bold ${
                  calendarStatus?.is_connected
                    ? "text-emerald-400"
                    : "text-zinc-400"
                }`}
              >
                {loading
                  ? "Checking..."
                  : calendarStatus?.is_connected
                  ? "Connected"
                  : "Disconnected"}
              </span>
              <span className="text-xs text-zinc-400">
                {calendarStatus?.provider || "google"}
              </span>
            </div>
          </Link>
        </div>

        {/* Detailed Sections Grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Section: Today's Timeline Preview */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4 backdrop-blur-md">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-white">Today&apos;s Schedule</h2>
              </div>
              <Link
                href="/schedule"
                className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
              >
                <span>Full Timeline</span>
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-zinc-500">Loading timeline...</div>
            ) : scheduleBlocks.length > 0 ? (
              <div className="space-y-2">
                {scheduleBlocks.slice(0, 5).map((block) => (
                  <div
                    key={block.id}
                    className="flex items-center justify-between rounded-xl border border-zinc-800/60 bg-zinc-950/60 p-3 text-xs"
                  >
                    <div className="space-y-0.5">
                      <p className="font-semibold text-white">{block.title}</p>
                      <p className="text-[11px] text-zinc-400 font-mono">
                        {safeFormatTime(block.start_time)} - {safeFormatTime(block.end_time)}
                      </p>
                    </div>
                    <span
                      className={`rounded-lg px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider ${
                        block.block_type === "fixed_commitment"
                          ? "bg-purple-500/10 text-purple-300 border border-purple-500/30"
                          : block.block_type === "break"
                          ? "bg-amber-500/10 text-amber-300 border border-amber-500/30"
                          : "bg-indigo-500/10 text-indigo-300 border border-indigo-500/30"
                      }`}
                    >
                      {safeBlockType(block.block_type)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center space-y-2.5">
                <Clock className="mx-auto h-7 w-7 text-zinc-600" />
                <p className="text-xs text-zinc-400 font-medium">No active schedule saved for today yet.</p>
                <Link
                  href="/schedule"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-400 hover:text-indigo-300"
                >
                  <span>Compute Deterministic Schedule</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>

          {/* Section: Priority Backlog */}
          <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4 backdrop-blur-md">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
              <div className="flex items-center gap-2">
                <ListTodo className="h-4 w-4 text-emerald-400" />
                <h2 className="text-sm font-semibold text-white">High Priority Tasks</h2>
              </div>
              <Link
                href="/tasks"
                className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
              >
                <span>View Backlog ({tasks.length})</span>
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-zinc-500">Loading tasks...</div>
            ) : pendingTasks.length > 0 ? (
              <div className="space-y-2">
                {pendingTasks.slice(0, 5).map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between rounded-xl border border-zinc-800/60 bg-zinc-950/60 p-3 text-xs"
                  >
                    <div className="space-y-0.5">
                      <p className="font-semibold text-white">{task.title}</p>
                      <p className="text-[11px] text-zinc-400">
                        {task.estimated_duration_minutes ?? task.duration_minutes ?? 45} mins
                        {task.deadline
                          ? ` • Due: ${safeFormatDate(task.deadline)}`
                          : ""}
                      </p>
                    </div>
                    <span
                      className={`rounded-lg px-2 py-0.5 text-[10px] font-bold ${
                        task.priority === "P1"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          : task.priority === "P2"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-zinc-800 text-zinc-300"
                      }`}
                    >
                      {task.priority || "P3"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center space-y-2.5">
                <CheckCircle2 className="mx-auto h-7 w-7 text-emerald-500" />
                <p className="text-xs text-zinc-400 font-medium">Backlog is clear! All scheduled tasks are done.</p>
                <Link
                  href="/tasks"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-400 hover:text-indigo-300"
                >
                  <span>Add New Task</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
