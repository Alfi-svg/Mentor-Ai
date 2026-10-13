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
// API Client Domain Methods
// -----------------------------------------------------------------------------

export const apiClient = {
  // --- Auth ---
  async signup(email: string, password: string): Promise<AuthResponse> {
    const data = await request<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(data.access_token);
    return data;
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const data = await request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(data.access_token);
    return data;
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
    limit?: number;
    offset?: number;
  }): Promise<Task[]> {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString() ? `?${q.toString()}` : "";
    const res = await request<Task[] | { items?: Task[]; total?: number }>(`/tasks${qs}`, { method: "GET" });
    if (Array.isArray(res)) return res;
    if (res && Array.isArray((res as { items?: Task[] }).items)) {
      return (res as { items: Task[] }).items;
    }
    return [];
  },

  async getTask(id: string): Promise<Task> {
    return request<Task>(`/tasks/${id}`, { method: "GET" });
  },

  async createTask(payload: TaskCreatePayload): Promise<Task> {
    return request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateTask(id: string, payload: TaskUpdatePayload): Promise<Task> {
    return request<Task>(`/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async deleteTask(id: string): Promise<void> {
    await request<void>(`/tasks/${id}`, { method: "DELETE" });
  },

  async completeTask(id: string): Promise<Task> {
    return request<Task>(`/tasks/${id}/complete`, { method: "POST" });
  },

  async reopenTask(id: string): Promise<Task> {
    return request<Task>(`/tasks/${id}/reopen`, { method: "POST" });
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
    return request<PlanConfirmResponse>("/planner/confirm", {
      method: "POST",
      body: JSON.stringify(payload),
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
};
