/**
 * Centralized, typed API Client for Mentor AI.
 */

import {
  ActionConfirmResponse,
  ActionRecord,
  ActionVerifyResponse,
  ApiErrorEnvelope,
  AuthResponse,
  CalendarEvent,
  CalendarStatus,
  CalendarSyncResult,
  ConflictCheckResult,
  NotificationItem,
  NotificationSettings,
  PlanConfirmPayload,
  PlanConfirmResponse,
  PlanProposalResponse,
  SavedSchedule,
  ScheduleProposal,
  Task,
  TaskCreatePayload,
  TaskPriority,
  TaskStatus,
  TaskUpdatePayload,
  User,
  UserPreferences,
  ValidationErrorItem,
} from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

export class ApiClientError extends Error {
  public statusCode: number;
  public errorCode: string;
  public validationErrors?: ValidationErrorItem[];
  public traceId?: string;

  constructor(envelope: ApiErrorEnvelope) {
    super(envelope.detail || "An unexpected API error occurred.");
    this.name = "ApiClientError";
    this.statusCode = envelope.status_code;
    this.errorCode = envelope.error_code || "UNKNOWN_ERROR";
    this.validationErrors = envelope.validation_errors;
    this.traceId = envelope.trace_id;
  }
}

// Token storage helper (uses sessionStorage to prevent cross-tab persistence of raw tokens,
// and strictly keeps tokens client-side without storing passwords or secrets)
const TOKEN_KEY = "mentor_ai_access_token";

let onUnauthorizedCallback: (() => void) | null = null;

export function setOnUnauthorizedCallback(cb: () => void): void {
  onUnauthorizedCallback = cb;
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  // Inject Bearer token if available
  const token = getStoredToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Default Content-Type to JSON if sending body
  if (options.body && typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers,
    });
  } catch (networkError) {
    throw new ApiClientError({
      status_code: 0,
      error_code: "NETWORK_ERROR",
      detail:
        "Unable to communicate with the Mentor AI backend. Check if the server is running.",
    });
  }

  // Handle Unauthorized (401)
  if (res.status === 401) {
    setStoredToken(null);
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback();
    }
  }

  if (!res.ok) {
    let errorEnvelope: ApiErrorEnvelope;
    try {
      const errJson = await res.json();
      errorEnvelope = {
        status_code: res.status,
        error_code: errJson.error_code || "API_ERROR",
        detail:
          errJson.detail ||
          (typeof errJson === "string"
            ? errJson
            : "An error occurred while processing your request."),
        validation_errors: errJson.validation_errors,
        trace_id: errJson.trace_id,
        timestamp: errJson.timestamp,
      };
    } catch {
      errorEnvelope = {
        status_code: res.status,
        error_code: "HTTP_ERROR",
        detail: `Server responded with HTTP status ${res.status} (${res.statusText})`,
      };
    }
    throw new ApiClientError(errorEnvelope);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

// -----------------------------------------------------------------------------
// Data Normalization Helpers
// -----------------------------------------------------------------------------

function normalizeTask(raw: any): Task {
  if (!raw) return raw;
  const duration =
    typeof raw.duration_minutes === "number"
      ? raw.duration_minutes
      : typeof raw.estimated_duration_minutes === "number"
      ? raw.estimated_duration_minutes
      : 45;

  return {
    ...raw,
    duration_minutes: duration,
    estimated_duration_minutes: duration,
    priority: raw.priority || "P3",
    status: raw.status || "pending",
  };
}

// -----------------------------------------------------------------------------
// API Client Domain Methods
// -----------------------------------------------------------------------------

export const apiClient = {
  // --- Auth ---
  async signup(email: string, password: string): Promise<AuthResponse> {
    const data = await request<{
      access_token: string;
      token_type?: string;
      expires_in?: number;
      refresh_token?: string | null;
      user_id?: string;
      email?: string;
      user?: User;
    }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(data.access_token);
    const user: User = data.user || {
      id: data.user_id || "",
      email: data.email || email,
    };
    return {
      access_token: data.access_token,
      token_type: data.token_type || "bearer",
      user,
    };
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const data = await request<{
      access_token: string;
      token_type?: string;
      expires_in?: number;
      refresh_token?: string | null;
      user_id?: string;
      email?: string;
      user?: User;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(data.access_token);
    const user: User = data.user || {
      id: data.user_id || "",
      email: data.email || email,
    };
    return {
      access_token: data.access_token,
      token_type: data.token_type || "bearer",
      user,
    };
  },

  async getMe(): Promise<User> {
    return request<User>("/auth/me", { method: "GET" });
  },

  logout(): void {
    setStoredToken(null);
  },

  async getTasks(params?: {
    status?: TaskStatus;
    priority?: TaskPriority;
    is_archived?: boolean;
    is_overdue?: boolean;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<Task[]> {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.is_archived !== undefined) q.set("is_archived", String(params.is_archived));
    if (params?.is_overdue !== undefined) q.set("is_overdue", String(params.is_overdue));
    if (params?.search) q.set("search", params.search);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString() ? `?${q.toString()}` : "";
    const res = await request<Task[] | { items?: Task[]; total?: number }>(`/tasks${qs}`, { method: "GET" });
    if (Array.isArray(res)) return res.map(normalizeTask);
    if (res && Array.isArray((res as { items?: Task[] }).items)) {
      return (res as { items: Task[] }).items.map(normalizeTask);
    }
    return [];
  },

  async getTask(id: string): Promise<Task> {
    const res = await request<Task>(`/tasks/${id}`, { method: "GET" });
    return normalizeTask(res);
  },

  async createTask(payload: TaskCreatePayload): Promise<Task> {
    const duration = payload.duration_minutes ?? payload.estimated_duration_minutes ?? 45;
    const backendPayload = {
      ...payload,
      duration_minutes: duration,
    };
    const res = await request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(backendPayload),
    });
    return normalizeTask(res);
  },

  async updateTask(id: string, payload: TaskUpdatePayload): Promise<Task> {
    const duration = payload.duration_minutes ?? payload.estimated_duration_minutes;
    const backendPayload = {
      ...payload,
      ...(duration !== undefined ? { duration_minutes: duration } : {}),
    };
    const res = await request<Task>(`/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(backendPayload),
    });
    return normalizeTask(res);
  },

  async deleteTask(id: string): Promise<void> {
    await request<void>(`/tasks/${id}`, { method: "DELETE" });
  },

  async completeTask(id: string): Promise<Task> {
    const res = await request<Task>(`/tasks/${id}/complete`, { method: "POST" });
    return normalizeTask(res);
  },

  async reopenTask(id: string): Promise<Task> {
    const res = await request<Task>(`/tasks/${id}/reopen`, { method: "POST" });
    return normalizeTask(res);
  },

  async archiveTask(id: string): Promise<Task> {
    const res = await request<Task>(`/tasks/${id}/archive`, { method: "POST" });
    return normalizeTask(res);
  },

  async unarchiveTask(id: string): Promise<Task> {
    const res = await request<Task>(`/tasks/${id}/unarchive`, { method: "POST" });
    return normalizeTask(res);
  },

  // --- Preferences ---
  async getPreferences(): Promise<UserPreferences> {
    return request<UserPreferences>("/auth/preferences", { method: "GET" });
  },

  async updatePreferences(payload: UserPreferences): Promise<UserPreferences> {
    return request<UserPreferences>("/auth/preferences", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  // --- Planner & Natural Language ---
  async generateDraft(
    message: string,
    clientTimezone: string = "UTC",
    targetDate?: string
  ): Promise<PlanProposalResponse> {
    return request<PlanProposalResponse>("/planner/draft", {
      method: "POST",
      body: JSON.stringify({
        message,
        client_timezone: clientTimezone,
        target_date: targetDate || undefined,
      }),
    });
  },

  async confirmPlan(payload: PlanConfirmPayload): Promise<PlanConfirmResponse> {
    const normalizedTasks = (payload.tasks || []).map((t) => ({
      ...t,
      duration_minutes: t.duration_minutes || t.estimated_duration_minutes || 60,
      energy_level: t.energy_level || "medium",
      deadline: t.deadline && typeof t.deadline === "string" && t.deadline.trim() !== "" ? t.deadline : null,
    }));
    return request<PlanConfirmResponse>("/planner/confirm", {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        tasks: normalizedTasks,
      }),
    });
  },

  // --- Schedule ---
  async generateSchedule(payload: {
    target_date: string;
    task_ids?: string[];
    enforce_buffer?: boolean;
    override_timezone?: string;
  }): Promise<ScheduleProposal> {
    return request<ScheduleProposal>("/schedule/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async approveSchedule(
    proposal: ScheduleProposal
  ): Promise<{ schedule_id: string; target_date: string; status: string }> {
    return request<{ schedule_id: string; target_date: string; status: string }>(
      "/schedule/approve",
      {
        method: "POST",
        body: JSON.stringify(proposal),
      }
    );
  },

  async getScheduleForDate(targetDate: string): Promise<SavedSchedule | null> {
    try {
      return await request<SavedSchedule>(`/schedule/${targetDate}`, {
        method: "GET",
      });
    } catch (err) {
      if (err instanceof ApiClientError && err.statusCode === 404) {
        return null;
      }
      throw err;
    }
  },

  // --- Calendar ---
  async getCalendarStatus(): Promise<CalendarStatus> {
    return request<CalendarStatus>("/calendar/status", { method: "GET" });
  },

  async getCalendarConnectUrl(): Promise<{ authorization_url: string; provider: string; scopes: string[] }> {
    return request<{ authorization_url: string; provider: string; scopes: string[] }>(
      "/calendar/connect",
      { method: "GET" }
    );
  },

  async handleCalendarCallback(
    code: string,
    state: string
  ): Promise<{ status: string; provider: string; account_email: string }> {
    return request<{ status: string; provider: string; account_email: string }>(
      `/calendar/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
      { method: "GET" }
    );
  },

  async disconnectCalendar(): Promise<{ status: string; provider: string; message: string }> {
    return request<{ status: string; provider: string; message: string }>(
      "/calendar/disconnect",
      { method: "POST" }
    );
  },

  async getCalendarEvents(
    startTimeOrParams?: string | { startTime?: string; endTime?: string; includeTasks?: boolean },
    endTime?: string
  ): Promise<CalendarEvent[]> {
    const q = new URLSearchParams();
    if (typeof startTimeOrParams === "string") {
      if (startTimeOrParams) q.set("start_time", startTimeOrParams);
      if (endTime) q.set("end_time", endTime);
    } else if (startTimeOrParams) {
      if (startTimeOrParams.startTime) q.set("start_time", startTimeOrParams.startTime);
      if (startTimeOrParams.endTime) q.set("end_time", startTimeOrParams.endTime);
      if (startTimeOrParams.includeTasks !== undefined) {
        q.set("include_tasks", String(startTimeOrParams.includeTasks));
      }
    }
    const qs = q.toString() ? `?${q.toString()}` : "";
    return request<CalendarEvent[]>(`/calendar/events${qs}`, { method: "GET" });
  },

  async createCalendarEvent(payload: import("./types").CalendarEventCreatePayload): Promise<CalendarEvent> {
    return request<CalendarEvent>("/calendar/events", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateCalendarEvent(id: string, payload: import("./types").CalendarEventUpdatePayload): Promise<CalendarEvent> {
    return request<CalendarEvent>(`/calendar/events/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async deleteCalendarEvent(id: string): Promise<{ status: string; id: string }> {
    return request<{ status: string; id: string }>(`/calendar/events/${id}`, {
      method: "DELETE",
    });
  },

  async syncCalendarTasks(): Promise<import("./types").CalendarTaskSyncSummary> {
    return request<import("./types").CalendarTaskSyncSummary>("/calendar/sync/tasks", {
      method: "POST",
    });
  },

  async getCalendarTaskSyncStatus(): Promise<import("./types").CalendarTaskSyncSummary> {
    return request<import("./types").CalendarTaskSyncSummary>("/calendar/sync/tasks", {
      method: "GET",
    });
  },

  async syncCalendar(
    daysBack: number = 7,
    daysForward: number = 14
  ): Promise<CalendarSyncResult> {
    return request<CalendarSyncResult>(
      `/calendar/sync?days_back=${daysBack}&days_forward=${daysForward}`,
      { method: "POST" }
    );
  },

  async checkConflicts(targetDate: string): Promise<ConflictCheckResult> {
    return request<ConflictCheckResult>(
      `/calendar/conflicts?target_date=${encodeURIComponent(targetDate)}`,
      { method: "GET" }
    );
  },

  // --- Actions ---
  async getPendingActions(): Promise<ActionRecord[]> {
    const res = await request<ActionRecord[] | { items?: ActionRecord[] }>("/actions/pending", { method: "GET" });
    if (Array.isArray(res)) return res;
    if (res && Array.isArray((res as { items?: ActionRecord[] }).items)) {
      return (res as { items: ActionRecord[] }).items;
    }
    return [];
  },

  async getActionHistory(
    limit: number = 50,
    offset: number = 0
  ): Promise<ActionRecord[]> {
    return request<ActionRecord[]>(
      `/actions/history?limit=${limit}&offset=${offset}`,
      { method: "GET" }
    );
  },

  async confirmAction(
    id: string,
    confirmed: boolean,
    rejectionReason?: string
  ): Promise<ActionConfirmResponse> {
    return request<ActionConfirmResponse>(`/actions/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({
        confirmed,
        rejection_reason: rejectionReason,
      }),
    });
  },

  async verifyAction(id: string): Promise<ActionVerifyResponse> {
    return request<ActionVerifyResponse>(`/actions/${id}/verify`, {
      method: "GET",
    });
  },

  // --- Notifications ---
  async getNotifications(unreadOnly = false): Promise<NotificationItem[]> {
    return request<NotificationItem[]>(`/notifications?unread_only=${unreadOnly}`);
  },

  async getUnreadNotificationCount(): Promise<{ unread_count: number }> {
    return request<{ unread_count: number }>("/notifications/unread-count");
  },

  async markNotificationRead(id: string): Promise<NotificationItem> {
    return request<NotificationItem>(`/notifications/${id}/read`, {
      method: "POST",
    });
  },

  async markAllNotificationsRead(): Promise<{ marked_as_read: number }> {
    return request<{ marked_as_read: number }>("/notifications/read-all", {
      method: "POST",
    });
  },

  async evaluateNotifications(): Promise<{
    evaluated_tasks_count: number;
    new_notifications_count: number;
    notifications: NotificationItem[];
  }> {
    return request("/notifications/evaluate", {
      method: "POST",
    });
  },

  async getNotificationPreferences(): Promise<NotificationSettings> {
    return request<NotificationSettings>("/notifications/preferences");
  },

  async updateNotificationPreferences(
    prefs: Partial<NotificationSettings>
  ): Promise<NotificationSettings> {
    return request<NotificationSettings>("/notifications/preferences", {
      method: "PUT",
      body: JSON.stringify(prefs),
    });
  },

  async getGmailStatus(): Promise<import("./types").GmailStatus> {
    return request<import("./types").GmailStatus>("/gmail/status");
  },

  async verifyGmail(): Promise<import("./types").GmailVerifyResponse> {
    return request<import("./types").GmailVerifyResponse>("/gmail/verify");
  },

  async getGmailConnectUrl(): Promise<{ authorization_url: string; state: string; provider: string }> {
    return request<{ authorization_url: string; state: string; provider: string }>("/gmail/connect");
  },

  async disconnectGmail(): Promise<{ status: string; message: string }> {
    return request<{ status: string; message: string }>("/gmail/disconnect", {
      method: "POST",
    });
  },

  async listGmailMessages(
    optionsOrQuery?: string | { query?: string; folder?: string; pageToken?: string; limit?: number },
    fallbackLimit: number = 15
  ): Promise<import("./types").GmailMessageSummary[]> {
    const q = new URLSearchParams();
    if (typeof optionsOrQuery === "string") {
      if (optionsOrQuery) q.set("query", optionsOrQuery);
      q.set("limit", String(fallbackLimit));
    } else if (optionsOrQuery) {
      if (optionsOrQuery.query) q.set("query", optionsOrQuery.query);
      if (optionsOrQuery.folder) q.set("folder", optionsOrQuery.folder);
      if (optionsOrQuery.pageToken) q.set("page_token", optionsOrQuery.pageToken);
      q.set("limit", String(optionsOrQuery.limit ?? fallbackLimit));
    } else {
      q.set("limit", String(fallbackLimit));
    }
    return request<import("./types").GmailMessageSummary[]>(`/gmail/messages?${q.toString()}`);
  },

  async modifyGmailMessage(
    id: string,
    payload: { add_label_ids?: string[]; remove_label_ids?: string[] }
  ): Promise<{ id: string; labels: string[]; is_unread: boolean; is_starred: boolean }> {
    return request<{ id: string; labels: string[]; is_unread: boolean; is_starred: boolean }>(
      `/gmail/messages/${id}/modify`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
  },

  async getGmailMessage(id: string): Promise<import("./types").GmailMessageDetail> {
    return request<import("./types").GmailMessageDetail>(`/gmail/messages/${id}`);
  },

  async summarizeGmailMessage(id: string): Promise<import("./types").GmailEmailSummaryResult> {
    return request<import("./types").GmailEmailSummaryResult>(`/gmail/messages/${id}/summary`);
  },

  async extractTasksFromEmails(
    messageIds: string[]
  ): Promise<import("./types").EmailTaskCandidate[]> {
    return request<import("./types").EmailTaskCandidate[]>("/gmail/extract-tasks", {
      method: "POST",
      body: JSON.stringify(messageIds),
    });
  },

  async createGmailDraft(
    draft: import("./types").GmailDraftCreate
  ): Promise<import("./types").GmailDraftResponse> {
    return request<import("./types").GmailDraftResponse>("/gmail/drafts", {
      method: "POST",
      body: JSON.stringify(draft),
    });
  },

  async stageSendEmail(
    payload: import("./types").GmailSendPayload
  ): Promise<ActionRecord> {
    return request<ActionRecord>("/gmail/send-staged", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // --- Unified LifeOps Workflow ---
  async executeLifeOpsWorkflow(req: {
    prompt: string;
    target_date?: string;
    client_timezone?: string;
    auto_extract_emails?: boolean;
    email_query?: string;
    confirmed_tasks?: any[];
    stage_calendar_action?: boolean;
    stage_email_action?: boolean;
    stage_notifications?: boolean;
  }): Promise<import("./types").LifeOpsWorkflowResponse> {
    return request<import("./types").LifeOpsWorkflowResponse>("/lifeops/workflow", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
};
