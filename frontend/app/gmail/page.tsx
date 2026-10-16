"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Inbox,
  Mail,
  Paperclip,
  PenSquare,
  RefreshCw,
  Search,
  Send,
  Settings,
  Shield,
  Sliders,
  Sparkles,
  Star,
  Tag,
  Trash2,
  Unlink,
  User,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  EmailTaskCandidate,
  GmailDraftCreate,
  GmailEmailSummaryResult,
  GmailMessageDetail,
  GmailMessageSummary,
  GmailSendPayload,
  GmailStatus,
} from "@/lib/types";

type GmailFolder = "INBOX" | "STARRED" | "SENT" | "DRAFT";

export default function GmailWorkspacePage() {
  const [activeFolder, setActiveFolder] = useState<GmailFolder>("INBOX");
  const [messages, setMessages] = useState<GmailMessageSummary[]>([]);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<GmailMessageDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loadingList, setLoadingList] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Settings drawer state
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [connecting, setConnecting] = useState<boolean>(false);
  const [disconnecting, setDisconnecting] = useState<boolean>(false);

  // AI Summarization & Task Extraction state
  const [summaryResult, setSummaryResult] = useState<GmailEmailSummaryResult | null>(null);
  const [summarizing, setSummarizing] = useState<boolean>(false);
  const [extractedTasks, setExtractedTasks] = useState<EmailTaskCandidate[] | null>(null);
  const [extracting, setExtracting] = useState<boolean>(false);

  // Compose / Draft modal state
  const [isComposeOpen, setIsComposeOpen] = useState<boolean>(false);
  const [savingDraft, setSavingDraft] = useState<boolean>(false);
  const [stagingSend, setStagingSend] = useState<boolean>(false);
  const [confirmSendOpen, setConfirmSendOpen] = useState<boolean>(false);
  const [composeForm, setComposeForm] = useState<GmailDraftCreate>({
    to: "",
    subject: "",
    body: "",
  });

  // Mobile navigation state
  const [mobilePane, setMobilePane] = useState<"list" | "detail">("list");

  // Load account status
  useEffect(() => {
    apiClient
      .getGmailStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  // Parse URL search params
  useEffect(() => {
    if (typeof window !== "undefined") {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get("settings") === "open" || sp.get("settings") === "true") {
        setIsSettingsOpen(true);
      }
      if (sp.get("connected") === "true") {
        setSuccessMessage("Gmail connected successfully with all required scopes.");
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
      const data = await apiClient.getGmailConnectUrl();
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initiate Gmail connection.");
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect Gmail?")) return;
    setDisconnecting(true);
    setError(null);
    try {
      await apiClient.disconnectGmail();
      setSuccessMessage("Gmail account disconnected.");
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
      setMessages([]);
      setSelectedMessageId(null);
      setSelectedDetail(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect Gmail.");
    } finally {
      setDisconnecting(false);
    }
  };

  // Fetch messages when folder or search query changes
  const loadMessages = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      const data = await apiClient.listGmailMessages({
        folder: activeFolder,
        query: searchQuery || undefined,
        limit: 25,
      });
      setMessages(data);
      // Auto-select first message on desktop if none selected
      if (data.length > 0 && !selectedMessageId) {
        setSelectedMessageId(data[0].id);
      }
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : "Failed to load messages.";
      if (
        msg.includes("403") ||
        msg.toLowerCase().includes("scope") ||
        msg.includes("GMAIL_SCOPE_INSUFFICIENT")
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
      setLoadingList(false);
    }
  }, [activeFolder, searchQuery, selectedMessageId]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  // Load message detail when selectedMessageId changes
  useEffect(() => {
    if (!selectedMessageId) {
      setSelectedDetail(null);
      setSummaryResult(null);
      setExtractedTasks(null);
      return;
    }

    let isMounted = true;
    setLoadingDetail(true);
    setSummaryResult(null);
    setExtractedTasks(null);

    apiClient
      .getGmailMessage(selectedMessageId)
      .then((detail) => {
        if (isMounted) setSelectedDetail(detail);
      })
      .catch((err: any) => {
        const msg = err instanceof Error ? err.message : "Failed to load message detail.";
        if (
          msg.includes("403") ||
          msg.toLowerCase().includes("scope") ||
          msg.includes("GMAIL_SCOPE_INSUFFICIENT")
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
        if (isMounted) setError(msg);
      })
      .finally(() => {
        if (isMounted) setLoadingDetail(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedMessageId]);

  // Star / Unstar message
  const handleToggleStar = async (msgId: string, currentStarred?: boolean) => {
    const nextStarred = !currentStarred;
    try {
      await apiClient.modifyGmailMessage(msgId, {
        add_label_ids: nextStarred ? ["STARRED"] : undefined,
        remove_label_ids: !nextStarred ? ["STARRED"] : undefined,
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, is_starred: nextStarred } : m))
      );
      if (selectedDetail && selectedDetail.id === msgId) {
        setSelectedDetail({ ...selectedDetail, is_starred: nextStarred });
      }
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : "Failed to update star.";
      if (
        msg.includes("403") ||
        msg.toLowerCase().includes("scope") ||
        msg.includes("GMAIL_SCOPE_INSUFFICIENT")
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

  // Mark Read / Unread
  const handleToggleUnread = async (msgId: string, currentUnread: boolean) => {
    const nextUnread = !currentUnread;
    try {
      await apiClient.modifyGmailMessage(msgId, {
        add_label_ids: nextUnread ? ["UNREAD"] : undefined,
        remove_label_ids: !nextUnread ? ["UNREAD"] : undefined,
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, is_unread: nextUnread } : m))
      );
      if (selectedDetail && selectedDetail.id === msgId) {
        const labels = new Set(selectedDetail.labels || []);
        if (nextUnread) labels.add("UNREAD");
        else labels.delete("UNREAD");
        setSelectedDetail({ ...selectedDetail, labels: Array.from(labels) });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update read state.");
    }
  };

  // Summarize email with AI
  const handleSummarize = async () => {
    if (!selectedMessageId) return;
    setSummarizing(true);
    setError(null);
    try {
      const res = await apiClient.summarizeGmailMessage(selectedMessageId);
      setSummaryResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to summarize email.");
    } finally {
      setSummarizing(false);
    }
  };

  // Extract tasks from email
  const handleExtractTasks = async () => {
    if (!selectedMessageId) return;
    setExtracting(true);
    setError(null);
    try {
      const candidates = await apiClient.extractTasksFromEmails([selectedMessageId]);
      setExtractedTasks(candidates);
      if (candidates.length === 0) {
        setSuccessMessage("No actionable tasks found in this email.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract tasks.");
    } finally {
      setExtracting(false);
    }
  };

  // Create Task from Candidate
  const handleCreateTaskFromCandidate = async (candidate: EmailTaskCandidate) => {
    try {
      await apiClient.createTask({
        title: candidate.title,
        description: candidate.description,
        estimated_duration_minutes: candidate.estimated_duration_minutes,
        priority: candidate.priority,
        deadline: candidate.proposed_deadline,
        energy_level: candidate.energy_level,
      });
      setSuccessMessage(`Created task "${candidate.title}" in your backlog.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task.");
    }
  };

  // Save Draft
  const handleSaveDraft = async () => {
    if (!composeForm.to || !composeForm.subject) {
      setError("Recipient and subject are required to save draft.");
      return;
    }
    setSavingDraft(true);
    setError(null);
    try {
      await apiClient.createGmailDraft(composeForm);
      setIsComposeOpen(false);
      setSuccessMessage("Draft saved successfully.");
      setComposeForm({ to: "", subject: "", body: "" });
      if (activeFolder === "DRAFT") loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save draft.");
    } finally {
      setSavingDraft(false);
    }
  };

  // Stage Send Email (requires confirmation)
  const handleSendEmailConfirmed = async () => {
    setStagingSend(true);
    setError(null);
    setConfirmSendOpen(false);
    try {
      const payload: GmailSendPayload = {
        to: composeForm.to,
        subject: composeForm.subject,
        body: composeForm.body,
      };
      await apiClient.stageSendEmail(payload);
      setIsComposeOpen(false);
      setSuccessMessage(
        `Email staged for delivery to ${composeForm.to}. Check Approvals to execute transmission.`
      );
      setComposeForm({ to: "", subject: "", body: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stage email transmission.");
    } finally {
      setStagingSend(false);
    }
  };

  return (
    <AppShell>
      <div className="flex h-[calc(100vh-5rem)] flex-col space-y-3">
        {/* Workspace Top Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/10 border border-brand-500/20 text-brand-400">
              <Mail className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white">Gmail Workspace</h1>
                {status?.is_connected ? (
                  (status.has_sufficient_scopes ?? true) && status.status_label !== "insufficient_scopes" ? (
                    <button
                      onClick={() => setIsSettingsOpen(true)}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2.5 py-0.5 hover:bg-emerald-500/20 transition-colors"
                      title="Gmail Connected - Click for Settings"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>{status.account_email || "Connected"}</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleConnect}
                      disabled={connecting}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-2.5 py-0.5 hover:bg-amber-500/20 transition-colors"
                      title="Scopes Missing - Click to Reconnect"
                    >
                      <AlertTriangle className="h-3 w-3 text-amber-400" />
                      <span>Missing Scopes</span>
                    </button>
                  )
                ) : (
                  <button
                    onClick={handleConnect}
                    disabled={connecting}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-zinc-400 bg-zinc-800 border border-zinc-700 rounded px-2.5 py-0.5 hover:text-white hover:bg-zinc-700 transition-colors"
                    title="Connect Gmail"
                  >
                    <Unlink className="h-2.5 w-2.5" />
                    <span>Connect Gmail</span>
                  </button>
                )}
              </div>
              <p className="text-xs text-zinc-400">
                Inbox management, email-to-task extraction, and AI summarization
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
              title="Gmail Integration Settings"
            >
              <Settings className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Settings</span>
            </button>
            <button
              onClick={() => setIsComposeOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 transition-colors shadow-sm"
            >
              <PenSquare className="h-4 w-4" />
              <span>Compose</span>
            </button>
            <button
              onClick={loadMessages}
              disabled={loadingList}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
              title="Refresh messages"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingList ? "animate-spin" : ""}`} />
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
                  Gmail Account Missing Read/Modify Permissions
                </p>
                <p className="text-zinc-300 text-[11px] mt-0.5 leading-relaxed">
                  Your Google account was connected without granting message access (<code className="text-amber-300 font-mono text-[10px]">https://www.googleapis.com/auth/gmail.readonly</code> & <code className="text-amber-300 font-mono text-[10px]">gmail.modify</code>). Google has blocked inbox retrieval with 403 Forbidden. Reconnect and select all permissions on the Google consent screen.
                </p>
              </div>
            </div>
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 px-3.5 py-1.5 font-semibold text-white transition-colors shadow-sm"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${connecting ? "animate-spin" : ""}`} />
              <span>Reconnect Gmail</span>
            </button>
          </div>
        )}

        {/* Global Notifications */}
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}
        {successMessage && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* 3-Panel Desktop Layout / Responsive Mobile */}
        <div className="flex-1 flex overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-900/40">
          {/* PANEL 1: Folders Navigation (Left) */}
          <aside className="hidden md:flex w-52 flex-col border-r border-zinc-800 bg-zinc-900/60 p-3 space-y-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 px-2 py-1">
              Mailboxes
            </span>
            {[
              { id: "INBOX", label: "Inbox", icon: Inbox },
              { id: "STARRED", label: "Starred", icon: Star },
              { id: "SENT", label: "Sent", icon: Send },
              { id: "DRAFT", label: "Drafts", icon: FileText },
            ].map((folder) => {
              const Icon = folder.icon;
              const isActive = activeFolder === folder.id;
              return (
                <button
                  key={folder.id}
                  onClick={() => {
                    setActiveFolder(folder.id as GmailFolder);
                    setMobilePane("list");
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
                    isActive
                      ? "bg-brand-600/20 text-brand-300 border border-brand-500/30"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-white"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? "text-brand-400" : "text-zinc-500"}`} />
                  <span>{folder.label}</span>
                </button>
              );
            })}
          </aside>

          {/* PANEL 2: Message List (Middle) */}
          <div
            className={`w-full md:w-80 lg:w-96 flex flex-col border-r border-zinc-800 bg-zinc-900/30 ${
              mobilePane === "detail" ? "hidden md:flex" : "flex"
            }`}
          >
            {/* Search Header */}
            <div className="p-3 border-b border-zinc-800">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Search emails..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/80 pl-8 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-brand-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Folder / Count Bar */}
            <div className="flex items-center justify-between px-3 py-2 bg-zinc-900/80 border-b border-zinc-800 text-[11px] text-zinc-400">
              <span className="font-bold text-zinc-300 capitalize">{activeFolder.toLowerCase()}</span>
              <span>{messages.length} messages</span>
            </div>

            {/* Messages List */}
            <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/60">
              {loadingList ? (
                <div className="flex items-center justify-center p-8 text-xs text-zinc-500 gap-2">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-brand-400" />
                  <span>Loading messages...</span>
                </div>
              ) : status && (!status.has_sufficient_scopes || status.status_label === "insufficient_scopes") ? (
                <div className="p-6 text-center space-y-3">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    <AlertTriangle className="h-5 w-5" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-xs font-semibold text-white">Forbidden: Missing Required Gmail Scope</h3>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      Google blocked message retrieval because read/modify permissions were not granted during authorization. Reconnect your account to approve the required scopes.
                    </p>
                  </div>
                  <button
                    onClick={handleConnect}
                    disabled={connecting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors"
                  >
                    <RefreshCw className={`h-3 w-3 ${connecting ? "animate-spin" : ""}`} />
                    <span>Reconnect Gmail</span>
                  </button>
                </div>
              ) : !status?.is_connected ? (
                <div className="p-6 text-center space-y-3">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700">
                    <Mail className="h-5 w-5" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-xs font-semibold text-white">Gmail Not Connected</h3>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      Connect your Google account to browse inbox messages, extract actionable tasks, and compose drafts.
                    </p>
                  </div>
                  <button
                    onClick={handleConnect}
                    disabled={connecting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors"
                  >
                    <Mail className="h-3 w-3" />
                    <span>Connect Gmail</span>
                  </button>
                </div>
              ) : messages.length === 0 ? (
                <div className="text-center p-8 text-xs text-zinc-500">
                  No messages found in {activeFolder.toLowerCase()}
                </div>
              ) : (
                messages.map((msg) => {
                  const isSelected = selectedMessageId === msg.id;
                  const isUnread = msg.is_unread;
                  return (
                    <div
                      key={msg.id}
                      onClick={() => {
                        setSelectedMessageId(msg.id);
                        setMobilePane("detail");
                      }}
                      className={`group cursor-pointer p-3 transition-colors ${
                        isSelected
                          ? "bg-brand-500/10 border-l-2 border-l-brand-500"
                          : isUnread
                          ? "bg-zinc-850/50 hover:bg-zinc-800/60"
                          : "hover:bg-zinc-800/40"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <div className="flex items-center gap-1.5 min-w-0">
                          {isUnread && (
                            <span className="h-2 w-2 rounded-full bg-brand-500 shrink-0" />
                          )}
                          <span
                            className={`text-xs truncate ${
                              isUnread ? "font-bold text-white" : "font-medium text-zinc-300"
                            }`}
                          >
                            {msg.sender}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleStar(msg.id, msg.is_starred);
                          }}
                          className="text-zinc-500 hover:text-amber-400 transition-colors p-0.5"
                        >
                          <Star
                            className={`h-3.5 w-3.5 ${
                              msg.is_starred
                                ? "fill-amber-400 text-amber-400"
                                : "text-zinc-600 hover:text-zinc-400"
                            }`}
                          />
                        </button>
                      </div>

                      <div
                        className={`text-xs truncate mb-1 ${
                          isUnread ? "font-semibold text-white" : "text-zinc-300"
                        }`}
                      >
                        {msg.subject || "(no subject)"}
                      </div>

                      <p className="text-[11px] text-zinc-500 line-clamp-2 leading-relaxed">
                        {msg.snippet}
                      </p>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* PANEL 3: Message Reading Pane (Right) */}
          <div
            className={`flex-1 flex flex-col bg-zinc-900/60 overflow-y-auto ${
              mobilePane === "list" ? "hidden md:flex" : "flex"
            }`}
          >
            {/* Mobile Back Button */}
            <div className="flex md:hidden items-center p-3 border-b border-zinc-800">
              <button
                onClick={() => setMobilePane("list")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand-400 hover:underline"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>Back to messages</span>
              </button>
            </div>

            {loadingDetail ? (
              <div className="flex flex-1 items-center justify-center text-xs text-zinc-500 gap-2">
                <RefreshCw className="h-4 w-4 animate-spin text-brand-400" />
                <span>Loading email details...</span>
              </div>
            ) : selectedDetail ? (
              <div className="flex-1 flex flex-col p-6 space-y-5">
                {/* Email Header */}
                <div className="space-y-3 border-b border-zinc-800 pb-4">
                  <div className="flex items-start justify-between gap-4">
                    <h2 className="text-lg font-bold text-white tracking-tight">
                      {selectedDetail.subject || "(no subject)"}
                    </h2>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() =>
                          handleToggleStar(selectedDetail.id, selectedDetail.is_starred)
                        }
                        className="rounded border border-zinc-700 bg-zinc-800 p-1.5 text-zinc-400 hover:text-amber-400"
                        title={selectedDetail.is_starred ? "Unstar" : "Star"}
                      >
                        <Star
                          className={`h-4 w-4 ${
                            selectedDetail.is_starred
                              ? "fill-amber-400 text-amber-400"
                              : ""
                          }`}
                        />
                      </button>
                      <button
                        onClick={() =>
                          handleToggleUnread(
                            selectedDetail.id,
                            selectedDetail.labels.includes("UNREAD")
                          )
                        }
                        className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs font-semibold text-zinc-300 hover:text-white"
                      >
                        {selectedDetail.labels.includes("UNREAD") ? "Mark Read" : "Mark Unread"}
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between text-xs text-zinc-400 gap-2">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2 text-zinc-200">
                        <User className="h-3.5 w-3.5 text-brand-400" />
                        <span className="font-semibold">{selectedDetail.sender}</span>
                      </div>
                      {selectedDetail.recipient && (
                        <div className="text-[11px] text-zinc-500">To: {selectedDetail.recipient}</div>
                      )}
                    </div>
                    {selectedDetail.date && (
                      <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-400">
                        <Clock className="h-3 w-3" />
                        <span>{new Date(selectedDetail.date).toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* AI LifeOps Action Toolbar */}
                <div className="flex flex-wrap items-center gap-2 bg-brand-500/5 border border-brand-500/20 rounded-lg p-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-300 mr-2">
                    <Sparkles className="h-4 w-4 text-brand-400" />
                    <span>AI LifeOps</span>
                  </div>

                  <button
                    onClick={handleSummarize}
                    disabled={summarizing}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-3 w-3 ${summarizing ? "animate-spin" : ""}`} />
                    <span>{summarizing ? "Analyzing..." : "Summarize Email"}</span>
                  </button>

                  <button
                    onClick={handleExtractTasks}
                    disabled={extracting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-3 w-3 ${extracting ? "animate-spin" : ""}`} />
                    <span>{extracting ? "Extracting..." : "Extract Tasks to Backlog"}</span>
                  </button>
                </div>

                {/* AI Summary Card (if triggered) */}
                {summaryResult && (
                  <div className="rounded-lg border border-brand-500/30 bg-zinc-900/90 p-4 space-y-3 text-xs">
                    <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                      <span className="font-bold text-white flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5 text-brand-400" />
                        <span>Verified AI Email Summary</span>
                      </span>
                      <span className="text-[10px] uppercase font-bold text-brand-400">
                        {(summaryResult.confidence_score * 100).toFixed(0)}% Confidence
                      </span>
                    </div>

                    <div className="space-y-1">
                      <span className="text-[10px] uppercase font-bold text-zinc-400">
                        Verified Facts (Ground Truth)
                      </span>
                      <ul className="list-disc list-inside space-y-1 text-zinc-300">
                        {summaryResult.verified_facts.map((fact, idx) => (
                          <li key={idx}>{fact}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="space-y-1 pt-1 border-t border-zinc-800">
                      <span className="text-[10px] uppercase font-bold text-zinc-400">
                        AI Interpretation
                      </span>
                      <p className="text-zinc-300 leading-relaxed italic">
                        {summaryResult.ai_interpretation}
                      </p>
                    </div>
                  </div>
                )}

                {/* Extracted Tasks (if triggered) */}
                {extractedTasks && extractedTasks.length > 0 && (
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3 text-xs">
                    <span className="font-bold text-white flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span>Extracted Tasks ({extractedTasks.length})</span>
                    </span>
                    <div className="space-y-2">
                      {extractedTasks.map((t, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-900/80 p-2.5"
                        >
                          <div>
                            <div className="font-semibold text-white">{t.title}</div>
                            <div className="text-[11px] text-zinc-400">
                              Duration: {t.estimated_duration_minutes}m • Priority: {t.priority}
                              {t.proposed_deadline && (
                                <span> • Due: {new Date(t.proposed_deadline).toLocaleDateString()}</span>
                              )}
                            </div>
                          </div>
                          <button
                            onClick={() => handleCreateTaskFromCandidate(t)}
                            className="rounded bg-brand-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-brand-500 transition-colors"
                          >
                            Add to Tasks
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Email Body Content */}
                <div className="flex-1 space-y-3">
                  <span className="text-[10px] uppercase font-bold text-zinc-400">Content</span>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5 text-xs text-zinc-200 leading-relaxed whitespace-pre-wrap font-sans">
                    {selectedDetail.body_plain}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center text-center p-8 text-zinc-500">
                <div>
                  <Mail className="h-10 w-10 mx-auto text-zinc-600 mb-2" />
                  <p className="font-semibold text-sm">Select an email to view</p>
                  <p className="text-xs text-zinc-600 mt-1">
                    Choose a conversation from the list to read content and extract tasks.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Compose / Draft Modal */}
        {isComposeOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-xl border border-zinc-800 bg-zinc-900 p-6 space-y-4 shadow-2xl">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <PenSquare className="h-4 w-4 text-brand-400" />
                  <h2 className="text-base font-bold text-white">Compose Message</h2>
                </div>
                <button
                  onClick={() => setIsComposeOpen(false)}
                  className="text-zinc-400 hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">To</label>
                  <input
                    type="email"
                    required
                    value={composeForm.to}
                    onChange={(e) => setComposeForm({ ...composeForm, to: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    placeholder="recipient@example.com"
                  />
                </div>

                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">Subject</label>
                  <input
                    type="text"
                    required
                    value={composeForm.subject}
                    onChange={(e) => setComposeForm({ ...composeForm, subject: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none"
                    placeholder="Subject line"
                  />
                </div>

                <div>
                  <label className="block text-zinc-400 font-semibold mb-1">Body</label>
                  <textarea
                    rows={8}
                    required
                    value={composeForm.body}
                    onChange={(e) => setComposeForm({ ...composeForm, body: e.target.value })}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-white focus:border-brand-500 focus:outline-none font-sans"
                    placeholder="Write your email here..."
                  />
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={handleSaveDraft}
                    disabled={savingDraft}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 font-semibold text-zinc-300 hover:bg-zinc-700 transition-colors"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    <span>{savingDraft ? "Saving..." : "Save Draft"}</span>
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsComposeOpen(false)}
                      className="rounded-lg border border-zinc-700 px-3.5 py-1.5 text-zinc-300 hover:bg-zinc-800 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmSendOpen(true)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-1.5 font-semibold text-white hover:bg-brand-500 transition-colors"
                    >
                      <Send className="h-3.5 w-3.5" />
                      <span>Send</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Explicit Consequential Action Confirmation Dialog for Sending Email */}
        {confirmSendOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="w-full max-w-sm rounded-xl border border-amber-500/40 bg-zinc-900 p-6 space-y-4 shadow-2xl">
              <div className="flex items-center gap-2.5 text-amber-400">
                <AlertTriangle className="h-5 w-5 shrink-0" />
                <h3 className="font-bold text-sm text-white">Confirm Email Delivery</h3>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Sending an email is an external consequential write action that cannot be undone. Are you sure you want to transmit this message to:
              </p>
              <div className="rounded border border-zinc-800 bg-zinc-850 p-2 text-xs font-mono text-zinc-200">
                To: {composeForm.to}
                <br />
                Subject: {composeForm.subject}
              </div>
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setConfirmSendOpen(false)}
                  className="rounded-lg border border-zinc-700 px-3.5 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSendEmailConfirmed}
                  disabled={stagingSend}
                  className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-amber-500 transition-colors"
                >
                  {stagingSend ? "Staging..." : "Confirm & Send"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Gmail Settings Drawer */}
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-sm p-0 sm:p-4 animate-in fade-in duration-150">
            <div className="flex h-full w-full max-w-lg flex-col rounded-none sm:rounded-2xl border-l sm:border border-zinc-800 bg-zinc-900 p-5 shadow-2xl overflow-y-auto">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-4">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600/10 text-brand-400">
                    <Sliders className="h-4 w-4" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white">Gmail Integration Settings</h2>
                    <p className="text-[11px] text-zinc-400">Account authorization, scopes, and delivery safeguards</p>
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
                {/* Account Status Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-850 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white flex items-center gap-1.5">
                      <Mail className="h-4 w-4 text-brand-400" />
                      Google Gmail Account
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
                      <span className="text-zinc-500">Connected As:</span>
                      <span className="font-mono text-zinc-200">{status?.account_email || "Not linked"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Security:</span>
                      <span className="text-emerald-400 font-medium">AES-128 Encrypted at rest</span>
                    </div>
                  </div>

                  {status?.is_connected && (!status?.has_sufficient_scopes || status?.status_label === "insufficient_scopes") && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-amber-200 text-[11px] leading-relaxed">
                      Missing required scopes: <code className="font-mono text-amber-300">gmail.readonly</code> & <code className="font-mono text-amber-300">gmail.modify</code>. Click Reconnect below and make sure all permissions are granted on Google&apos;s consent screen.
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
                    <button
                      onClick={handleConnect}
                      disabled={connecting}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 px-3 py-2 text-xs font-semibold text-white transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${connecting ? "animate-spin" : ""}`} />
                      <span>{status?.is_connected ? "Reconnect Account" : "Connect Gmail Account"}</span>
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

                {/* Scopes Transparency Card */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-850 p-4 space-y-3">
                  <div className="flex items-center gap-2 text-zinc-200 font-semibold">
                    <Shield className="h-4 w-4 text-brand-400" />
                    <span>Requested Scopes & Permissions</span>
                  </div>
                  <ul className="space-y-2 text-[11px] text-zinc-300">
                    <li className="flex items-start gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <code className="text-zinc-200 font-mono">gmail.readonly</code>: Used solely to list and read emails for inbox view and task extraction.
                      </div>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <code className="text-zinc-200 font-mono">gmail.modify</code>: Used to mark messages as read/unread or star important threads.
                      </div>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <code className="text-zinc-200 font-mono">gmail.compose</code>: Used to prepare draft responses directly in your mailbox.
                      </div>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <code className="text-zinc-200 font-mono">gmail.send</code>: Used only after explicit human confirmation to transmit scheduled replies.
                      </div>
                    </li>
                  </ul>
                </div>

                {/* Two-Phase Approval Disclosure */}
                <div className="rounded-lg border border-zinc-800/60 bg-zinc-900/40 p-3.5 text-[11px] text-zinc-400 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-zinc-300 font-semibold">
                    <Shield className="h-3.5 w-3.5 text-amber-400" />
                    <span>Consequential Write Safeguards</span>
                  </div>
                  <p className="leading-relaxed">
                    Mentor AI strictly enforces a two-phase human-in-the-loop approval policy for emails. AI will never send an email automatically. All email transmissions are staged as pending approval records under <Link href="/actions" className="text-brand-400 underline">Approvals & History</Link> where you must explicitly review and confirm them.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
