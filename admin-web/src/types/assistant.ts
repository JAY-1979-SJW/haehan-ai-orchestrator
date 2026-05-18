/** 비서앱 MVP 상태 모델 — APP_UI_SHELL_SKELETON_01 + APP_UI_READONLY_BACKEND_STATUS_CARDS_01 */

export type TaskStatus =
  | "READ_ONLY"
  | "DRY_RUN"
  | "BLOCKED"
  | "APPROVAL_DISPLAY_ONLY"
  | "FUTURE"
  | "ERROR"
  | "PENDING";

export type ActionRisk = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ProviderStatus = "CURRENT" | "PLANNED" | "HOLD" | "DISABLED";

export type GateState = "DISPLAY_ONLY" | "DISABLED" | "HIDDEN" | "DRY_RUN_ONLY";

export type BackendHealth = "OK" | "WARN" | "BLOCKED" | "UNKNOWN" | "DEGRADED" | "MOCK";

export type StoragePersistence = "PERSISTENT" | "EPHEMERAL" | "DISPOSABLE" | "UNKNOWN";

export type DeploymentState =
  | "SYNCED"
  | "BUILD_REQUIRED"
  | "DEPLOYED"
  | "RESTART_REQUIRED"
  | "BLOCKED";

export type ApiSource = "api" | "mock" | "static" | "mock_fallback";

export type ErrorKind = "network" | "schema" | "timeout" | "unknown" | null;

/** API 연결 상태 확장 필드 — APP_UI_READONLY_BACKEND_STATUS_CARDS_01 */
export interface ApiConnectionMeta {
  source: ApiSource;
  last_checked: string | null;
  error_kind: ErrorKind;
  is_read_only: true;
  mutation_allowed: false;
}

export interface AssistantTask {
  id: string;
  title: string;
  status: TaskStatus;
  risk: ActionRisk;
  provider: string;
  action_type: string;
  dry_run: boolean | null;
  approval_token_exists: boolean;
  created_at: string;
  updated_at: string;
  /** APP_TASK_QUEUE_READONLY_LIST_POLISH_01 확장 필드 */
  allowed?: boolean;
  requires_approval?: boolean;
  blocked_reasons?: string[];
  summary?: string;
  approval_token_id?: null | "redacted";
}

export interface ApprovalGate {
  gate_id: string;
  risk_level: ActionRisk;
  user_approval_required: boolean;
  auto_execute_allowed: false;
  evidence_required: boolean;
  state: GateState;
  current_behavior: string;
}

export interface ExternalProvider {
  id: string;
  label: string;
  risk: ActionRisk;
  status: ProviderStatus;
  user_present_required: boolean;
  desktop_required: boolean;
  cookie_storage_forbidden: boolean;
  approval_gate_required: boolean;
  certificate_required?: boolean;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  source: "storage" | "app-logs";
  level: "INFO" | "WARN" | "ERROR";
  message: string;
  redacted: true;
}

export interface StorageMount {
  label: string;
  path: string;
  host_path?: string;
  persistence: StoragePersistence;
  description: string;
}

export interface BackendStatus {
  head: string;
  origin_head: string;
  health: BackendHealth;
  container_status: string;
  dry_run_gate_enabled: boolean;
  phase1_closeout: string;
  /** API 연결 메타 — APP_UI_READONLY_BACKEND_STATUS_CARDS_01 */
  api_meta?: ApiConnectionMeta;
}

export interface DeploymentStatus {
  server_head: string;
  origin_head: string;
  state: DeploymentState;
  build_required: boolean;
  sop_steps: string[];
  /** server_apply_allowed 항상 false */
  server_apply_allowed?: false;
}
