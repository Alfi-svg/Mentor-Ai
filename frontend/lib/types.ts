/**
 * Typed domain models and API contracts for Mentor AI.
 */

export type TaskPriority = "P1" | "P2" | "P3" | "P4";
export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled" | "archived";
export type CalendarSyncStatus =
  | "unscheduled"
  | "local_only"
  | "unsynced"
  | "pending"
  | "syncing"
  | "synced"
  | "failed"
  | "reauthorization_required";

export interface TaskConstraints {
  can_split?: boolean;
  min_split_duration_minutes?: number;
  preferred_time_of_day?: "morning" | "afternoon" | "evening";
}

export interface Task {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  estimated_duration_minutes: number;
  duration_minutes?: number;
  priority: TaskPriority;
  deadline: string | null;
  energy_level: "low" | "medium" | "high" | null;
  availability_constraints: TaskConstraints | null;
  status: TaskStatus;
  is_completed: boolean;
  completed_at: string | null;
  tags?: string[];
  constraints?: Record<string, any>;
  is_archived?: boolean;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  google_calendar_event_id?: string | null;
  calendar_sync_status?: CalendarSyncStatus | string | null;
  calendar_sync_error?: string | null;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreatePayload {
  title: string;
  description?: string | null;
  estimated_duration_minutes?: number;
  duration_minutes?: number;
  priority?: TaskPriority;
  deadline?: string | null;
  energy_level?: "low" | "medium" | "high" | null;
  availability_constraints?: TaskConstraints | null;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  tags?: string[];
  constraints?: Record<string, any>;
  status?: TaskStatus;
  scheduling_preference?: "auto" | "manual" | "unscheduled";
}

export interface TaskAutoScheduleResult {
  task: Task;
  scheduled: boolean;
  message: string;
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string | null;
  estimated_duration_minutes?: number;
  duration_minutes?: number;
  priority?: TaskPriority;
  deadline?: string | null;
  energy_level?: "low" | "medium" | "high" | null;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  status?: TaskStatus;
  tags?: string[];
  constraints?: Record<string, any>;
  is_archived?: boolean;
}

export interface UserPreferences {
  work_start_time?: string;
  work_end_time?: string;
  timezone?: string;
  buffer_minutes?: number;
  default_task_duration?: number;
  max_focus_hours_per_day?: number;
  available_days?: number[];
  auto_schedule_breaks?: boolean;
  allow_weekend_scheduling?: boolean;
  lunch_break_start?: string;
  lunch_break_duration_minutes?: number;
  calendar_auto_sync?: boolean;
  notification_settings?: NotificationSettings;
}

export interface User {
  id: string;
  email: string;
  preferences?: UserPreferences;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// -----------------------------------------------------------------------------
// Calendar Models
// -----------------------------------------------------------------------------

export interface CalendarStatus {
  is_connected: boolean;
  provider: string;
  configured?: boolean;
  status_label?: string;
  account_email: string | null;
  last_synced_at: string | null;
  scopes: string[];
  message?: string | null;
  has_sufficient_scopes?: boolean;
  missing_scopes?: string[];
}

export interface CalendarEvent {
  id: string;
  external_id: string | null;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string;
  is_all_day: boolean;
  is_fixed: boolean;
  source: string;
  location: string | null;
  task_id?: string | null;
  priority?: string | null;
  task_status?: string | null;
  calendar_sync_status?: CalendarSyncStatus | string | null;
}

export interface CalendarSyncResult {
  synced_count: number;
  start_time: string;
  end_time: string;
  provider: string;
  last_synced_at: string;
}

export interface CalendarEventCreatePayload {
  title: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  is_all_day?: boolean;
  location?: string | null;
}

export interface CalendarEventUpdatePayload {
  title?: string;
  description?: string | null;
  start_time?: string;
  end_time?: string;
  is_all_day?: boolean;
  location?: string | null;
  status?: string;
}

export interface CalendarTaskSyncSummary {
  synced: number;
  failed: number;
  errors: Array<{ task_id: string; title: string; error: string }>;
}

export interface FreeSlot {
  start_time: string;
  end_time: string;
  duration_minutes: number;
}

export interface ConflictingEvent {
  title: string;
  start_time: string;
  end_time: string;
  is_all_day: boolean;
}

export interface ConflictCheckResult {
  target_date: string;
  has_conflicts: boolean;
  total_busy_minutes: number;
  conflicting_events: ConflictingEvent[];
  free_slots: FreeSlot[];
}

// -----------------------------------------------------------------------------
// Scheduler Models
// -----------------------------------------------------------------------------

export interface ScheduleBlockProposal {
  task_id: string | null;
  calendar_event_id: string | null;
  title: string;
  start_time: string;
  end_time: string;
  block_type: "fixed_commitment" | "task_allocation" | "break" | "buffer";
  is_completed: boolean;
}

export interface UnscheduledTask {
  task_id: string;
  title?: string;
  task_title?: string;
  estimated_duration_minutes?: number;
  required_minutes?: number;
  priority?: TaskPriority | string;
  reason: string;
}

export interface ScheduleConflict {
  block_a_title: string;
  block_b_title: string;
  overlap_start: string;
  overlap_end: string;
  conflict_type: string;
}

export interface ScheduleSummary {
  total_working_minutes: number;
  total_scheduled_task_minutes: number;
  total_fixed_minutes: number;
  total_free_minutes: number;
  utilization_percentage: number;
}

export interface ScheduleProposal {
  target_date: string;
  timezone: string;
  working_hours: {
    start_time: string;
    end_time: string;
  };
  scheduled_blocks: ScheduleBlockProposal[];
  unscheduled_tasks: UnscheduledTask[];
  conflicts: ScheduleConflict[];
  summary?: ScheduleSummary;
  scheduling_explanation?: string;
  status: "feasible" | "conflict_detected" | "partial";
  validation_passed: boolean;
}

export interface SavedScheduleBlock {
  id: string;
  task_id: string | null;
  calendar_event_id: string | null;
  title: string;
  start_time: string;
  end_time: string;
  block_type: string;
  is_completed: boolean;
}

export interface SavedSchedule {
  schedule_id: string;
  target_date: string;
  status: string;
  metadata?: Record<string, unknown>;
  blocks: SavedScheduleBlock[];
}

// -----------------------------------------------------------------------------
// Planner / NLU Models
// -----------------------------------------------------------------------------

export type PlanIntent =
  | "plan_day"
  | "add_task"
  | "add_event"
  | "reschedule"
  | "clarification_needed"
  | "unsupported";

export interface DetectedFixedEvent {
  title: string;
  start_time: string;
  end_time: string;
  location?: string | null;
}

export interface DetectedTask {
  title: string;
  duration_minutes: number | null;
  priority: TaskPriority;
  deadline?: string | null;
  energy_level?: "low" | "medium" | "high" | null;
  depends_on?: string[];
}

export interface PlanProposalResponse {
  proposal_id: string;
  original_prompt: string;
  target_date: string;
  intent: PlanIntent;
  explanation: string;
  fixed_events: DetectedFixedEvent[];
  tasks: DetectedTask[];
  missing_information: string[];
  clarification_question: string | null;
  requires_confirmation: boolean;
  parser_used: "gemini" | "groq" | "deterministic_offline";
  fallback_applied: boolean;
  preview_schedule: ScheduleProposal | null;
}

export interface PlanConfirmPayload {
  proposal_id?: string | null;
  target_date: string;
  tasks: TaskCreatePayload[];
  fixed_events?: DetectedFixedEvent[];
  persist_tasks?: boolean;
  generate_schedule?: boolean;
}

export interface PlanConfirmResponse {
  target_date: string;
  created_tasks: Task[];
  created_events: DetectedFixedEvent[];
  schedule: ScheduleProposal | null;
  persisted_schedule_id: string | null;
  status: string;
}

// -----------------------------------------------------------------------------
// Action Approvals & History
// -----------------------------------------------------------------------------

export type ActionStatus =
  | "pending_approval"
  | "executing"
  | "completed"
  | "failed"
  | "rejected";

export interface ActionRecord {
  id: string;
  user_id: string;
  action_type: string;
  status: ActionStatus;
  payload: Record<string, unknown>;
  verification_result?: Record<string, unknown> | null;
  error_message?: string | null;
  idempotency_key?: string | null;
  created_at: string;
  confirmed_at?: string | null;
  completed_at?: string | null;
}

export interface ActionConfirmResponse {
  action_id: string;
  status: ActionStatus;
  verified: boolean;
  verification_details?: Record<string, unknown> | null;
}

export interface ActionVerifyResponse {
  action_id: string;
  status: string;
  verified: boolean;
  details?: Record<string, unknown> | null;
  error_message?: string | null;
}

// -----------------------------------------------------------------------------
// Error Envelopes
// -----------------------------------------------------------------------------

export interface ValidationErrorItem {
  field: string;
  issue: string;
  received?: unknown;
}

export interface ApiErrorEnvelope {
  status_code: number;
  error_code: string;
  detail: string;
  validation_errors?: ValidationErrorItem[];
  trace_id?: string;
  timestamp?: string;
}

export type NotificationType =
  | "due_soon"
  | "due_now"
  | "overdue"
  | "upcoming_task"
  | "schedule_conflict"
  | "calendar_revoked"
  | "calendar_stale"
  | "action_required"
  | "action_failed"
  | "task_completed";

export type NotificationChannel = "in_app" | "email" | "browser_push";
export type NotificationDeliveryStatus =
  | "pending"
  | "processing"
  | "delivered"
  | "failed"
  | "cancelled"
  | "permanently_failed";

export interface NotificationSettings {
  notify_upcoming_tasks: boolean;
  notify_deadlines: boolean;
  notify_overdue: boolean;
  notify_schedule_conflicts: boolean;
  notify_action_requests: boolean;
  notify_task_completed: boolean;
  reminder_lead_time_minutes: number;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  task_id: string | null;
  action_id?: string | null;
  notification_type: NotificationType;
  channel?: NotificationChannel;
  status?: NotificationDeliveryStatus;
  title: string;
  message: string;
  scheduled_for: string;
  delivered_at: string | null;
  read_at: string | null;
  is_read: boolean;
  attempt_count?: number;
  deduplication_key?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
  target_date?: string | null;
  target_time?: string | null;
  timezone?: string | null;
  trigger_datetime?: string | null;
}

// -----------------------------------------------------------------------------
// Gmail Models
// -----------------------------------------------------------------------------

export interface GmailStatus {
  provider: string;
  is_connected: boolean;
  configured: boolean;
  status_label: string;
  account_email: string | null;
  last_synced_at: string | null;
  scopes: string[];
  message?: string | null;
  has_sufficient_scopes?: boolean;
  missing_scopes?: string[];
}

export interface GmailMessageSummary {
  id: string;
  thread_id: string;
  sender: string;
  recipient?: string | null;
  subject: string;
  date?: string | null;
  snippet: string;
  is_unread: boolean;
  is_starred?: boolean;
  has_attachments: boolean;
  labels?: string[];
}

export interface GmailMessageDetail {
  id: string;
  thread_id: string;
  sender: string;
  recipient?: string | null;
  subject: string;
  date?: string | null;
  snippet: string;
  body_plain: string;
  body_html?: string | null;
  sanitized: boolean;
  has_attachments: boolean;
  attachments?: Array<{ filename: string; mime_type: string; size_bytes?: number }>;
  labels: string[];
  is_starred?: boolean;
}

export interface GmailEmailSummaryResult {
  message_id: string;
  subject: string;
  sender: string;
  verified_facts: string[];
  ai_interpretation: string;
  confidence_score: number;
}

export interface EmailTaskCandidate {
  title: string;
  description?: string | null;
  proposed_deadline?: string | null;
  is_deadline_proposed: boolean;
  is_deadline_ambiguous: boolean;
  ambiguity_reason?: string | null;
  estimated_duration_minutes: number;
  priority: TaskPriority;
  energy_level: "low" | "medium" | "high";
  source_message_id: string;
  source_subject: string;
  source_sender: string;
}

export interface GmailDraftCreate {
  to: string;
  subject: string;
  body: string;
  thread_id?: string | null;
}

export interface GmailDraftResponse {
  draft_id: string;
  message_id?: string | null;
  to: string;
  subject: string;
  created_at: string;
}

export interface GmailSendPayload {
  to: string;
  subject: string;
  body: string;
  thread_id?: string | null;
  source_reference?: string | null;
}

export interface GmailVerifyResponse {
  connected: boolean;
  status: string;
  verified: boolean;
  account_email: string | null;
  has_sufficient_scopes: boolean;
  missing_scopes: string[];
  granted_scopes: string[];
  can_read_messages: boolean;
  api_status: string;
  api_error: string | null;
  message: string | null;
}

// -----------------------------------------------------------------------------

// LifeOps Workflow Models
// -----------------------------------------------------------------------------

export interface LifeOpsWorkflowStep {
  step: string;
  status: "completed" | "requires_clarification" | "pending_review" | "skipped";
  detail: string;
}

export interface LifeOpsWorkflowResponse {
  intent_summary: string;
  target_date: string;
  gmail_status: GmailStatus;
  calendar_status: CalendarStatus;
  analyzed_emails: GmailMessageSummary[];
  extracted_candidates: EmailTaskCandidate[];
  has_ambiguous_deadlines: boolean;
  clarification_questions: string[];
  schedule_proposal?: any;
  staged_actions: ActionRecord[];
  notifications_created_count: number;
  workflow_steps: LifeOpsWorkflowStep[];
}

// -----------------------------------------------------------------------------
// Mentor AI Educational Copilot Models
// -----------------------------------------------------------------------------

export interface CopilotChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

export interface CopilotMessageRequest {
  message: string;
  input_mode?: "text" | "voice";
  client_timezone?: string;
  conversation_history?: CopilotChatMessage[];
  target_date?: string;
  voice_preset?: string;
}

export interface CopilotScheduleItem {
  id: string;
  title: string;
  item_type: "task" | "calendar_event";
  start_time: string;
  end_time: string;
  raw_start: string;
  raw_end: string;
  status: string;
  is_completed: boolean;
  is_overdue: boolean;
  priority?: TaskPriority | string | null;
  task_id?: string | null;
  event_id?: string | null;
  sync_status?: CalendarSyncStatus | string | null;
}

export interface CopilotScheduleSummary {
  target_date: string;
  timezone: string;
  total_items: number;

  scheduled_items: CopilotScheduleItem[];
  unscheduled_tasks: {
    id: string;
    title: string;
    duration_minutes?: number;
    priority?: string;
    deadline?: string;
  }[];
  deadlines: {
    id: string;
    title: string;
    deadline_time?: string;
    priority?: string;
    status?: string;
  }[];
  next_action?: string | null;
  next_action_time?: string | null;
  summary_text: string;
}

export interface EducationalResource {
  title: string;
  url: string;
  platform: string;
  topic: string;
  difficulty: "Beginner" | "Intermediate" | "Advanced" | "All Levels" | string;
  is_free: boolean;
  description: string;
  why_recommended: string;
}

export interface EmailDraftPreview {
  thread_id?: string | null;
  recipient_email: string;
  recipient_name?: string | null;
  subject: string;
  body: string;
  context_summary?: string | null;
  requires_confirmation: boolean;
  approval_id?: string | null;
  status: "draft_ready" | "ambiguous_recipient" | "not_found" | "sent" | "failed";
  clarification_question?: string | null;
  candidates?: { email: string; name: string }[];
}

export interface CopilotNavigationTarget {
  route: string;
  params: Record<string, string>;
  label: string;
}

export interface StudentAccountabilitySummary {
  missed_sessions_count: number;
  completed_today_count: number;
  total_tasks_count: number;
  streak_days: number;
  supportive_message: string;
  suggested_recovery_task?: {
    id: string;
    title: string;
    priority?: string;
    duration_minutes?: number;
  } | null;
}

export interface CopilotResponse {
  reply: string;
  spoken_reply?: string | null;
  speech_audio_base64?: string | null;
  speech_audio_format?: string | null;
  input_mode?: "text" | "voice";
  intent: string;
  tools_invoked?: string[];
  tool_results?: Record<string, any>[];
  schedule_summary?: CopilotScheduleSummary | null;
  resources?: EducationalResource[] | null;
  email_draft?: EmailDraftPreview | null;
  approval_id?: string | null;
  navigation?: CopilotNavigationTarget | null;
  accountability?: StudentAccountabilitySummary | null;
  code_line_count?: number | null;
  verification_status: "verified" | "clarification_needed" | "unsupported" | "error" | "unconfigured";
}

export interface CopilotActionConfirmRequest {
  action_type: "send_email" | "reschedule_task";
  approval_id?: string | null;
  email_payload?: {
    recipient_email: string;
    subject: string;
    body: string;
    thread_id?: string;
    approval_id?: string;
  };
  task_payload?: Record<string, any>;
}

export interface CopilotActionConfirmResponse {
  success: boolean;
  action_type: string;
  result_message: string;
  details?: Record<string, any> | null;
}

export interface CopilotVoiceOption {
  id: string;
  name: string;
  perceived_sound: "masculine" | "feminine";
  description: string;
  sample_text: string;
}

export interface CopilotPreferences {
  voice_preset: string;
  voice_gender: "masculine" | "feminine";
  auto_play_speech: boolean;
  stt_engine: string;
}

export interface CopilotPreferencesUpdate {
  voice_preset?: string;
  voice_gender?: "masculine" | "feminine";
  auto_play_speech?: boolean;
  stt_engine?: string;
}

export interface CopilotTranscribeResponse {
  transcript: string;
  language?: string | null;
}


