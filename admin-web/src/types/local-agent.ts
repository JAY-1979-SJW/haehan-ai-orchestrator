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
