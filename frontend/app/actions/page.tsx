"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  History,
  Info,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ActionRecord, ActionVerifyResponse } from "@/lib/types";

export default function ActionsPage() {
  const [activeTab, setActiveTab] = useState<"pending" | "history">("pending");
  const [pendingActions, setPendingActions] = useState<ActionRecord[]>([]);
  const [historyActions, setHistoryActions] = useState<ActionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Verification Results Cache { [action_id]: ActionVerifyResponse }
  const [verifyResults, setVerifyResults] = useState<Record<string, ActionVerifyResponse>>({});
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingRes, historyRes] = await Promise.allSettled([
        apiClient.getPendingActions(),
        apiClient.getActionHistory(50, 0),
      ]);

      if (pendingRes.status === "fulfilled") {
        setPendingActions(pendingRes.value);
      }
      if (historyRes.status === "fulfilled") {
        setHistoryActions(historyRes.value);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load actions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleConfirmDecision = async (id: string, confirmed: boolean) => {
    setProcessingId(id);
    setError(null);
    setActionSuccess(null);
    try {
      const res = await apiClient.confirmAction(
        id,
        confirmed,
        confirmed ? undefined : "Declined by user via approval interface."
      );

      // Never report success before server confirms
      if (res.verified) {
        setActionSuccess(
          confirmed
            ? "Action approved, executed, and independently verified!"
            : "Action rejected. Zero state mutations occurred."
        );
      } else {
        setActionSuccess(
          `Action processed with status: ${res.status}.`
        );
      }

      await loadData();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to execute approval decision.");
      }
    } finally {
      setProcessingId(null);
    }
  };

  const handleVerifyProbe = async (id: string) => {
    setVerifyingId(id);
    try {
      const res = await apiClient.verifyAction(id);
      setVerifyResults((prev) => ({ ...prev, [id]: res }));
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Verification probe failed.");
      }
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>Safe Execution State Machine</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Action Approvals & Verification
            </h1>
            <p className="text-xs text-zinc-400">
              Consequential external mutations require explicit user approval. Post-conditions are verified before success is reported.
            </p>
          </div>

          {/* Tab Selector */}
          <div className="flex items-center rounded-xl border border-zinc-800/80 bg-zinc-900/60 p-1 backdrop-blur-md">
            <button
              onClick={() => setActiveTab("pending")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "pending"
                  ? "bg-indigo-600 text-white shadow-sm border border-indigo-400/30"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>Pending Approvals ({pendingActions.length})</span>
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "history"
                  ? "bg-indigo-600 text-white shadow-sm border border-indigo-400/30"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <History className="h-3.5 w-3.5" />
              <span>Audit History ({historyActions.length})</span>
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

        {/* Global Success Notice */}
        {actionSuccess && (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{actionSuccess}</span>
          </div>
        )}

        {/* Tab 1: Pending Approvals Inbox */}
        {activeTab === "pending" && (
          <div className="space-y-4">
            {loading ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-12 text-center text-xs text-zinc-500">
                Checking pending approval inbox...
              </div>
            ) : pendingActions.length > 0 ? (
              pendingActions.map((action) => (
                <div
                  key={action.id}
                  className="rounded-xl border border-amber-500/40 bg-zinc-900/60 p-6 space-y-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 pb-3">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-amber-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 border border-amber-500/30">
                        {action.action_type.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs text-zinc-400 font-mono">ID: {action.id.slice(0, 8)}...</span>
                    </div>
                    <span className="text-[11px] text-zinc-400">
                      Staged {new Date(action.created_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Proposed Parameters & Consequences */}
                  <div className="space-y-2 text-xs">
                    <div className="rounded-lg border border-zinc-800 bg-zinc-800/40 p-3.5 space-y-2">
                      <p className="font-semibold text-white">Proposed Action Payload:</p>
                      <pre className="overflow-x-auto text-[11px] font-mono text-zinc-300">
                        {JSON.stringify(action.payload, null, 2)}
                      </pre>
                    </div>

                    <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-200">
                      <Info className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                      <span>
                        <strong>Consequence Disclosure:</strong> Confirming this action will
                        permanently publish this item to your external Google Calendar and update your
                        deterministic schedule.
                      </span>
                    </div>
                  </div>

                  {/* Approval / Rejection Controls */}
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                      onClick={() => handleConfirmDecision(action.id, false)}
                      disabled={processingId === action.id}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-xs font-semibold text-rose-400 hover:bg-zinc-700 hover:text-rose-300 disabled:opacity-50 transition-colors"
                    >
                      <XCircle className="h-4 w-4" />
                      <span>Reject Action</span>
                    </button>
                    <button
                      onClick={() => handleConfirmDecision(action.id, true)}
                      disabled={processingId === action.id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-md hover:bg-emerald-500 disabled:opacity-50 transition-colors"
                    >
                      {processingId === action.id ? (
                        <span>Executing & Verifying...</span>
                      ) : (
                        <>
                          <CheckCircle2 className="h-4 w-4" />
                          <span>Approve & Execute</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-zinc-800 p-16 text-center space-y-3 bg-zinc-900/20">
                <ShieldCheck className="mx-auto h-8 w-8 text-emerald-500" />
                <p className="text-sm font-semibold text-white">No Staged Actions Awaiting Approval</p>
                <p className="text-xs text-zinc-500 max-w-sm mx-auto">
                  All systems are up to date. When an external agent or tool proposes a consequential
                  calendar mutation, it will be safely staged here for your authorization.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Audit & Action History */}
        {activeTab === "history" && (
          <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 divide-y divide-zinc-800/80 overflow-hidden">
            {loading ? (
              <div className="py-16 text-center text-xs text-zinc-500">Loading audit history...</div>
            ) : historyActions.length > 0 ? (
              historyActions.map((action) => {
                const verifyData = verifyResults[action.id];
                return (
                  <div key={action.id} className="p-4 space-y-3 hover:bg-zinc-800/20 transition-colors">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-white">
                          {action.action_type}
                        </span>
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                            action.status === "completed"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : action.status === "rejected"
                              ? "bg-zinc-800 text-zinc-400 border border-zinc-700"
                              : action.status === "failed"
                              ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          }`}
                        >
                          {action.status.replace("_", " ")}
                        </span>
                      </div>

                      <div className="flex items-center gap-3">
                        <span className="text-[11px] text-zinc-400">
                          {new Date(action.created_at).toLocaleString()}
                        </span>

                        {/* Truthful post-condition verification trigger */}
                        <button
                          onClick={() => handleVerifyProbe(action.id)}
                          disabled={verifyingId === action.id}
                          className="inline-flex items-center gap-1 rounded border border-zinc-700 bg-zinc-800/80 px-2.5 py-1 text-[11px] font-medium text-zinc-300 hover:text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
                          title="Query independent post-condition probe"
                        >
                          <RefreshCw
                            className={`h-3 w-3 ${verifyingId === action.id ? "animate-spin" : ""}`}
                          />
                          <span>Probe State</span>
                        </button>
                      </div>
                    </div>

                    {/* Error message if rejected or failed */}
                    {action.error_message && (
                      <p className="text-xs text-rose-300 font-mono">
                        Detail: {action.error_message}
                      </p>
                    )}

                    {/* Independent Verification Probe Output */}
                    {verifyData && (
                      <div
                        className={`rounded-lg border p-2.5 text-xs font-mono ${
                          verifyData.verified
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                            : "border-rose-500/30 bg-rose-500/10 text-rose-300"
                        }`}
                      >
                        <strong>Verification Probe Result:</strong>{" "}
                        {verifyData.verified
                          ? "State verified in database and provider."
                          : verifyData.error_message || "Unverified."}
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="py-16 text-center space-y-2 p-6">
                <History className="mx-auto h-8 w-8 text-zinc-600" />
                <p className="text-sm font-semibold text-white">No Action History Yet</p>
                <p className="text-xs text-zinc-500">
                  All executed or rejected consequential actions are stored in this immutable audit
                  trail.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
