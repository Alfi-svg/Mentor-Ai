/**
 * Typed domain models and API contracts for Mentor AI.
 */

export type TaskPriority = "P1" | "P2" | "P3" | "P4";
export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled" | "archived";

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
  tags?: string[];
  constraints?: Record<string, any>;
  status?: TaskStatus;
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string | null;
  estimated_duration_minutes?: number;
  duration_minutes?: number;
  priority?: TaskPriority;
  deadline?: string | null;
  energy_level?: "low" | "medium" | "high" | null;
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
  account_email: string | null;
  last_synced_at: string | null;
  scopes: string[];
  message: string;
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
}

export interface CalendarSyncResult {
  synced_count: number;
  start_time: string;
  end_time: string;
  provider: string;
  last_synced_at: string;
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
  has_attachments: boolean;
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
  sanitized: boolean;
  has_attachments: boolean;
  labels: string[];
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

