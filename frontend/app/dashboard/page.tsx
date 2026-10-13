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
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient } from "@/lib/api-client";
import {
  CalendarStatus,
  SavedSchedule,
  Task,
  ActionRecord,
} from "@/lib/types";

export default function DashboardPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionRecord[]>([]);
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus | null>(null);
  const [todaySchedule, setTodaySchedule] = useState<SavedSchedule | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const todayStr = new Date().toISOString().split("T")[0];

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
  const nextCommitment = scheduleBlocks
    .filter((b) => b.block_type === "fixed_commitment" || b.block_type === "task_allocation")
    .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime())[0];

  return (
    <AppShell>
      <div className="space-y-8">
        {/* Top Greeting & Date */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Workspace Overview
            </h1>
            <p className="text-xs text-zinc-400">
              Today is{" "}
              {new Date().toLocaleDateString(undefined, {
                weekday: "long",
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
              . Deterministic engine active.
            </p>
          </div>
          <button
            onClick={loadDashboardData}
            disabled={loading}
            className="inline-flex items-center gap-2 self-start rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Data</span>
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="flex items-center justify-between rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
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

        {/* Quick Natural Language Command Callout */}
        <div className="relative overflow-hidden rounded-xl border border-brand-500/20 bg-gradient-to-r from-brand-950/40 via-zinc-900/40 to-zinc-900/40 p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-400">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Natural-Language Planner</span>
              </div>
              <p className="text-sm font-medium text-zinc-200">
                &ldquo;Mentor, plan my day tomorrow: 2 classes from 10am to 11:30am and 2pm to 3:30pm, team sync at 4pm, and 2 hours for my compiler lab.&rdquo;
              </p>
            </div>
            <Link
              href="/planner"
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
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
            className="group rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 transition-all hover:border-zinc-700 hover:bg-zinc-900/70"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Pending Tasks</span>
              <ListTodo className="h-4 w-4 text-zinc-500 group-hover:text-brand-400 transition-colors" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">
                {loading ? "..." : pendingTasks.length}
              </span>
              <span className="text-xs text-zinc-500">in backlog</span>
            </div>
          </Link>

          {/* Card 2: Today's Scheduled Blocks */}
          <Link
            href="/schedule"
            className="group rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 transition-all hover:border-zinc-700 hover:bg-zinc-900/70"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Today&apos;s Schedule</span>
              <Clock className="h-4 w-4 text-zinc-500 group-hover:text-brand-400 transition-colors" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">
                {loading
                  ? "..."
                  : todaySchedule?.blocks?.length
                  ? todaySchedule.blocks.length
                  : "0"}
              </span>
              <span className="text-xs text-zinc-500">
                {todaySchedule ? "blocks persisted" : "not computed yet"}
              </span>
            </div>
          </Link>

          {/* Card 3: Pending Approvals */}
          <Link
            href="/actions"
            className="group rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 transition-all hover:border-zinc-700 hover:bg-zinc-900/70"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Action Approvals</span>
              <ShieldAlert
                className={`h-4 w-4 ${
                  pendingActions.length > 0
                    ? "text-amber-400 animate-pulse"
                    : "text-zinc-500 group-hover:text-brand-400"
                }`}
              />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span
                className={`text-2xl font-bold ${
                  pendingActions.length > 0 ? "text-amber-400" : "text-white"
                }`}
              >
                {loading ? "..." : pendingActions.length}
              </span>
              <span className="text-xs text-zinc-500">awaiting review</span>
            </div>
          </Link>

          {/* Card 4: Calendar Connection */}
          <Link
            href="/settings/calendar"
            className="group rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 transition-all hover:border-zinc-700 hover:bg-zinc-900/70"
          >
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-xs font-medium">Calendar Integration</span>
              <Calendar className="h-4 w-4 text-zinc-500 group-hover:text-brand-400 transition-colors" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span
                className={`text-sm font-semibold ${
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
              <span className="text-xs text-zinc-500">
                {calendarStatus?.provider || "google"}
              </span>
            </div>
          </Link>
        </div>

        {/* Detailed Sections Grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Section: Today's Timeline Preview */}
          <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-brand-400" />
                <h2 className="text-sm font-semibold text-white">Today&apos;s Schedule</h2>
              </div>
              <Link
                href="/schedule"
                className="text-xs font-medium text-brand-400 hover:text-brand-300"
              >
                Full Timeline &rarr;
              </Link>
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-zinc-500">Loading timeline...</div>
            ) : scheduleBlocks.length > 0 ? (
              <div className="space-y-2">
                {scheduleBlocks.slice(0, 5).map((block) => (
                  <div
                    key={block.id}
                    className="flex items-center justify-between rounded-lg border border-zinc-800/60 bg-zinc-800/30 p-2.5 text-xs"
                  >
                    <div className="space-y-0.5">
                      <p className="font-medium text-white">{block.title}</p>
                      <p className="text-[11px] text-zinc-400 font-mono">
                        {new Date(block.start_time).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        -{" "}
                        {new Date(block.end_time).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] uppercase font-semibold ${
                        block.block_type === "fixed_commitment"
                          ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                          : block.block_type === "break"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      }`}
                    >
                      {block.block_type.replace("_", " ")}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-center space-y-2">
                <p className="text-xs text-zinc-400">No active schedule saved for today yet.</p>
                <Link
                  href="/schedule"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-400 hover:underline"
                >
                  <span>Compute Deterministic Schedule</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>

          {/* Section: Priority Backlog */}
          <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <ListTodo className="h-4 w-4 text-emerald-400" />
                <h2 className="text-sm font-semibold text-white">High Priority Tasks</h2>
              </div>
              <Link
                href="/tasks"
                className="text-xs font-medium text-brand-400 hover:text-brand-300"
              >
                View Backlog ({tasks.length}) &rarr;
              </Link>
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-zinc-500">Loading tasks...</div>
            ) : pendingTasks.length > 0 ? (
              <div className="space-y-2">
                {pendingTasks.slice(0, 5).map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between rounded-lg border border-zinc-800/60 bg-zinc-800/30 p-2.5 text-xs"
                  >
                    <div className="space-y-0.5">
                      <p className="font-medium text-white">{task.title}</p>
                      <p className="text-[11px] text-zinc-400">
                        {task.estimated_duration_minutes} mins
                        {task.deadline
                          ? ` • Due: ${new Date(task.deadline).toLocaleDateString()}`
                          : ""}
                      </p>
                    </div>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        task.priority === "P1"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          : task.priority === "P2"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      {task.priority}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-center space-y-2">
                <CheckCircle2 className="mx-auto h-6 w-6 text-emerald-500" />
                <p className="text-xs text-zinc-400">Backlog is empty or all tasks completed.</p>
                <Link
                  href="/tasks"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-400 hover:underline"
                >
                  <span>Add a Task</span>
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
