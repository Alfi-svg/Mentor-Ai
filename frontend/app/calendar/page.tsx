"use client";

import React, { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  Calendar as CalendarIcon,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Info,
  Layers,
  ListPlus,
  MapPin,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sliders,
  Sparkles,
  Trash2,
  Unlink,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/ToastProvider";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  CalendarEvent,
  CalendarEventCreatePayload,
  CalendarEventUpdatePayload,
  CalendarStatus,
  CalendarTaskSyncSummary,
  ConflictCheckResult,
} from "@/lib/types";

type CalendarViewMode = "month" | "week" | "day";

export default function CalendarWorkspacePage() {
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [viewMode, setViewMode] = useState<CalendarViewMode>("week");
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [status, setStatus] = useState<CalendarStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Settings drawer & Availability tool state
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [connecting, setConnecting] = useState<boolean>(false);
  const [disconnecting, setDisconnecting] = useState<boolean>(false);
  const [disconnectConfirmOpen, setDisconnectConfirmOpen] = useState<boolean>(false);
  const [eventToDelete, setEventToDelete] = useState<CalendarEvent | null>(null);
  const [deleteLoading, setDeleteLoading] = useState<boolean>(false);
  const [unscheduledDrawerOpen, setUnscheduledDrawerOpen] = useState<boolean>(false);
  const [unscheduledTasks, setUnscheduledTasks] = useState<any[]>([]);
  const [loadingUnscheduled, setLoadingUnscheduled] = useState<boolean>(false);
  const toast = useToast();
  const [taskSyncSummary, setTaskSyncSummary] = useState<CalendarTaskSyncSummary | null>(null);
  const [conflictDate, setConflictDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [conflictResult, setConflictResult] = useState<ConflictCheckResult | null>(null);
  const [checkingConflicts, setCheckingConflicts] = useState<boolean>(false);

  // Selected event for detail/edit modal
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState<CalendarEventUpdatePayload>({});

  // Create event modal state
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [createForm, setCreateForm] = useState<CalendarEventCreatePayload>({
    title: "",
    description: "",
    start_time: new Date().toISOString().slice(0, 16),
    end_time: new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16),
    is_all_day: false,
    location: "",
  });

  // Calculate start and end of view window
  const { viewStart, viewEnd } = useMemo(() => {
    const d = new Date(currentDate);
    if (viewMode === "month") {
      const start = new Date(d.getFullYear(), d.getMonth(), 1);
      const end = new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59);
      // Pad to full weeks
      start.setDate(start.getDate() - start.getDay());
      end.setDate(end.getDate() + (6 - end.getDay()));
      return { viewStart: start, viewEnd: end };
    } else if (viewMode === "week") {
      const start = new Date(d);
      start.setDate(d.getDate() - d.getDay());
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      end.setHours(23, 59, 59, 999);
      return { viewStart: start, viewEnd: end };
    } else {
      const start = new Date(d);
      start.setHours(0, 0, 0, 0);
      const end = new Date(d);
      end.setHours(23, 59, 59, 999);
      return { viewStart: start, viewEnd: end };
    }
  }, [currentDate, viewMode]);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [fetchedEvents, calStatus, unsched] = await Promise.all([
        apiClient.getCalendarEvents({
          startTime: viewStart.toISOString(),
          endTime: viewEnd.toISOString(),
          includeTasks: true,
        }),
        apiClient.getCalendarStatus().catch(() => null),
        apiClient.getUnscheduledTasks().catch(() => []),
      ]);
      setEvents(fetchedEvents);
      if (calStatus) setStatus(calStatus);
      if (unsched) setUnscheduledTasks(unsched);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calendar events.");
    } finally {
      setLoading(false);
    }
  }, [viewStart, viewEnd]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get("settings") === "open" || sp.get("settings") === "true") {
        setIsSettingsOpen(true);
      }
      if (sp.get("connected") === "true") {
        setSuccessMessage("Google Calendar connected successfully with all required scopes.");
      }
      const err = sp.get("error");
      if (err) {
        setError(decodeURIComponent(err));
      }
    }
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const data = await apiClient.getCalendarConnectUrl();
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initiate Google Calendar connection.");
      setConnecting(false);
    }
  };

  const handleDisconnect = () => {
    setDisconnectConfirmOpen(true);
  };

  const confirmDisconnect = async () => {
    setDisconnecting(true);
    setError(null);
    try {
      await apiClient.disconnectCalendar();
      setSuccessMessage("Google Calendar disconnected.");
      toast.success("Google Calendar Disconnected", "Your Google account tokens have been revoked.");
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              is_connected: false,
              status_label: "disconnected",
              has_sufficient_scopes: false,
            }
          : null
      );
      setDisconnectConfirmOpen(false);
      await loadEvents();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to disconnect Google Calendar.";
      setError(msg);
      toast.error("Disconnection Failed", msg);
    } finally {
      setDisconnecting(false);
    }
  };

  const handleCheckConflicts = async () => {
    if (!conflictDate) return;
    setCheckingConflicts(true);
    setError(null);
    try {
      const res = await apiClient.checkConflicts(conflictDate);
      setConflictResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze conflicts and free slots.");
    } finally {
      setCheckingConflicts(false);
    }
  };

  // Date Navigation
  const handlePrev = () => {
    const d = new Date(currentDate);
    if (viewMode === "month") d.setMonth(d.getMonth() - 1);
    else if (viewMode === "week") d.setDate(d.getDate() - 7);
    else d.setDate(d.getDate() - 1);
    setCurrentDate(d);
  };

  const handleNext = () => {
    const d = new Date(currentDate);
    if (viewMode === "month") d.setMonth(d.getMonth() + 1);
    else if (viewMode === "week") d.setDate(d.getDate() + 7);
    else d.setDate(d.getDate() + 1);
    setCurrentDate(d);
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  const handleSyncTasks = async () => {
    setSyncing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await apiClient.syncCalendarTasks();
      setTaskSyncSummary(res);
      setSuccessMessage(
        `Synchronized ${res.synced} tasks to Google Calendar${res.failed > 0 ? ` (${res.failed} failed)` : ""}.`
      );
      await loadEvents();
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : "Failed to synchronize tasks.";
      if (
        msg.includes("403") ||
        msg.toLowerCase().includes("scope") ||
        msg.includes("CALENDAR_SCOPE_INSUFFICIENT")
      ) {
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                has_sufficient_scopes: false,
                status_label: "insufficient_scopes",
              }
            : null
        );
      }
      setError(msg);
    } finally {
      setSyncing(false);
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await apiClient.createCalendarEvent({
        ...createForm,
        start_time: new Date(createForm.start_time).toISOString(),
        end_time: new Date(createForm.end_time).toISOString(),
      });
      setIsCreateOpen(false);
      setSuccessMessage("Event created and saved to Google Calendar.");
      await loadEvents();
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : "Failed to create event.";
      if (
        msg.includes("403") ||
        msg.toLowerCase().includes("scope") ||
        msg.includes("CALENDAR_SCOPE_INSUFFICIENT")
      ) {
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                has_sufficient_scopes: false,
                status_label: "insufficient_scopes",
              }
            : null
        );
      }
      setError(msg);
    }
  };

  const handleUpdateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEvent) return;
    setError(null);
    try {
      const payload: CalendarEventUpdatePayload = {
        title: editForm.title,
        description: editForm.description,
        location: editForm.location,
        start_time: editForm.start_time ? new Date(editForm.start_time).toISOString() : undefined,
        end_time: editForm.end_time ? new Date(editForm.end_time).toISOString() : undefined,
      };
      await apiClient.updateCalendarEvent(selectedEvent.id, payload);
      setIsEditing(false);
      setSelectedEvent(null);
      setSuccessMessage("Event updated successfully.");
      await loadEvents();
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : "Failed to update event.";
      if (
        msg.includes("403") ||
        msg.toLowerCase().includes("scope") ||
        msg.includes("CALENDAR_SCOPE_INSUFFICIENT")
      ) {
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                has_sufficient_scopes: false,
                status_label: "insufficient_scopes",
              }
            : null
        );
      }
      setError(msg);
    }
  };

  const handleDeleteEvent = (event: CalendarEvent) => {
    setEventToDelete(event);
  };

  const confirmDeleteEvent = async () => {
    if (!eventToDelete) return;
    setDeleteLoading(true);
    setError(null);
    try {
      await apiClient.deleteCalendarEvent(eventToDelete.id);
      setSelectedEvent(null);
      setIsEditing(false);
      setSuccessMessage("Event deleted successfully.");
      toast.success("Event Deleted", `"${eventToDelete.title}" has been deleted.`);
      setEventToDelete(null);
      await loadEvents();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete event.";
      setError(msg);
      toast.error("Failed to Delete Event", msg);
    } finally {
      setDeleteLoading(false);
    }
  };

  // Helper formatting
  const formattedDateTitle = useMemo(() => {
    if (viewMode === "month") {
      return currentDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    } else if (viewMode === "week") {
      const end = new Date(viewStart);
      end.setDate(end.getDate() + 6);
      return `${viewStart.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      })} - ${end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
    } else {
      return currentDate.toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    }
  }, [currentDate, viewMode, viewStart]);

  // Day columns for week view
  const weekDays = useMemo(() => {
    const days = [];
    const curr = new Date(viewStart);
    for (let i = 0; i < 7; i++) {
      days.push(new Date(curr));
      curr.setDate(curr.getDate() + 1);
    }
    return days;
  }, [viewStart]);

  // Filter events for a given day
  const getEventsForDay = (day: Date) => {
    const dayStart = new Date(day);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(day);
    dayEnd.setHours(23, 59, 59, 999);

    return events.filter((ev) => {
      const evStart = new Date(ev.start_time);
      const evEnd = new Date(ev.end_time);
      return evStart <= dayEnd && evEnd >= dayStart;
    });
  };

  return (
    <AppShell>
      <div className="flex h-[calc(100vh-5rem)] flex-col space-y-4">
        {/* Workspace Top Bar */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-zinc-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/10 border border-brand-500/20 text-brand-400">
              <CalendarIcon className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white">{formattedDateTitle}</h1>
                <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">
                  {Intl.DateTimeFormat().resolvedOptions().timeZone}
                </span>
              </div>
              <p className="text-xs text-zinc-400">
                Unified Google Calendar & Scheduled Tasks Workspace
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* View Mode Switcher */}
            <div className="inline-flex rounded-xl border border-zinc-800/80 bg-zinc-900/60 p-1 backdrop-blur-md">
              {(["month", "week", "day"] as CalendarViewMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold capitalize transition-all ${
                    viewMode === mode
                      ? "bg-indigo-600 text-white shadow-sm border border-indigo-400/30"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>

            {/* Date Nav Controls */}
            <div className="flex items-center rounded-xl border border-zinc-800/80 bg-zinc-900/60 p-1 backdrop-blur-md">
              <button
                onClick={handlePrev}
                className="p-1 text-zinc-400 hover:text-white transition-colors rounded-lg"
                title="Previous"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={handleToday}
                className="px-2.5 py-1 text-xs font-semibold text-zinc-300 hover:text-white transition-colors rounded-lg"
              >
                Today
              </button>
              <button
                onClick={handleNext}
                className="p-1 text-zinc-400 hover:text-white transition-colors rounded-lg"
                title="Next"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            {/* Status Indicator */}
            {status?.is_connected ? (
              (status?.has_sufficient_scopes ?? true) && status?.status_label !== "insufficient_scopes" ? (
                <button
                  onClick={() => setIsSettingsOpen(true)}
                  className="hidden md:inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-all backdrop-blur-md"
                  title="Google Calendar Connected - Click for Settings"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span className="truncate max-w-[140px]">{status.account_email || "Connected"}</span>
                </button>
              ) : (
                <button
                  onClick={handleConnect}
                  disabled={connecting}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 transition-all backdrop-blur-md"
                  title="Scopes missing - Click to Reconnect"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                  <span>Missing Scopes</span>
                </button>
              )
            ) : (
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="hidden sm:inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-800/80 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:bg-zinc-700 hover:text-white transition-all backdrop-blur-md"
                title="Connect Google Calendar"
              >
                <Unlink className="h-3.5 w-3.5" />
                <span>Not Connected</span>
              </button>
            )}

            {/* Unscheduled Backlog Drawer Button */}
            <button
              onClick={() => setUnscheduledDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-800/80 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 hover:text-white transition-all backdrop-blur-md"
              title="View unscheduled tasks waiting for calendar allocation"
            >
              <ListPlus className="h-3.5 w-3.5 text-brand-400" />
              <span className="hidden sm:inline">Backlog</span>
              {unscheduledTasks.length > 0 && (
                <span className="rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {unscheduledTasks.length}
                </span>
              )}
            </button>

            {/* Settings Drawer Button */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-800/80 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 hover:text-white transition-all backdrop-blur-md"
              title="Calendar Integration Settings & Availability"
            >
              <Settings className="h-3.5 w-3.5" />
              <span className="hidden xl:inline">Settings</span>
            </button>

            {/* Sync Now Button */}
            <button
              onClick={handleSyncTasks}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-700/80 bg-zinc-800/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 transition-all backdrop-blur-md"
              title="Synchronize tasks and calendar"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin text-indigo-400" : ""}`} />
              <span className="hidden sm:inline">Sync Tasks</span>
            </button>

            {/* New Event Button */}
            <button
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-all shadow-sm border border-indigo-400/30"
            >
              <Plus className="h-4 w-4" />
              <span>New Event</span>
            </button>
          </div>
        </div>

        {/* Prominent Warning Banner if Insufficient Scopes */}
        {status?.is_connected && (!status?.has_sufficient_scopes || status?.status_label === "insufficient_scopes") && (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200 shadow-sm">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-300">
                  Google Calendar Missing Event Permissions
                </p>
                <p className="text-zinc-300 text-[11px] mt-0.5 leading-relaxed">
                  Your Google account was connected without the necessary event write/sync scope (<code className="text-amber-300 font-mono text-[10px]">https://www.googleapis.com/auth/calendar.events</code>). Creating events or syncing tasks will be rejected by Google with 403 Forbidden until you grant event management access.
                </p>
              </div>
            </div>
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 px-3.5 py-1.5 font-semibold text-white transition-colors shadow-sm"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${connecting ? "animate-spin" : ""}`} />
              <span>Reconnect Google Calendar</span>
            </button>
          </div>
        )}

        {/* Status Alerts */}
        {error && events.length > 0 && (
          <ErrorState
            compact
            title="Connection Warning"
            message={error}
            onRetry={loadEvents}
            isRetrying={loading}
          />
        )}

        {successMessage && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-400 px-1">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-brand-500" />
            <span>Scheduled Task</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            <span>Google Calendar Event</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
            <span>Task Deadline [DUE]</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-zinc-600" />
            <span>Completed Task [DONE]</span>
          </div>
        </div>

        {/* Calendar Body Grid */}
        <div className="flex-1 overflow-auto rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <div className="flex items-center gap-2 text-zinc-400 text-sm">
                <RefreshCw className="h-4 w-4 animate-spin text-brand-400" />
                <span>Loading calendar events...</span>
              </div>
            </div>
          ) : error && events.length === 0 ? (
            <div className="flex h-full items-center justify-center py-10">
              <ErrorState
                title="Unable to communicate with the Mentor AI backend"
                message={error}
                onRetry={loadEvents}
                retryLabel="Retry Connection"
                isRetrying={loading}
                details={`Connection Diagnostic:\n${error}\n\nNote: If using cloud hosting (Render free tier), backends spin down after 15 minutes of inactivity and take 30-50s to wake up on the first request.`}
              />
            </div>
          ) : viewMode === "week" ? (
            /* WEEK VIEW */
            <div className="grid grid-cols-7 gap-2 min-w-[700px] h-full">
              {weekDays.map((day, idx) => {
                const isToday =
                  day.toDateString() === new Date().toDateString();
                const dayEvents = getEventsForDay(day);
                return (
                  <div
                    key={idx}
                    className={`flex flex-col rounded-lg border p-2 min-h-[350px] transition-colors ${
                      isToday
                        ? "border-brand-500/50 bg-brand-500/5"
                        : "border-zinc-800/80 bg-zinc-900/50"
                    }`}
                  >
                    <div className="flex items-center justify-between pb-2 border-b border-zinc-800/60 mb-2">
                      <span className="text-[11px] font-bold text-zinc-400 uppercase">
                        {day.toLocaleDateString(undefined, { weekday: "short" })}
                      </span>
                      <span
                        className={`text-xs font-bold rounded-full h-6 w-6 flex items-center justify-center ${
                          isToday
                            ? "bg-brand-600 text-white"
                            : "text-zinc-300"
                        }`}
                      >
                        {day.getDate()}
                      </span>
                    </div>

                    <div className="flex-1 space-y-1.5 overflow-y-auto">
                      {dayEvents.map((ev) => {
                        const isTask = ev.source === "task";
                        const isDeadline = Boolean(ev.is_deadline || ev.title.startsWith("[DUE]"));
                        const isDone = ev.title.startsWith("[DONE]");
                        return (
                          <div
                            key={ev.id}
                            onClick={() => {
                              setSelectedEvent(ev);
                              setEditForm({
                                title: ev.title,
                                description: ev.description || "",
                                location: ev.location || "",
                                start_time: new Date(ev.start_time).toISOString().slice(0, 16),
                                end_time: new Date(ev.end_time).toISOString().slice(0, 16),
                              });
                              setIsEditing(false);
                            }}
                            className={`group cursor-pointer rounded-xl border p-2 text-xs transition-all hover:scale-[1.02] shadow-sm ${
                              isDone
                                ? "border-zinc-700/60 bg-zinc-800/50 text-zinc-400 line-through"
                                : isDeadline
                                ? "border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-400"
                                : isTask
                                ? "border-brand-500/40 bg-brand-500/10 text-white hover:border-brand-400"
                                : "border-emerald-500/40 bg-emerald-500/10 text-white hover:border-emerald-400"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-1 mb-1">
                              <span
                                className={`text-[10px] font-bold uppercase rounded px-1.5 py-0.5 ${
                                  isDone
                                    ? "bg-zinc-700 text-zinc-300"
                                    : isDeadline
                                    ? "bg-amber-600 text-white"
                                    : isTask
                                    ? "bg-brand-600 text-white"
                                    : "bg-emerald-600 text-white"
                                }`}
                              >
                                {isDone ? "Done" : isDeadline ? "Due" : isTask ? "Task" : "GCal"}
                              </span>
                              <span className="text-[10px] text-zinc-400 font-mono">
                                {new Date(ev.start_time).toLocaleTimeString([], {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </span>
                            </div>
                            <div className="font-semibold truncate">{ev.title}</div>
                            {ev.location && (
                              <div className="flex items-center gap-1 text-[10px] text-zinc-400 truncate mt-0.5">
                                <MapPin className="h-3 w-3 shrink-0" />
                                <span>{ev.location}</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {dayEvents.length === 0 && (
                        <div className="text-[11px] text-zinc-500 text-center py-6">
                          No events
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : viewMode === "day" ? (
            /* DAY VIEW */
            <div className="max-w-2xl mx-auto space-y-3">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-base font-bold text-white">
                  Events for {currentDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
                </h2>
                <span className="text-xs text-zinc-400">
                  {getEventsForDay(currentDate).length} scheduled items
                </span>
              </div>
              <div className="space-y-2">
                {getEventsForDay(currentDate).map((ev) => {
                  const isTask = ev.source === "task";
                  const isDeadline = Boolean(ev.is_deadline || ev.title.startsWith("[DUE]"));
                  const isDone = ev.title.startsWith("[DONE]");
                  return (
                    <div
                      key={ev.id}
                      onClick={() => {
                        setSelectedEvent(ev);
                        setEditForm({
                          title: ev.title,
                          description: ev.description || "",
                          location: ev.location || "",
                          start_time: new Date(ev.start_time).toISOString().slice(0, 16),
                          end_time: new Date(ev.end_time).toISOString().slice(0, 16),
                        });
                        setIsEditing(false);
                      }}
                      className={`cursor-pointer rounded-xl border p-4 text-xs transition-all hover:border-zinc-500 shadow-sm ${
                        isDone
                          ? "border-zinc-800 bg-zinc-900/40 text-zinc-400"
                          : isDeadline
                          ? "border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-400"
                          : isTask
                          ? "border-brand-500/30 bg-brand-500/10 text-white hover:border-brand-400"
                          : "border-emerald-500/30 bg-emerald-500/10 text-white hover:border-emerald-400"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-[10px] font-bold uppercase rounded px-2 py-0.5 ${
                              isDone
                                ? "bg-zinc-700 text-zinc-300"
                                : isDeadline
                                ? "bg-amber-600 text-white"
                                : isTask
                                ? "bg-brand-600 text-white"
                                : "bg-emerald-600 text-white"
                            }`}
                          >
                            {isDone ? "Done" : isDeadline ? "Deadline" : isTask ? "Task" : "Google Calendar"}
                          </span>
                          <h3 className={`text-sm font-bold ${isDone ? "line-through text-zinc-400" : isDeadline ? "text-amber-100" : "text-white"}`}>
                            {ev.title}
                          </h3>
                        </div>
                        <span className="text-xs text-zinc-400 font-mono">
                          {new Date(ev.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          {" - "}
                          {new Date(ev.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      {ev.description && (
                        <p className="text-xs text-zinc-300 line-clamp-2 mt-1">{ev.description}</p>
                      )}
                      {ev.location && (
                        <div className="flex items-center gap-1.5 text-zinc-400 text-xs mt-2">
                          <MapPin className="h-3.5 w-3.5" />
                          <span>{ev.location}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
                {getEventsForDay(currentDate).length === 0 && (
                  <div className="text-center py-16 text-zinc-400">
                    <CalendarIcon className="h-10 w-10 mx-auto text-zinc-600 mb-2" />
                    <p className="font-semibold text-sm">No events scheduled for this day</p>
                    <p className="text-xs text-zinc-500 mt-1">
                      Click &quot;New Event&quot; above to schedule a block or create tasks in the AI planner.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* MONTH VIEW */
            <div className="space-y-2">
              <div className="grid grid-cols-7 gap-1 text-center font-bold text-xs uppercase text-zinc-400 pb-2 border-b border-zinc-800">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
                  <div key={day} className="py-1">
                    {day}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1.5 auto-rows-fr">
                {Array.from({ length: 35 }).map((_, index) => {
                  const day = new Date(viewStart);
                  day.setDate(viewStart.getDate() + index);
                  const isCurrentMonth = day.getMonth() === currentDate.getMonth();
                  const isToday = day.toDateString() === new Date().toDateString();
                  const dayEvents = getEventsForDay(day);

                  return (
                    <div
                      key={index}
                      className={`min-h-[90px] rounded-lg border p-1.5 flex flex-col justify-between transition-colors ${
                        isToday
                          ? "border-brand-500/60 bg-brand-500/5"
                          : isCurrentMonth
                          ? "border-zinc-800 bg-zinc-900/50"
                          : "border-zinc-850 bg-zinc-950/40 opacity-40"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span
                          className={`text-xs font-bold ${
                            isToday
                              ? "bg-brand-600 text-white rounded-full h-5 w-5 flex items-center justify-center"
                              : "text-zinc-300"
                          }`}
                        >
                          {day.getDate()}
                        </span>
                        {dayEvents.length > 0 && (
                          <span className="text-[10px] text-zinc-400 font-semibold">
                            {dayEvents.length}
                          </span>
                        )}
                      </div>

                      <div className="space-y-1 mt-1 overflow-y-auto max-h-[60px]">
                        {dayEvents.slice(0, 2).map((ev) => {
                          const isTask = ev.source === "task";
                          const isDeadline = Boolean(ev.is_deadline || ev.title.startsWith("[DUE]"));
                          const isDone = ev.title.startsWith("[DONE]");
                          return (
                            <div
                              key={ev.id}
                              onClick={() => {
                                setSelectedEvent(ev);
                                setEditForm({
                                  title: ev.title,
                                  description: ev.description || "",
                                  location: ev.location || "",
                                  start_time: new Date(ev.start_time).toISOString().slice(0, 16),
                                  end_time: new Date(ev.end_time).toISOString().slice(0, 16),
                                });
                              }}
                              className={`cursor-pointer rounded px-1.5 py-0.5 text-[10px] font-medium truncate ${
                                isDone
                                  ? "bg-zinc-800 text-zinc-400 line-through"
                                  : isDeadline
                                  ? "bg-amber-500/20 text-amber-200 border border-amber-500/30"
                                  : isTask
                                  ? "bg-brand-600/30 text-brand-200"
                                  : "bg-emerald-600/30 text-emerald-200"
                              }`}
                            >
                              {ev.title}
                            </div>
                          );
                        })}
                        {dayEvents.length > 2 && (
                          <span className="text-[9px] text-zinc-400 font-mono block">
                            +{dayEvents.length - 2} more
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Create Event Modal */}
        {isCreateOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-6 space-y-4 shadow-2xl">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <CalendarIcon className="h-4 w-4 text-brand-400" />
                  <h2 className="text-base font-bold text-white">Create New Event</h2>
                </div>
                <button
                  onClick={() => setIsCreateOpen(false)}
                  className="text-zinc-400 hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <form onSubmit={handleCreateEvent} className="space-y-3.5 text-xs">
                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">Title</label>
                  <input
                    type="text"
                    required
                    value={createForm.title}
                    onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    placeholder="e.g. Algorithms Lecture or Team Standup"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-zinc-400 font-semibold mb-1">Start Time</label>
                    <input
                      type="datetime-local"
                      required
                      value={createForm.start_time}
                      onChange={(e) => setCreateForm({ ...createForm, start_time: e.target.value })}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-zinc-400 font-semibold mb-1">End Time</label>
                    <input
                      type="datetime-local"
                      required
                      value={createForm.end_time}
                      onChange={(e) => setCreateForm({ ...createForm, end_time: e.target.value })}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">Location (Optional)</label>
                  <input
                    type="text"
                    value={createForm.location || ""}
                    onChange={(e) => setCreateForm({ ...createForm, location: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    placeholder="e.g. Science Building Rm 302 or Zoom link"
                  />
                </div>

                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">Description (Optional)</label>
                  <textarea
                    rows={3}
                    value={createForm.description || ""}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    placeholder="Notes or agenda..."
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={() => setIsCreateOpen(false)}
                    className="rounded-lg border border-zinc-700 px-3.5 py-1.5 text-zinc-300 hover:bg-zinc-800 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="rounded-lg bg-brand-600 px-4 py-1.5 font-semibold text-white hover:bg-brand-500 transition-colors"
                  >
                    Save Event
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* View / Edit Event Modal */}
        {selectedEvent && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-6 space-y-4 shadow-2xl">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-bold uppercase rounded px-2 py-0.5 ${
                      selectedEvent.source === "task" ? "bg-brand-600 text-white" : "bg-emerald-600 text-white"
                    }`}
                  >
                    {selectedEvent.source === "task" ? "Scheduled Task" : "Google Calendar"}
                  </span>
                  <h2 className="text-base font-bold text-white truncate max-w-[200px]">
                    {selectedEvent.title}
                  </h2>
                </div>
                <button
                  onClick={() => {
                    setSelectedEvent(null);
                    setIsEditing(false);
                  }}
                  className="text-zinc-400 hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {isEditing ? (
                <form onSubmit={handleUpdateEvent} className="space-y-3.5 text-xs">
                  <div>
                    <label className="block text-zinc-400 font-semibold mb-1">Title</label>
                    <input
                      type="text"
                      required
                      value={editForm.title || ""}
                      onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-zinc-400 font-semibold mb-1">Start Time</label>
                      <input
                        type="datetime-local"
                        required
                        value={editForm.start_time || ""}
                        onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })}
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-zinc-400 font-semibold mb-1">End Time</label>
                      <input
                        type="datetime-local"
                        required
                        value={editForm.end_time || ""}
                        onChange={(e) => setEditForm({ ...editForm, end_time: e.target.value })}
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-zinc-400 font-semibold mb-1">Location</label>
                    <input
                      type="text"
                      value={editForm.location || ""}
                      onChange={(e) => setEditForm({ ...editForm, location: e.target.value })}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-zinc-400 font-semibold mb-1">Description</label>
                    <textarea
                      rows={3}
                      value={editForm.description || ""}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    />
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-zinc-800">
                    <button
                      type="button"
                      onClick={() => setIsEditing(false)}
                      className="rounded-lg border border-zinc-700 px-3.5 py-1.5 text-zinc-300 hover:bg-zinc-800 transition-colors"
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      className="rounded-lg bg-brand-600 px-4 py-1.5 font-semibold text-white hover:bg-brand-500 transition-colors"
                    >
                      Update Event
                    </button>
                  </div>
                </form>
              ) : (
                <div className="space-y-4 text-xs">
                  <div className="space-y-1">
                    <span className="text-[10px] uppercase font-bold text-zinc-400">Time Range</span>
                    <p className="font-mono text-zinc-200">
                      {new Date(selectedEvent.start_time).toLocaleString()} -{" "}
                      {new Date(selectedEvent.end_time).toLocaleString()}
                    </p>
                  </div>

                  {selectedEvent.location && (
                    <div className="space-y-1">
                      <span className="text-[10px] uppercase font-bold text-zinc-400">Location</span>
                      <p className="text-zinc-200 flex items-center gap-1.5">
                        <MapPin className="h-3.5 w-3.5 text-brand-400" />
                        <span>{selectedEvent.location}</span>
                      </p>
                    </div>
                  )}

                  {selectedEvent.description && (
                    <div className="space-y-1">
                      <span className="text-[10px] uppercase font-bold text-zinc-400">Description</span>
                      <p className="text-zinc-300 whitespace-pre-wrap bg-zinc-850 p-3 rounded-lg border border-zinc-800">
                        {selectedEvent.description}
                      </p>
                    </div>
                  )}

                  {selectedEvent.source === "task" && (
                    <div className="rounded-lg border border-brand-500/30 bg-brand-500/10 p-3.5 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-brand-300">Linked Mentor AI Task</span>
                          {selectedEvent.priority && (
                            <span className="rounded bg-brand-500/20 px-1.5 py-0.5 text-[10px] font-bold text-brand-300 uppercase">
                              {selectedEvent.priority}
                            </span>
                          )}
                          {selectedEvent.task_status && (
                            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-300 capitalize">
                              {selectedEvent.task_status.replace("_", " ")}
                            </span>
                          )}
                        </div>
                        <Link
                          href="/tasks"
                          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-400 hover:underline"
                        >
                          <span>Manage in Tasks</span>
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      </div>
                      <p className="text-[11px] text-zinc-400 leading-relaxed">
                        Changes to scheduled times or completion synchronize automatically with Mentor AI tasks and Google Calendar.
                        {selectedEvent.calendar_sync_status && (
                          <span className="block mt-1 font-mono text-[10px] text-zinc-400">
                            Calendar Sync Status:{" "}
                            <span
                              className={`font-semibold capitalize ${
                                selectedEvent.calendar_sync_status === "synced"
                                  ? "text-emerald-400"
                                  : selectedEvent.calendar_sync_status === "reauthorization_required"
                                  ? "text-amber-400"
                                  : selectedEvent.calendar_sync_status === "failed"
                                  ? "text-rose-400"
                                  : "text-zinc-300"
                              }`}
                            >
                              {selectedEvent.calendar_sync_status.replace("_", " ")}
                            </span>
                          </span>
                        )}
                      </p>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                    <button
                      type="button"
                      onClick={() => handleDeleteEvent(selectedEvent)}
                      className="inline-flex items-center gap-1.5 text-rose-400 hover:text-rose-300 font-semibold"
                    >
                      <Trash2 className="h-4 w-4" />
                      <span>Delete</span>
                    </button>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setIsEditing(true)}
                        className="rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 font-semibold text-white hover:bg-zinc-700 transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedEvent(null)}
                        className="rounded-lg bg-brand-600 px-3.5 py-1.5 font-semibold text-white hover:bg-brand-500 transition-colors"
                      >
                        Close
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Settings & Availability Drawer */}
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-sm p-0 sm:p-4 animate-in fade-in duration-150">
            <div className="flex h-full w-full max-w-lg flex-col rounded-none sm:rounded-2xl border-l sm:border border-zinc-800 bg-zinc-900 p-5 shadow-2xl overflow-y-auto">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-4">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600/10 text-brand-400">
                    <Sliders className="h-4 w-4" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white">Calendar Settings & Availability</h2>
                    <p className="text-[11px] text-zinc-400">Manage OAuth connection, tasks sync, and busy blocks</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-5 text-xs">
                {/* Connection Box */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-850 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white flex items-center gap-1.5">
                      <CalendarIcon className="h-4 w-4 text-brand-400" />
                      Google Calendar Integration
                    </span>
                    {status?.is_connected ? (
                      (status?.has_sufficient_scopes ?? true) && status?.status_label !== "insufficient_scopes" ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="h-3 w-3" /> Connected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-400 border border-amber-500/20">
                          <AlertTriangle className="h-3 w-3" /> Missing Scopes
                        </span>
                      )
                    ) : (
                      <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400">
                        Disconnected
                      </span>
                    )}
                  </div>

                  <div className="space-y-1 text-zinc-300">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Account:</span>
                      <span className="font-mono text-zinc-200">{status?.account_email || "Not connected"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Last Synced:</span>
                      <span>{status?.last_synced_at ? new Date(status.last_synced_at).toLocaleString() : "Never"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Token Storage:</span>
                      <span className="text-emerald-400 font-medium">AES-128 Encrypted at rest</span>
                    </div>
                  </div>

                  {status?.is_connected && (!status?.has_sufficient_scopes || status?.status_label === "insufficient_scopes") && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-amber-200 text-[11px]">
                      Required scope <code className="font-mono text-amber-300">calendar.events</code> is missing. Please click Reconnect below to grant access.
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
                    <button
                      onClick={handleConnect}
                      disabled={connecting}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 px-3 py-2 text-xs font-semibold text-white transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${connecting ? "animate-spin" : ""}`} />
                      <span>{status?.is_connected ? "Reconnect Account" : "Connect Google Calendar"}</span>
                    </button>
                    {status?.is_connected && (
                      <button
                        onClick={handleDisconnect}
                        disabled={disconnecting}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-400 hover:bg-rose-500/20 transition-colors disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        <span>Disconnect</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Task Sync Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-850 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Layers className="h-4 w-4 text-brand-400" />
                      <span className="font-semibold text-white">Task & Schedule Synchronization</span>
                    </div>
                    <Link href="/tasks" className="text-[11px] text-brand-400 hover:underline flex items-center gap-1">
                      <span>Tasks Backlog</span>
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    Automatically propagates scheduled tasks into your Google Calendar. Rescheduling updates event timing; task completion updates title to <code className="text-zinc-300 font-mono">[DONE]</code>; cancellations safely prune the calendar event.
                  </p>

                  <div className="flex items-center justify-between pt-1">
                    <button
                      onClick={handleSyncTasks}
                      disabled={syncing}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2 font-semibold text-white hover:bg-zinc-700 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                      <span>{syncing ? "Synchronizing Tasks..." : "Sync All Tasks Now"}</span>
                    </button>
                    {taskSyncSummary && (
                      <span className="text-[11px] text-emerald-400 font-mono">
                        Synced: {taskSyncSummary.synced} | Failed: {taskSyncSummary.failed}
                      </span>
                    )}
                  </div>
                </div>

                {/* Free Slot & Conflict Discovery Tool */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-850 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-brand-400" />
                      <span className="font-semibold text-white">Free Slot & Conflict Inspector</span>
                    </div>
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Query your Google Calendar events to find available work slots and verify absence of meeting conflicts.
                  </p>

                  <div className="flex items-center gap-2">
                    <input
                      type="date"
                      value={conflictDate}
                      onChange={(e) => setConflictDate(e.target.value)}
                      className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                    />
                    <button
                      onClick={handleCheckConflicts}
                      disabled={checkingConflicts}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 font-semibold text-white hover:bg-zinc-700 transition-colors disabled:opacity-50"
                    >
                      {checkingConflicts ? "Analyzing..." : "Check Availability"}
                    </button>
                  </div>

                  {conflictResult && (
                    <div className="mt-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{conflictResult.target_date}</span>
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                            conflictResult.has_conflicts
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          }`}
                        >
                          {conflictResult.has_conflicts
                            ? `${conflictResult.total_busy_minutes} Busy Min`
                            : "Fully Free"}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-zinc-500">
                          Free Slots ({conflictResult.free_slots.length})
                        </span>
                        <div className="grid gap-1.5 max-h-36 overflow-y-auto">
                          {conflictResult.free_slots.length === 0 ? (
                            <p className="text-[11px] text-zinc-500">No free slots found.</p>
                          ) : (
                            conflictResult.free_slots.map((slot, i) => (
                              <div
                                key={i}
                                className="rounded border border-zinc-800 bg-zinc-800/40 px-2 py-1 font-mono text-[11px] text-zinc-300 flex justify-between"
                              >
                                <span>
                                  {new Date(slot.start_time).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })}{" "}
                                  -{" "}
                                  {new Date(slot.end_time).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })}
                                </span>
                                <span className="text-zinc-500">{slot.duration_minutes}m</span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Scopes Security Disclosure */}
                <div className="rounded-lg border border-zinc-800/60 bg-zinc-900/30 p-3 text-[11px] text-zinc-400 space-y-1">
                  <div className="flex items-center gap-1.5 text-zinc-300 font-semibold">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Least-Privilege Policy</span>
                  </div>
                  <p>
                    Only <code className="text-amber-300 font-mono">calendar.events</code> is requested for read/write. Full root calendar access is never requested. Tokens are never exposed to the client.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Unscheduled Tasks Backlog Drawer */}
        {unscheduledDrawerOpen && (
          <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
            <div
              className="fixed inset-0"
              onClick={() => setUnscheduledDrawerOpen(false)}
            />
            <div className="relative z-10 w-full max-w-md bg-[#0c1429] border-l border-[#1e2f57] p-6 shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-200">
              <div className="flex items-center justify-between border-b border-[#1e2f57] pb-4 mb-4">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400">
                    <ListPlus className="w-4 h-4" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white tracking-tight">Task Backlog</h2>
                    <p className="text-xs text-slate-400">
                      {unscheduledTasks.length} {unscheduledTasks.length === 1 ? "task" : "tasks"} waiting for calendar time blocks
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setUnscheduledDrawerOpen(false)}
                  className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/10 transition"
                  aria-label="Close backlog drawer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {loadingUnscheduled ? (
                  <div className="flex items-center justify-center py-16 text-xs text-slate-400 gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-brand-400" />
                    <span>Loading backlog...</span>
                  </div>
                ) : unscheduledTasks.length === 0 ? (
                  <EmptyState
                    icon={<CheckCircle2 className="w-6 h-6 text-emerald-400" />}
                    title="All Tasks Scheduled"
                    description="You have no pending unscheduled tasks. Any task created with a deadline or allocated by Day Planner will appear on your calendar automatically."
                  />
                ) : (
                  unscheduledTasks.map((task) => (
                    <div
                      key={task.id}
                      className="rounded-xl border border-[#1e2f57] bg-[#101b38]/60 p-4 transition-all hover:border-[#2f4984]"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                              task.priority === "P1"
                                ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                                : task.priority === "P2"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : task.priority === "P3"
                                ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                                : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                            }`}
                          >
                            {task.priority}
                          </span>
                          <span className="text-xs font-semibold text-white">
                            {task.title}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 shrink-0">
                          {task.duration_minutes || 45}m
                        </span>
                      </div>

                      {task.description && (
                        <p className="text-xs text-slate-300 line-clamp-2 mb-2">
                          {task.description}
                        </p>
                      )}

                      <div className="flex items-center justify-between pt-2 border-t border-[#1e2f57]/80 text-[11px]">
                        {task.deadline ? (
                          <span className="text-amber-300 flex items-center gap-1 font-mono text-[10px]">
                            <Clock className="w-3 h-3" />
                            Due: {new Date(task.deadline).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-[10px]">No deadline</span>
                        )}

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setCreateForm({
                                title: task.title,
                                description: task.description || "",
                                start_time: new Date().toISOString().slice(0, 16),
                                end_time: new Date(Date.now() + (task.duration_minutes || 45) * 60 * 1000).toISOString().slice(0, 16),
                                is_all_day: false,
                                location: "",
                              });
                              setUnscheduledDrawerOpen(false);
                              setIsCreateOpen(true);
                            }}
                            className="rounded-lg bg-[#625BFF]/20 border border-[#625BFF]/30 px-2.5 py-1 text-[11px] font-semibold text-[#8B5CF6] hover:bg-[#625BFF]/30 transition"
                          >
                            Schedule Block
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="pt-4 border-t border-[#1e2f57] flex items-center justify-between">
                <Link
                  href="/tasks"
                  className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition"
                  onClick={() => setUnscheduledDrawerOpen(false)}
                >
                  <span>Open Task Manager</span>
                  <ExternalLink className="w-3 h-3" />
                </Link>
                <Link
                  href="/planner"
                  className="rounded-lg bg-[#625BFF] hover:bg-[#5248E5] text-white px-3 py-1.5 text-xs font-semibold shadow-sm transition"
                  onClick={() => setUnscheduledDrawerOpen(false)}
                >
                  AI Day Planner
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Disconnect Google Calendar Confirmation Dialog */}
        <ConfirmDialog
          isOpen={disconnectConfirmOpen}
          title="Disconnect Google Calendar"
          description="Are you sure you want to disconnect Google Calendar? External synchronization will be suspended and stored authentication tokens will be securely removed."
          confirmText="Disconnect Calendar"
          cancelText="Keep Connected"
          variant="danger"
          isLoading={disconnecting}
          onConfirm={confirmDisconnect}
          onCancel={() => setDisconnectConfirmOpen(false)}
        />

        {/* Delete Event Confirmation Dialog */}
        <ConfirmDialog
          isOpen={eventToDelete !== null}
          title="Delete Calendar Event"
          description={
            eventToDelete ? (
              <span>
                Are you sure you want to delete event{" "}
                <strong className="text-white">&quot;{eventToDelete.title}&quot;</strong>? This
                will also remove the event from Google Calendar if connected.
              </span>
            ) : null
          }
          confirmText="Delete Event"
          cancelText="Keep Event"
          variant="danger"
          isLoading={deleteLoading}
          onConfirm={confirmDeleteEvent}
          onCancel={() => setEventToDelete(null)}
        />
      </div>
    </AppShell>
  );
}
