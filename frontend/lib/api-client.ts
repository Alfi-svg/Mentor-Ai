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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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

  async getCalendarEvents(startTime?: string, endTime?: string): Promise<CalendarEvent[]> {
    const q = new URLSearchParams();
    if (startTime) q.set("start_time", startTime);
    if (endTime) q.set("end_time", endTime);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return request<CalendarEvent[]>(`/calendar/events${qs}`, { method: "GET" });
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
};
