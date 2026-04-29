export type AgentStatus = "idle" | "busy" | "stale" | "offline" | (string & {});

export type TaskStatus =
  | "queued"
  | "waiting_approval"
  | "delivered"
  | "running"
  | "completed"
  | "failed"
  | "rejected"
  | "cancel_requested"
  | "cancelled";

export type RiskLevel = "low" | "medium" | "high";

export interface LocalAgent {
  agent_id: string;
  host: string;
  os_name: string;
  version: string;
  registered_at: string;
  requested_by: string;
  agent_status: AgentStatus;
  connected_at: string | null;
  last_seen_at: string | null;
  disconnected_at: string | null;
  active_task_count: number;
  current_task_id: string | null;
}

export interface LocalAgentTask {
  task_id: string;
  agent_id: string;
  action: string;
  risk_level: RiskLevel;
  status: TaskStatus;
  requested_by: string;
  created_at: string;
  updated_at: string;
  delivered_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  failure_reason: string | null;
  timed_out_at: string | null;
  error_summary: string | null;
  result_summary: string | null;
  cancel_reason: string | null;
  cancel_requested_at: string | null;
  cancel_requested_by: string | null;
  cancelled_at: string | null;
}

export interface LocalAgentsResponse {
  agents: LocalAgent[];
}

export interface LocalAgentTasksResponse {
  agent_id: string;
  total: number;
  tasks: LocalAgentTask[];
}

export interface CancelTaskRequest {
  reason: string;
}

export interface CancelTaskResponse {
  task: LocalAgentTask;
  cancel_action: "cancelled" | "cancel_requested" | (string & {});
}

export interface ApiErrorResponse {
  detail: string | Record<string, unknown>;
}

export interface CaptureScreenshotRequest {
  dry_run: boolean;
  reason?: string;
  note?: string;
}

export interface CaptureScreenshotResponse {
  task_id: string;
  agent_id: string;
  action: "capture_screenshot" | string;
  status: "waiting_approval" | string;
  dry_run: boolean;
  approval_required: boolean;
}

/** Stage 13B-3A: controlled browser observe 결과 구조화 요약 (sanitized). */
export interface ObserveSummary {
  target_kind?: string | null;
  url_category?: string | null;
  /** query/fragment 제거된 안전 URL — about:blank 또는 loopback 만 허용, 외부 URL은 null */
  final_url_sanitized?: string | null;
  title?: string | null;
  title_len?: number | null;
  status_category?: string | null;
  pages_observed_count?: number | null;
  error_category?: string | null;
  blocked_reason?: string | null;
  login_required_hint?: boolean | null;
  modal_candidates_count?: number | null;
  html_truncated?: boolean | null;
  page_structure_counts?: {
    headings?: number;
    links?: number;
    buttons?: number;
    inputs?: number;
    forms?: number;
    tables?: number;
  } | null;
  observed_at?: string | null;
}

/** Stage 13C-2: audit summary (PC local audit safe 요약, raw audit 원문 금지). */
export interface AuditSummary {
  // STORE_AND_DISPLAY
  audit_event_count?: number | null;
  audit_window_started_at?: string | null;
  audit_window_ended_at?: string | null;
  audit_event_categories?: string[] | null;
  blocked_event_count?: number | null;
  allowed_event_count?: number | null;
  denied_event_count?: number | null;
  error_event_count?: number | null;
  last_event_category?: string | null;
  last_event_status?: string | null;
  policy_decision_counts?: {
    [key: string]: number;
  } | null;
  target_kind_counts?: {
    [key: string]: number;
  } | null;
  action_kind_counts?: {
    [key: string]: number;
  } | null;
  // STORE_ONLY (DO NOT DISPLAY)
  audit_schema_version?: number | null;
  local_audit_source?: string | null;
  agent_reported_event_count?: number | null;
  audit_summary_generated_at?: string | null;
  audit_summary_hash?: string | null;
  dropped_event_count?: number | null;
  redacted_field_count?: number | null;
}

/** GET /local-agents/{agent_id}/tasks/{task_id} — to_safe() 응답 (token_id 포함) */
export interface LocalAgentTaskDetail extends LocalAgentTask {
  token_id: string;
  approved_at: string | null;
  approved_by: string | null;
  rejected_at: string | null;
  reject_reason: string | null;
  observe_summary?: ObserveSummary | null;
  audit_summary?: AuditSummary | null;
}

export interface ApprovalRequest {
  token_id: string;
  reason?: string;
}

export interface ApprovalResponse extends LocalAgentTask {
  token_id: string;
  approved_at: string | null;
  approved_by: string | null;
  rejected_at: string | null;
  reject_reason: string | null;
}
