"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  AlertTriangle,
  Archive,
  ArchiveRestore,
  Calendar,
  CheckCircle2,
  CheckSquare,
  Clock,
  Edit3,
  Filter,
  Flame,
  Link as LinkIcon,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  Tag,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  Task,
  TaskCreatePayload,
  TaskPriority,
  TaskStatus,
  TaskUpdatePayload,
} from "@/lib/types";

type TabFilter = "all" | "active" | "upcoming" | "overdue" | "completed" | "archived";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Tabs
  const [activeTab, setActiveTab] = useState<TabFilter>("active");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Create Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createDuration, setCreateDuration] = useState(60);
  const [createPriority, setCreatePriority] = useState<TaskPriority>("P3");
  const [createEnergy, setCreateEnergy] = useState<"high" | "medium" | "low">("medium");
  const [createDeadline, setCreateDeadline] = useState("");
  const [createScheduledStart, setCreateScheduledStart] = useState("");
  const [createScheduledEnd, setCreateScheduledEnd] = useState("");
  const [createTags, setCreateTags] = useState("");
  const [createDependsOn, setCreateDependsOn] = useState<string>("");
  const [createLoading, setCreateLoading] = useState(false);

  // Edit Modal State
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editDuration, setEditDuration] = useState(60);
  const [editPriority, setEditPriority] = useState<TaskPriority>("P3");
  const [editEnergy, setEditEnergy] = useState<"high" | "medium" | "low">("medium");
  const [editStatus, setEditStatus] = useState<TaskStatus>("pending");
  const [editDeadline, setEditDeadline] = useState("");
  const [editScheduledStart, setEditScheduledStart] = useState("");
  const [editScheduledEnd, setEditScheduledEnd] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editDependsOn, setEditDependsOn] = useState<string>("");
  const [editLoading, setEditLoading] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // If activeTab is archived, fetch archived tasks. Otherwise fetch active tasks.
      const isArchived = activeTab === "archived";
      const data = await apiClient.getTasks({ is_archived: isArchived });
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks.");
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleToggleComplete = async (task: Task) => {
    try {
      if (task.status === "completed") {
        const updated = await apiClient.reopenTask(task.id);
        setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      } else {
        const updated = await apiClient.completeTask(task.id);
        setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to update task completion state.");
      }
    }
  };

  const handleArchiveTask = async (id: string) => {
    try {
      const updated = await apiClient.archiveTask(id);
      if (activeTab !== "archived") {
        setTasks((prev) => prev.filter((t) => t.id !== id));
      } else {
        setTasks((prev) => prev.map((t) => (t.id === id ? updated : t)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive task.");
    }
  };

  const handleUnarchiveTask = async (id: string) => {
    try {
      const updated = await apiClient.unarchiveTask(id);
      if (activeTab === "archived") {
        setTasks((prev) => prev.filter((t) => t.id !== id));
      } else {
        setTasks((prev) => prev.map((t) => (t.id === id ? updated : t)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore task.");
    }
  };

  const handleDeleteTask = async (id: string) => {
    if (!confirm("Are you sure you want to permanently delete this task?")) return;
    try {
      await apiClient.deleteTask(id);
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to delete task.");
      }
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createTitle.trim()) return;
    setCreateLoading(true);
    setError(null);
    try {
      const parsedTags = createTags
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter((t) => t.length > 0);

      const constraints: Record<string, any> = {};
      if (createDependsOn) {
        constraints.depends_on = [createDependsOn];
      }

      const payload: TaskCreatePayload = {
        title: createTitle.trim(),
        description: createDesc.trim() || null,
        duration_minutes: Number(createDuration),
        priority: createPriority,
        energy_level: createEnergy,
        deadline: createDeadline ? new Date(createDeadline).toISOString() : null,
        scheduled_start: createScheduledStart ? new Date(createScheduledStart).toISOString() : null,
        scheduled_end: createScheduledEnd ? new Date(createScheduledEnd).toISOString() : null,
        tags: parsedTags,
        constraints,
      };

      const created = await apiClient.createTask(payload);
      if (activeTab !== "archived") {
        setTasks((prev) => [created, ...prev]);
      }
      setCreateModalOpen(false);
      setCreateTitle("");
      setCreateDesc("");
      setCreateDuration(60);
      setCreatePriority("P3");
      setCreateEnergy("medium");
      setCreateDeadline("");
      setCreateScheduledStart("");
      setCreateScheduledEnd("");
      setCreateTags("");
      setCreateDependsOn("");
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to create task.");
      }
    } finally {
      setCreateLoading(false);
    }
  };

  const openEditModal = (task: Task) => {
    setEditingTask(task);
    setEditTitle(task.title);
    setEditDesc(task.description || "");
    setEditDuration(task.duration_minutes ?? task.estimated_duration_minutes ?? 60);
    setEditPriority(task.priority);
    setEditEnergy(task.energy_level || "medium");
    setEditStatus(task.status);
    setEditDeadline(task.deadline ? task.deadline.slice(0, 16) : "");
    setEditScheduledStart(task.scheduled_start ? task.scheduled_start.slice(0, 16) : "");
    setEditScheduledEnd(task.scheduled_end ? task.scheduled_end.slice(0, 16) : "");
    setEditTags((task.tags || []).join(", "));
    const rawDeps = task.constraints?.depends_on;
    setEditDependsOn(Array.isArray(rawDeps) && rawDeps.length > 0 ? String(rawDeps[0]) : "");
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTask || !editTitle.trim()) return;
    setEditLoading(true);
    setError(null);
    try {
      const parsedTags = editTags
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter((t) => t.length > 0);

      const updatedConstraints: Record<string, any> = {
        ...(editingTask.constraints || {}),
      };
      if (editDependsOn) {
        updatedConstraints.depends_on = [editDependsOn];
      } else {
        delete updatedConstraints.depends_on;
      }

      const payload: TaskUpdatePayload = {
        title: editTitle.trim(),
        description: editDesc.trim() || null,
        duration_minutes: Number(editDuration),
        priority: editPriority,
        energy_level: editEnergy,
        status: editStatus,
        deadline: editDeadline ? new Date(editDeadline).toISOString() : null,
        scheduled_start: editScheduledStart ? new Date(editScheduledStart).toISOString() : null,
        scheduled_end: editScheduledEnd ? new Date(editScheduledEnd).toISOString() : null,
        tags: parsedTags,
        constraints: updatedConstraints,
      };

      const updated = await apiClient.updateTask(editingTask.id, payload);
      setTasks((prev) => prev.map((t) => (t.id === editingTask.id ? updated : t)));
      setEditingTask(null);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to update task.");
      }
    } finally {
      setEditLoading(false);
    }
  };

  // Filter and search logic
  const nowUtc = useMemo(() => new Date(), []);

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      // Tab filter
      if (activeTab === "active" && (t.status === "completed" || t.status === "cancelled")) return false;
      if (activeTab === "completed" && t.status !== "completed") return false;
      if (activeTab === "overdue") {
        if (!t.deadline || t.status === "completed" || t.status === "cancelled") return false;
        if (new Date(t.deadline) >= nowUtc) return false;
      }
      if (activeTab === "upcoming") {
        if (!t.deadline || t.status === "completed" || t.status === "cancelled") return false;
        if (new Date(t.deadline) < nowUtc) return false;
      }

      // Priority filter
      if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;

      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = t.title.toLowerCase().includes(q);
        const matchDesc = t.description?.toLowerCase().includes(q);
        const matchTag = (t.tags || []).some((tag) => tag.toLowerCase().includes(q));
        if (!matchTitle && !matchDesc && !matchTag) return false;
      }

      return true;
    });
  }, [tasks, activeTab, priorityFilter, searchQuery, nowUtc]);

  return (
    <AppShell>
      <div className="space-y-6 max-w-6xl mx-auto">
        {/* Top Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Task Backlog
            </h1>
            <p className="text-xs text-zinc-400">
              Manage, prioritize, and track actionable tasks with deadline and dependency awareness.
            </p>
          </div>

          <button
            onClick={() => setCreateModalOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
          >
            <Plus className="h-4 w-4" />
            <span>New Task</span>
          </button>
        </div>

        {/* Global Error Notice */}
        {error && (
          <div className="flex items-center gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-rose-400 hover:text-rose-200"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Tabs Bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 pb-2">
          {(
            [
              { id: "active", label: "Active" },
              { id: "all", label: "All Tasks" },
              { id: "upcoming", label: "Upcoming Deadlines" },
              { id: "overdue", label: "Overdue" },
              { id: "completed", label: "Completed" },
              { id: "archived", label: "Archived" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                activeTab === tab.id
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filter and Search Controls */}
        <div className="flex flex-col gap-3 rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3.5 sm:flex-row sm:items-center">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search tasks by title, notes, or tags..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800/70 py-1.5 pl-9 pr-3 text-xs text-white placeholder-zinc-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Priority Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-800/70 px-2.5 py-1.5 text-xs text-zinc-300 focus:border-brand-500 focus:outline-none"
            >
              <option value="all">All Priorities</option>
              <option value="P1">P1 (Urgent)</option>
              <option value="P2">P2 (High)</option>
              <option value="P3">P3 (Medium)</option>
              <option value="P4">P4 (Low)</option>
            </select>
          </div>
        </div>

        {/* Task Cards List */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 divide-y divide-zinc-800/80 overflow-hidden">
          {loading ? (
            <div className="py-16 text-center text-xs text-zinc-500">
              <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-brand-500 border-t-transparent mb-2" />
              <p>Loading backlog tasks...</p>
            </div>
          ) : filteredTasks.length > 0 ? (
            filteredTasks.map((task) => {
              const isOverdue =
                task.deadline &&
                new Date(task.deadline) < nowUtc &&
                task.status !== "completed" &&
                task.status !== "cancelled";

              const rawDeps = task.constraints?.depends_on;
              const hasPrereq = Array.isArray(rawDeps) && rawDeps.length > 0;

              return (
                <div
                  key={task.id}
                  className="flex items-start justify-between p-4 hover:bg-zinc-800/30 transition-colors gap-3"
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <button
                      onClick={() => handleToggleComplete(task)}
                      className="mt-0.5 text-zinc-500 hover:text-emerald-400 shrink-0 transition-colors"
                      title={task.status === "completed" ? "Mark incomplete" : "Mark complete"}
                    >
                      {task.status === "completed" ? (
                        <CheckSquare className="h-5 w-5 text-emerald-500" />
                      ) : (
                        <Square className="h-5 w-5" />
                      )}
                    </button>

                    <div className="space-y-1 truncate flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p
                          className={`text-sm font-semibold truncate ${
                            task.status === "completed"
                              ? "line-through text-zinc-500"
                              : "text-white"
                          }`}
                        >
                          {task.title}
                        </p>

                        {/* Status Badge */}
                        {task.status === "in_progress" && (
                          <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-bold text-sky-400 border border-sky-500/20">
                            In Progress
                          </span>
                        )}
                        {task.status === "cancelled" && (
                          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-bold text-zinc-400">
                            Cancelled
                          </span>
                        )}

                        {/* Overdue Alert Badge */}
                        {isOverdue && (
                          <span className="flex items-center gap-1 rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-bold text-rose-400 border border-rose-500/20 animate-pulse">
                            <AlertTriangle className="h-3 w-3" />
                            Overdue
                          </span>
                        )}
                      </div>

                      {task.description && (
                        <p className="text-xs text-zinc-400 truncate">{task.description}</p>
                      )}

                      {/* Metadata Row */}
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-500 pt-0.5">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {task.duration_minutes ?? task.estimated_duration_minutes ?? 45} mins
                        </span>

                        {task.deadline && (
                          <span className={`flex items-center gap-1 ${isOverdue ? "text-rose-400 font-semibold" : ""}`}>
                            <Calendar className="h-3 w-3" />
                            Due: {new Date(task.deadline).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                          </span>
                        )}

                        {task.scheduled_start && (
                          <span className="flex items-center gap-1 text-emerald-400 font-medium">
                            <Clock className="h-3 w-3 text-emerald-400" />
                            Scheduled: {new Date(task.scheduled_start).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                          </span>
                        )}

                        {task.calendar_sync_status && (
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                            task.calendar_sync_status === "synced"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : task.calendar_sync_status === "pending"
                              ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                              : task.calendar_sync_status === "failed"
                              ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                              : "bg-zinc-800 text-zinc-400 border-zinc-700"
                          }`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${
                              task.calendar_sync_status === "synced" ? "bg-emerald-400" :
                              task.calendar_sync_status === "pending" ? "bg-sky-400 animate-pulse" :
                              task.calendar_sync_status === "failed" ? "bg-rose-400" : "bg-zinc-500"
                            }`} />
                            {task.calendar_sync_status}
                          </span>
                        )}

                        {task.energy_level && (
                          <span className="flex items-center gap-1 text-zinc-400">
                            <Zap className="h-3 w-3 text-amber-400" />
                            {task.energy_level.toUpperCase()}
                          </span>
                        )}

                        {/* Tags */}
                        {task.tags && task.tags.length > 0 && (
                          <div className="flex items-center gap-1">
                            <Tag className="h-3 w-3" />
                            {task.tags.map((tg) => (
                              <span
                                key={tg}
                                className="rounded bg-zinc-800 px-1.5 py-0.2 text-[10px] text-zinc-300"
                              >
                                #{tg}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Prerequisite Indicator */}
                        {hasPrereq && (
                          <span className="flex items-center gap-1 text-indigo-400 text-[10px]">
                            <LinkIcon className="h-3 w-3" />
                            Depends on: {String(rawDeps[0])}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions Column */}
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Priority Badge */}
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                        task.priority === "P1"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          : task.priority === "P2"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : task.priority === "P3"
                          ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                          : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      {task.priority}
                    </span>

                    {/* Edit */}
                    <button
                      onClick={() => openEditModal(task)}
                      className="p-1.5 text-zinc-500 hover:text-white rounded hover:bg-zinc-800 transition-colors"
                      title="Edit task"
                    >
                      <Edit3 className="h-4 w-4" />
                    </button>

                    {/* Archive / Unarchive */}
                    {activeTab === "archived" || task.is_archived ? (
                      <button
                        onClick={() => handleUnarchiveTask(task.id)}
                        className="p-1.5 text-zinc-500 hover:text-emerald-400 rounded hover:bg-zinc-800 transition-colors"
                        title="Restore task"
                      >
                        <ArchiveRestore className="h-4 w-4" />
                      </button>
                    ) : (
                      <button
                        onClick={() => handleArchiveTask(task.id)}
                        className="p-1.5 text-zinc-500 hover:text-amber-400 rounded hover:bg-zinc-800 transition-colors"
                        title="Archive task"
                      >
                        <Archive className="h-4 w-4" />
                      </button>
                    )}

                    {/* Delete */}
                    <button
                      onClick={() => handleDeleteTask(task.id)}
                      className="p-1.5 text-zinc-500 hover:text-rose-400 rounded hover:bg-zinc-800 transition-colors"
                      title="Permanently delete task"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="py-16 text-center space-y-3 p-6">
              <CheckCircle2 className="mx-auto h-8 w-8 text-zinc-600" />
              <p className="text-sm font-medium text-zinc-300">
                {activeTab === "overdue"
                  ? "No overdue tasks — great job staying on track!"
                  : activeTab === "archived"
                  ? "No archived tasks."
                  : "No tasks found matching your filter."}
              </p>
              <p className="text-xs text-zinc-500 max-w-sm mx-auto">
                Create a task manually or use the AI Planner to convert natural language goals into
                tasks.
              </p>
              <button
                onClick={() => setCreateModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create Task</span>
              </button>
            </div>
          )}
        </div>

        {/* Create Task Modal */}
        {createModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Plus className="h-4 w-4 text-brand-400" />
                  Create New Task
                </h2>
                <button
                  onClick={() => setCreateModalOpen(false)}
                  className="rounded p-1 text-zinc-400 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleCreateSubmit} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">Task Title *</label>
                  <input
                    type="text"
                    required
                    value={createTitle}
                    onChange={(e) => setCreateTitle(e.target.value)}
                    placeholder="e.g., Code Compiler Assignment"
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">Notes / Details</label>
                  <textarea
                    rows={2}
                    value={createDesc}
                    onChange={(e) => setCreateDesc(e.target.value)}
                    placeholder="Optional details, acceptance notes, or subtasks..."
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">
                      Duration (Minutes) *
                    </label>
                    <input
                      type="number"
                      required
                      min={5}
                      max={720}
                      value={createDuration}
                      onChange={(e) => setCreateDuration(parseInt(e.target.value) || 0)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Priority</label>
                    <select
                      value={createPriority}
                      onChange={(e) => setCreatePriority(e.target.value as TaskPriority)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="P1">P1 (Urgent)</option>
                      <option value="P2">P2 (High)</option>
                      <option value="P3">P3 (Medium)</option>
                      <option value="P4">P4 (Low)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Energy Level</label>
                    <select
                      value={createEnergy}
                      onChange={(e) => setCreateEnergy(e.target.value as "high" | "medium" | "low")}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="high">High Focus</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Optional Deadline</label>
                    <input
                      type="datetime-local"
                      value={createDeadline}
                      onChange={(e) => setCreateDeadline(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Tags (comma-separated)</label>
                    <input
                      type="text"
                      value={createTags}
                      onChange={(e) => setCreateTags(e.target.value)}
                      placeholder="e.g., cs301, lab, thesis"
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Optional Scheduled Start</label>
                    <input
                      type="datetime-local"
                      value={createScheduledStart}
                      onChange={(e) => setCreateScheduledStart(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Optional Scheduled End</label>
                    <input
                      type="datetime-local"
                      value={createScheduledEnd}
                      onChange={(e) => setCreateScheduledEnd(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Prerequisite Task Selection */}
                {tasks.length > 0 && (
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">
                      Prerequisite Dependency (Must finish before this task)
                    </label>
                    <select
                      value={createDependsOn}
                      onChange={(e) => setCreateDependsOn(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="">No prerequisite (Independent task)</option>
                      {tasks
                        .filter((t) => !t.is_archived)
                        .map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.title} ({t.priority})
                          </option>
                        ))}
                    </select>
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={() => setCreateModalOpen(false)}
                    className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createLoading}
                    className="rounded-lg bg-brand-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-brand-500 disabled:opacity-50"
                  >
                    {createLoading ? "Creating..." : "Save Task"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Edit Task Modal */}
        {editingTask && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Edit3 className="h-4 w-4 text-brand-400" />
                  Edit Task
                </h2>
                <button
                  onClick={() => setEditingTask(null)}
                  className="rounded p-1 text-zinc-400 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleEditSubmit} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">Task Title *</label>
                  <input
                    type="text"
                    required
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">Notes / Details</label>
                  <textarea
                    rows={2}
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-4 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Status</label>
                    <select
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value as TaskStatus)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="pending">Pending</option>
                      <option value="in_progress">In Progress</option>
                      <option value="completed">Completed</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Duration</label>
                    <input
                      type="number"
                      required
                      min={5}
                      max={720}
                      value={editDuration}
                      onChange={(e) => setEditDuration(parseInt(e.target.value) || 0)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Priority</label>
                    <select
                      value={editPriority}
                      onChange={(e) => setEditPriority(e.target.value as TaskPriority)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="P1">P1 (Urgent)</option>
                      <option value="P2">P2 (High)</option>
                      <option value="P3">P3 (Medium)</option>
                      <option value="P4">P4 (Low)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Energy</label>
                    <select
                      value={editEnergy}
                      onChange={(e) => setEditEnergy(e.target.value as "high" | "medium" | "low")}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    >
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Deadline</label>
                    <input
                      type="datetime-local"
                      value={editDeadline}
                      onChange={(e) => setEditDeadline(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Tags</label>
                    <input
                      type="text"
                      value={editTags}
                      onChange={(e) => setEditTags(e.target.value)}
                      placeholder="e.g., cs301, lab"
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Scheduled Start</label>
                    <input
                      type="datetime-local"
                      value={editScheduledStart}
                      onChange={(e) => setEditScheduledStart(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Scheduled End</label>
                    <input
                      type="datetime-local"
                      value={editScheduledEnd}
                      onChange={(e) => setEditScheduledEnd(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Prerequisite Selection */}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">
                    Prerequisite Dependency
                  </label>
                  <select
                    value={editDependsOn}
                    onChange={(e) => setEditDependsOn(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  >
                    <option value="">No prerequisite (Independent task)</option>
                    {tasks
                      .filter((t) => t.id !== editingTask.id && !t.is_archived)
                      .map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.title} ({t.priority})
                        </option>
                      ))}
                  </select>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={() => setEditingTask(null)}
                    className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editLoading}
                    className="rounded-lg bg-brand-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-brand-500 disabled:opacity-50"
                  >
                    {editLoading ? "Updating..." : "Save Changes"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
