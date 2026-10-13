"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  Lock,
  RefreshCw,
  ShieldCheck,
  Unlink,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { CalendarStatus, ConflictCheckResult } from "@/lib/types";

export default function CalendarSettingsPage() {
  const [status, setStatus] = useState<CalendarStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [disconnecting, setDisconnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  // Conflict test tool state
  const [conflictDate, setConflictDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [conflictResult, setConflictResult] = useState<ConflictCheckResult | null>(null);
  const [checkingConflicts, setCheckingConflicts] = useState<boolean>(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getCalendarStatus();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calendar status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleConnect = async () => {
    setError(null);
    try {
      const res = await apiClient.getCalendarConnectUrl();
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to initiate calendar connection.");
      }
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect your Google Calendar?")) return;
    setDisconnecting(true);
    setError(null);
    setSyncMessage(null);
    try {
      await apiClient.disconnectCalendar();
      await loadStatus();
      setSyncMessage("Calendar connection successfully disconnected.");
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to disconnect calendar.");
      }
    } finally {
      setDisconnecting(false);
    }
  };

  const handleManualSync = async () => {
    setSyncing(true);
    setError(null);
    setSyncMessage(null);
    try {
      const res = await apiClient.syncCalendar(7, 14);
      setSyncMessage(
        `Sync completed: ${res.synced_count} events synchronized and normalized to UTC.`
      );
      await loadStatus();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to synchronize calendar events.");
      }
    } finally {
      setSyncing(false);
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
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to analyze conflicts.");
      }
    } finally {
      setCheckingConflicts(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="space-y-1">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-400">
            <Calendar className="h-3.5 w-3.5" />
            <span>Integrations</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Google Calendar Sync & Settings
          </h1>
          <p className="text-xs text-zinc-400">
            Bidirectional calendar integration with timezone normalization and conflict analysis.
          </p>
        </div>

        {/* Global Error Notice */}
        {error && (
          <div className="flex items-center gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* Sync Success Message */}
        {syncMessage && (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{syncMessage}</span>
          </div>
        )}

        {/* Real Status Card */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-5">
            <div className="flex items-center gap-3">
              <div
                className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                  status?.is_connected
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-zinc-800 text-zinc-400"
                }`}
              >
                <Calendar className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white">Google Calendar API v3</h2>
                <p className="text-xs text-zinc-400">
                  Provider Status:{" "}
                  <strong
                    className={
                      status?.is_connected ? "text-emerald-400" : "text-amber-400"
                    }
                  >
                    {loading
                      ? "Querying..."
                      : status?.is_connected
                      ? "Connected & Authorized"
                      : status?.message || "Not Connected"}
                  </strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {status?.is_connected ? (
                <>
                  <button
                    onClick={handleManualSync}
                    disabled={syncing}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                    <span>{syncing ? "Syncing..." : "Sync Now"}</span>
                  </button>
                  <button
                    onClick={handleDisconnect}
                    disabled={disconnecting}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2 text-xs font-semibold text-rose-400 hover:bg-zinc-700 hover:text-rose-300 disabled:opacity-50 transition-colors"
                  >
                    <Unlink className="h-3.5 w-3.5" />
                    <span>Disconnect</span>
                  </button>
                </>
              ) : (
                <button
                  onClick={handleConnect}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  <span>Connect Google Calendar</span>
                </button>
              )}
            </div>
          </div>

          {/* Connection Metadata Grid */}
          <div className="grid gap-4 sm:grid-cols-3 text-xs">
            <div className="rounded-lg border border-zinc-800 bg-zinc-800/30 p-3 space-y-1">
              <span className="text-[10px] uppercase font-bold text-zinc-400">Account</span>
              <p className="font-semibold text-white truncate">
                {status?.account_email || "No account linked"}
              </p>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-800/30 p-3 space-y-1">
              <span className="text-[10px] uppercase font-bold text-zinc-400">Last Synced</span>
              <p className="font-semibold text-white">
                {status?.last_synced_at
                  ? new Date(status.last_synced_at).toLocaleString()
                  : "Never"}
              </p>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-800/30 p-3 space-y-1">
              <span className="text-[10px] uppercase font-bold text-zinc-400">Tokens Security</span>
              <p className="font-semibold text-emerald-400">Encrypted at rest (AES-128)</p>
            </div>
          </div>

          {/* Least-Privilege Scopes Disclosure */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-800/20 p-4 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-white">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <span>Least-Privilege Scopes Enforced</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Mentor AI strictly requests only{" "}
              <code className="text-amber-300 font-mono text-[11px]">
                https://www.googleapis.com/auth/calendar.events
              </code>{" "}
              (view and edit events). Full administrative calendar access (
              <code className="line-through text-zinc-500 font-mono text-[11px]">
                calendar
              </code>
              ) is rejected. Plaintext tokens never leave the backend.
            </p>
          </div>
        </div>

        {/* Free Slot & Conflict Discovery Tool */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-brand-400" />
              <h2 className="text-sm font-semibold text-white">
                Calendar Conflict & Free Slot Inspector
              </h2>
            </div>
            <span className="text-[11px] text-zinc-400">
              Evaluates busy blocks & free slots
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              type="date"
              value={conflictDate}
              onChange={(e) => setConflictDate(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
            />
            <button
              onClick={handleCheckConflicts}
              disabled={checkingConflicts}
              className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              {checkingConflicts ? "Analyzing..." : "Check Availability"}
            </button>
          </div>

          {conflictResult && (
            <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-800/30 p-4 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white">
                  Target Date: {conflictResult.target_date}
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                    conflictResult.has_conflicts
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  }`}
                >
                  {conflictResult.has_conflicts
                    ? `${conflictResult.total_busy_minutes} Busy Minutes`
                    : "Fully Available"}
                </span>
              </div>

              {/* Free slots */}
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-zinc-400">
                  Available Working Slots ({conflictResult.free_slots.length})
                </span>
                <div className="grid gap-2 sm:grid-cols-2">
                  {conflictResult.free_slots.map((slot, i) => (
                    <div
                      key={i}
                      className="rounded border border-zinc-800 bg-zinc-900/60 p-2 font-mono text-[11px] text-zinc-300"
                    >
                      {new Date(slot.start_time).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      -{" "}
                      {new Date(slot.end_time).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      ({slot.duration_minutes}m free)
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
