"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Globe,
  RotateCcw,
  Save,
  Sliders,
  Sparkles,
  Zap,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { UserPreferences } from "@/lib/types";

const POPULAR_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Dhaka",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const DAYS_OF_WEEK = [
  { id: 1, name: "Mon", full: "Monday" },
  { id: 2, name: "Tue", full: "Tuesday" },
  { id: 3, name: "Wed", full: "Wednesday" },
  { id: 4, name: "Thu", full: "Thursday" },
  { id: 5, name: "Fri", full: "Friday" },
  { id: 6, name: "Sat", full: "Saturday" },
  { id: 7, name: "Sun", full: "Sunday" },
];

export default function PreferencesSettingsPage() {
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form State
  const [workStartTime, setWorkStartTime] = useState<string>("09:00");
  const [workEndTime, setWorkEndTime] = useState<string>("17:00");
  const [timezone, setTimezone] = useState<string>("UTC");
  const [bufferMinutes, setBufferMinutes] = useState<number>(15);
  const [defaultTaskDuration, setDefaultTaskDuration] = useState<number>(45);
  const [maxFocusHours, setMaxFocusHours] = useState<number>(8);
  const [availableDays, setAvailableDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [autoScheduleBreaks, setAutoScheduleBreaks] = useState<boolean>(true);

  // Normalize HH:MM:SS to HH:MM for time inputs
  const toTimeString = (t?: string) => {
    if (!t) return "09:00";
    const parts = t.split(":");
    return `${parts[0].padStart(2, "0")}:${parts[1].padStart(2, "0")}`;
  };

  const loadPreferences = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getPreferences();
      if (data.work_start_time) setWorkStartTime(toTimeString(data.work_start_time));
      if (data.work_end_time) setWorkEndTime(toTimeString(data.work_end_time));
      if (data.timezone) setTimezone(data.timezone);
      if (typeof data.buffer_minutes === "number") setBufferMinutes(data.buffer_minutes);
      if (typeof data.default_task_duration === "number") setDefaultTaskDuration(data.default_task_duration);
      if (typeof data.max_focus_hours_per_day === "number") setMaxFocusHours(data.max_focus_hours_per_day);
      if (Array.isArray(data.available_days) && data.available_days.length > 0) {
        setAvailableDays(data.available_days);
      }
      if (typeof data.auto_schedule_breaks === "boolean") {
        setAutoScheduleBreaks(data.auto_schedule_breaks);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load preferences.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPreferences();
  }, [loadPreferences]);

  const toggleDay = (dayId: number) => {
    setAvailableDays((prev) => {
      if (prev.includes(dayId)) {
        if (prev.length === 1) return prev; // Keep at least one day
        return prev.filter((d) => d !== dayId).sort((a, b) => a - b);
      } else {
        return [...prev, dayId].sort((a, b) => a - b);
      }
    });
  };

  const handleDetectBrowserTimezone = () => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) {
        setTimezone(detected);
        setSuccessMessage(`Detected local timezone: ${detected}`);
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch {
      setError("Unable to automatically detect local browser timezone.");
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    // Frontend validation
    if (workStartTime === workEndTime) {
      setError("Work start time and work end time cannot be identical.");
      return;
    }
    if (availableDays.length === 0) {
      setError("At least one working day must be selected.");
      return;
    }

    setSaving(true);
    try {
      const payload: UserPreferences = {
        work_start_time: `${workStartTime}:00`,
        work_end_time: `${workEndTime}:00`,
        timezone: timezone.trim(),
        buffer_minutes: Number(bufferMinutes),
        default_task_duration: Number(defaultTaskDuration),
        max_focus_hours_per_day: Number(maxFocusHours),
        available_days: availableDays,
        auto_schedule_breaks: autoScheduleBreaks,
      };

      await apiClient.updatePreferences(payload);
      setSuccessMessage("Preferences successfully saved and synchronized.");
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to update preferences. Please check your inputs.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleResetDefaults = () => {
    setWorkStartTime("09:00");
    setWorkEndTime("17:00");
    setTimezone("UTC");
    setBufferMinutes(15);
    setDefaultTaskDuration(45);
    setMaxFocusHours(8);
    setAvailableDays([1, 2, 3, 4, 5]);
    setAutoScheduleBreaks(true);
    setSuccessMessage("Reset form to standard defaults. Click 'Save Changes' to apply.");
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-400">
              <Sliders className="h-3.5 w-3.5" />
              <span>Routine & Work Style</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              User Preferences & Scheduling Rules
            </h1>
            <p className="text-xs text-zinc-400">
              Configure your daily active hours, buffer windows, timezone, and autonomous scheduling constraints.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleResetDefaults}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
            >
              <RotateCcw className="h-3.5 w-3.5 text-zinc-400" />
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Global Error Notice */}
        {error && (
          <div className="flex items-center gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* Success Message */}
        {successMessage && (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {loading ? (
          <div className="flex h-64 items-center justify-center rounded-xl border border-zinc-800/80 bg-zinc-900/30">
            <div className="flex flex-col items-center gap-2 text-xs text-zinc-400">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
              <span>Loading preferences...</span>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6">
            {/* Working Hours & Timezone */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-6">
              <div className="flex items-center gap-2.5 border-b border-zinc-800 pb-4">
                <Clock className="h-4 w-4 text-brand-400" />
                <h2 className="text-sm font-semibold text-white">Working Hours & Timezone</h2>
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-300">
                    Day Start Time <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="time"
                    required
                    value={workStartTime}
                    onChange={(e) => setWorkStartTime(e.target.value)}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                  <p className="text-[11px] text-zinc-400">The earliest hour tasks can be scheduled.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-300">
                    Day End Time <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="time"
                    required
                    value={workEndTime}
                    onChange={(e) => setWorkEndTime(e.target.value)}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                  <p className="text-[11px] text-zinc-400">The cutoff hour for scheduling active work blocks.</p>
                </div>
              </div>

              {/* Timezone Configuration */}
              <div className="space-y-2 pt-2 border-t border-zinc-800/60">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-300 flex items-center gap-1.5">
                    <Globe className="h-3.5 w-3.5 text-zinc-400" />
                    <span>IANA Timezone</span>
                  </label>
                  <button
                    type="button"
                    onClick={handleDetectBrowserTimezone}
                    className="text-[11px] text-brand-400 hover:text-brand-300 underline font-medium"
                  >
                    Detect from browser
                  </button>
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    list="tz-options"
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    placeholder="e.g. America/New_York or UTC"
                    className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs font-mono text-white focus:border-brand-500 focus:outline-none"
                  />
                  <datalist id="tz-options">
                    {POPULAR_TIMEZONES.map((tz) => (
                      <option key={tz} value={tz} />
                    ))}
                  </datalist>
                </div>
                <p className="text-[11px] text-zinc-400">
                  All dates, deadlines, and external calendar sync events are normalized against this IANA timezone.
                </p>
              </div>
            </div>

            {/* Task Buffers & Focus Limits */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-6">
              <div className="flex items-center gap-2.5 border-b border-zinc-800 pb-4">
                <Zap className="h-4 w-4 text-brand-400" />
                <h2 className="text-sm font-semibold text-white">Pacing & Energy Constraints</h2>
              </div>

              <div className="grid gap-5 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-300">
                    Buffer Between Tasks (min)
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={60}
                    value={bufferMinutes}
                    onChange={(e) => setBufferMinutes(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                  <p className="text-[11px] text-zinc-400">Rest gap between consecutive allocations.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-300">
                    Default Task Duration (min)
                  </label>
                  <input
                    type="number"
                    min={5}
                    max={360}
                    value={defaultTaskDuration}
                    onChange={(e) => setDefaultTaskDuration(Math.max(5, parseInt(e.target.value) || 30))}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                  <p className="text-[11px] text-zinc-400">Fallback duration when not specified.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-300">
                    Max Daily Focus Hours
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={16}
                    value={maxFocusHours}
                    onChange={(e) => setMaxFocusHours(Math.max(1, parseInt(e.target.value) || 8))}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none"
                  />
                  <p className="text-[11px] text-zinc-400">Prevents algorithmic overcommitment.</p>
                </div>
              </div>
            </div>

            {/* Available Days & Breaks */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-6">
              <div className="flex items-center gap-2.5 border-b border-zinc-800 pb-4">
                <Sparkles className="h-4 w-4 text-brand-400" />
                <h2 className="text-sm font-semibold text-white">Active Days & Autonomous Breaks</h2>
              </div>

              {/* Working Days Selector */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-zinc-300 block">
                  Active Working Days ({availableDays.length} active)
                </label>
                <div className="flex flex-wrap gap-2">
                  {DAYS_OF_WEEK.map((d) => {
                    const isSelected = availableDays.includes(d.id);
                    return (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => toggleDay(d.id)}
                        className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition-colors ${
                          isSelected
                            ? "bg-brand-600 text-white shadow-sm ring-1 ring-brand-500/50"
                            : "bg-zinc-800/80 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                        }`}
                      >
                        {d.full}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[11px] text-zinc-400">
                  The AI scheduler only schedules task allocations on selected days.
                </p>
              </div>

              {/* Auto Schedule Breaks */}
              <div className="flex items-center justify-between pt-3 border-t border-zinc-800/60">
                <div className="space-y-0.5">
                  <span className="text-xs font-semibold text-white">Automatic Break Insertion</span>
                  <p className="text-[11px] text-zinc-400">
                    Automatically inject short restorative break blocks between heavy focus blocks.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoScheduleBreaks}
                    onChange={(e) => setAutoScheduleBreaks(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-brand-600"></div>
                </label>
              </div>
            </div>

            {/* Submit Button */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 disabled:opacity-50 transition-colors"
              >
                <Save className="h-4 w-4" />
                <span>{saving ? "Saving Changes..." : "Save Preferences"}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </AppShell>
  );
}
