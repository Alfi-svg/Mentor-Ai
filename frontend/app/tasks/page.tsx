"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  Clock,
  Filter,
  Plus,
  Search,
  Square,
  Trash2,
  X,
  Edit3,
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

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filter & Search states
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Create Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createDuration, setCreateDuration] = useState(60);
  const [createPriority, setCreatePriority] = useState<TaskPriority>("P3");
  const [createDeadline, setCreateDeadline] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  // Edit Modal
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editDuration, setEditDuration] = useState(60);
  const [editPriority, setEditPriority] = useState<TaskPriority>("P3");
  const [editDeadline, setEditDeadline] = useState("");
  const [editLoading, setEditLoading] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getTasks();
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks.");
    } finally {
      setLoading(false);
    }
  }, []);

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

  const handleDeleteTask = async (id: string) => {
    if (!confirm("Are you sure you want to delete this task?")) return;
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
      const payload: TaskCreatePayload = {
        title: createTitle.trim(),
        description: createDesc.trim() || null,
        estimated_duration_minutes: Number(createDuration),
        priority: createPriority,
        deadline: createDeadline ? new Date(createDeadline).toISOString() : null,
      };
      const created = await apiClient.createTask(payload);
      setTasks((prev) => [created, ...prev]);
      setCreateModalOpen(false);
      setCreateTitle("");
      setCreateDesc("");
      setCreateDuration(60);
      setCreatePriority("P3");
      setCreateDeadline("");
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
    setEditDuration(task.estimated_duration_minutes);
    setEditPriority(task.priority);
    setEditDeadline(task.deadline ? task.deadline.slice(0, 16) : "");
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTask || !editTitle.trim()) return;
    setEditLoading(true);
    setError(null);
    try {
      const payload: TaskUpdatePayload = {
        title: editTitle.trim(),
        description: editDesc.trim() || null,
        estimated_duration_minutes: Number(editDuration),
        priority: editPriority,
        deadline: editDeadline ? new Date(editDeadline).toISOString() : null,
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

  // Filter and search
  const filteredTasks = tasks.filter((t) => {
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = t.title.toLowerCase().includes(q);
      const matchDesc = t.description?.toLowerCase().includes(q);
      if (!matchTitle && !matchDesc) return false;
    }
    return true;
  });

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Top Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Task Backlog
            </h1>
            <p className="text-xs text-zinc-400">
              Manage your actionable tasks, durations, deadlines, and priorities.
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
          </div>
        )}

        {/* Filters and Search Bar */}
        <div className="flex flex-col gap-3 rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3.5 sm:flex-row sm:items-center">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search tasks by title or notes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800/70 py-1.5 pl-9 pr-3 text-xs text-white placeholder-zinc-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-800/70 px-2.5 py-1.5 text-xs text-zinc-300 focus:border-brand-500 focus:outline-none"
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="archived">Archived</option>
            </select>

            {/* Priority Filter */}
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

        {/* Tasks List */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 divide-y divide-zinc-800/80 overflow-hidden">
          {loading ? (
            <div className="py-16 text-center text-xs text-zinc-500">Loading backlog tasks...</div>
          ) : filteredTasks.length > 0 ? (
            filteredTasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-4 hover:bg-zinc-800/30 transition-colors gap-3"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <button
                    onClick={() => handleToggleComplete(task)}
                    className="text-zinc-500 hover:text-emerald-400 shrink-0 transition-colors"
                    title={task.status === "completed" ? "Mark incomplete" : "Mark complete"}
                  >
                    {task.status === "completed" ? (
                      <CheckSquare className="h-5 w-5 text-emerald-500" />
                    ) : (
                      <Square className="h-5 w-5" />
                    )}
                  </button>

                  <div className="space-y-0.5 truncate">
                    <p
                      className={`text-sm font-semibold truncate ${
                        task.status === "completed"
                          ? "line-through text-zinc-500"
                          : "text-white"
                      }`}
                    >
                      {task.title}
                    </p>
                    {task.description && (
                      <p className="text-xs text-zinc-400 truncate">{task.description}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                      <span>{task.estimated_duration_minutes} mins</span>
                      {task.deadline && (
                        <span>
                          • Due: {new Date(task.deadline).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
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

                  <button
                    onClick={() => openEditModal(task)}
                    className="p-1.5 text-zinc-500 hover:text-white rounded hover:bg-zinc-800 transition-colors"
                    title="Edit task"
                  >
                    <Edit3 className="h-4 w-4" />
                  </button>

                  <button
                    onClick={() => handleDeleteTask(task.id)}
                    className="p-1.5 text-zinc-500 hover:text-rose-400 rounded hover:bg-zinc-800 transition-colors"
                    title="Delete task"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="py-16 text-center space-y-3 p-6">
              <CheckCircle2 className="mx-auto h-8 w-8 text-zinc-600" />
              <p className="text-sm font-medium text-zinc-300">No matching tasks found.</p>
              <p className="text-xs text-zinc-500 max-w-sm mx-auto">
                Create a task manually or use the Natural-Language Planner to populate your
                backlog.
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
            <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider">
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
                    placeholder="Optional notes or subtasks..."
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
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
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">
                    Optional Deadline
                  </label>
                  <input
                    type="datetime-local"
                    value={createDeadline}
                    onChange={(e) => setCreateDeadline(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                </div>

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
            <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider">
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

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">
                      Duration (Minutes) *
                    </label>
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
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-zinc-300">
                    Optional Deadline
                  </label>
                  <input
                    type="datetime-local"
                    value={editDeadline}
                    onChange={(e) => setEditDeadline(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
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
