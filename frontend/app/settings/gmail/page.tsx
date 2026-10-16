"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Inbox,
  Mail,
  RefreshCw,
  Shield,
  Sparkles,
  Trash2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  EmailTaskCandidate,
  GmailEmailSummaryResult,
  GmailMessageDetail,
  GmailMessageSummary,
  GmailStatus,
} from "@/lib/types";

export default function GmailSettingsPage() {
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [messages, setMessages] = useState<GmailMessageSummary[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [selectedSummary, setSelectedSummary] = useState<GmailEmailSummaryResult | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const fetchMessages = React.useCallback(async () => {
    setLoadingMessages(true);
    try {
      const msgs = await apiClient.listGmailMessages(undefined, 10);
      setMessages(msgs);
    } catch (err) {
      console.warn("Could not load Gmail messages", err);
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  const fetchStatus = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getGmailStatus();
      setStatus(data);
      if (data.is_connected) {
        fetchMessages();
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to load Gmail integration status.");
      }
    } finally {
      setLoading(false);
    }
  }, [fetchMessages]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleConnect = async () => {
    setError(null);
    try {
      const { authorization_url } = await apiClient.getGmailConnectUrl();
      window.location.href = authorization_url;
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Could not initiate Google OAuth connection.");
      }
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect Gmail? Stored credentials will be removed.")) {
      return;
    }
    setDisconnecting(true);
    setError(null);
    try {
      await apiClient.disconnectGmail();
      await fetchStatus();
      setMessages([]);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Failed to disconnect Gmail.");
      }
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSummarize = async (mid: string) => {
    setSummaryLoading(true);
    try {
      const res = await apiClient.summarizeGmailMessage(mid);
      setSelectedSummary(res);
    } catch (err) {
      alert("Failed to summarize email: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setSummaryLoading(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Gmail Integration</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Connect your Gmail account to extract tasks from important assignments, draft replies, and coordinate LifeOps schedules.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-3 rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {/* Connection Status Card */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-500/10 text-red-400 border border-red-500/20">
                <Mail className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-white">Google Gmail</h2>
                  {status?.is_connected ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400 border border-emerald-500/20">
                      <CheckCircle2 className="h-3 w-3" /> Connected
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-400">
                      {status?.status_label === "unconfigured" ? "Unconfigured" : "Disconnected"}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-zinc-400">
                  {status?.is_connected
                    ? `Connected as ${status.account_email || "your Google account"}`
                    : "Least-privilege OAuth: allows reading messages and creating drafts. Never sends without your explicit confirmation."}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {status?.is_connected ? (
                <>
                  <button
                    onClick={fetchMessages}
                    disabled={loadingMessages}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-700 transition"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${loadingMessages ? "animate-spin" : ""}`} />
                    Refresh Inbox
                  </button>
                  <button
                    onClick={handleDisconnect}
                    disabled={disconnecting}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-400 hover:bg-red-500/20 transition"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Disconnect
                  </button>
                </>
              ) : (
                <button
                  onClick={handleConnect}
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-xs font-medium text-white hover:bg-red-500 transition shadow-sm"
                >
                  <Mail className="h-4 w-4" />
                  Connect Gmail
                </button>
              )}
            </div>
          </div>

          {/* Scopes & Security Note */}
          <div className="mt-6 border-t border-zinc-800/60 pt-4">
            <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
              <Shield className="h-3.5 w-3.5 text-brand-400" />
              <span>Least-Privilege Security Policy:</span>
            </div>
            <p className="mt-1 text-xs text-zinc-500">
              Mentor AI only requests access to read recent emails and compose drafts. Emails are never sent automatically. Any outgoing email requires explicit human confirmation via the Two-Phase Approval framework.
            </p>
          </div>
        </div>

        {/* Selected Email Summary Modal/Card */}
        {selectedSummary && (
          <div className="rounded-xl border border-brand-500/30 bg-zinc-900/60 p-6 shadow-md space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-400" />
                <h3 className="text-sm font-semibold text-white">AI Email Summary & Verified Facts</h3>
              </div>
              <button
                onClick={() => setSelectedSummary(null)}
                className="text-xs text-zinc-400 hover:text-white"
              >
                Close
              </button>
            </div>
            <div className="text-xs text-zinc-300">
              <span className="font-semibold text-white">Subject:</span> {selectedSummary.subject}
            </div>

            <div className="space-y-2 rounded-lg bg-zinc-950/60 p-3 border border-zinc-800">
              <p className="text-[11px] uppercase font-bold tracking-wider text-emerald-400">
                Verified Facts (Stated directly in email):
              </p>
              <ul className="list-disc pl-4 space-y-1 text-xs text-zinc-300">
                {selectedSummary.verified_facts.map((fact, i) => (
                  <li key={i}>{fact}</li>
                ))}
              </ul>
            </div>

            <div className="space-y-1 rounded-lg bg-brand-950/20 p-3 border border-brand-500/20">
              <p className="text-[11px] uppercase font-bold tracking-wider text-brand-400">
                AI Interpretation & Context:
              </p>
              <p className="text-xs text-zinc-300 leading-relaxed">{selectedSummary.ai_interpretation}</p>
            </div>
          </div>
        )}

        {/* Recent Messages View */}
        {status?.is_connected && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Inbox className="h-4 w-4 text-zinc-400" />
                Recent Inbox Messages ({messages.length})
              </h3>
              <Link
                href="/planner"
                className="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1"
              >
                Launch LifeOps Planner <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            {loadingMessages ? (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-8 text-center text-sm text-zinc-400">
                Loading messages...
              </div>
            ) : messages.length === 0 ? (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/30 p-8 text-center text-sm text-zinc-500">
                No recent messages found in inbox.
              </div>
            ) : (
              <div className="divide-y divide-zinc-800/60 rounded-xl border border-zinc-800/80 bg-zinc-900/40 overflow-hidden">
                {messages.map((m) => (
                  <div key={m.id} className="p-4 hover:bg-zinc-800/30 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        {m.is_unread && (
                          <span className="h-2 w-2 rounded-full bg-brand-500" />
                        )}
                        <span className="text-xs font-semibold text-zinc-200 truncate">{m.sender}</span>
                        {m.date && <span className="text-[10px] text-zinc-500">{m.date}</span>}
                      </div>
                      <p className="text-sm font-medium text-white truncate mt-0.5">{m.subject}</p>
                      <p className="text-xs text-zinc-400 truncate mt-0.5">{m.snippet}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleSummarize(m.id)}
                        disabled={summaryLoading}
                        className="inline-flex items-center gap-1 rounded bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 transition"
                      >
                        <Sparkles className="h-3 w-3 text-brand-400" />
                        Summarize
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
