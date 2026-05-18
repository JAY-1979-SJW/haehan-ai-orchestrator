/**
 * 비서앱 MVP mock data — APP_UI_SHELL_SKELETON_01
 * 주의: secret / token 원문 / cookie raw 절대 포함 금지
 */
import type {
  AssistantTask, ApprovalGate, ExternalProvider,
  AuditLogEntry, StorageMount, BackendStatus, DeploymentStatus,
} from "@/types/assistant";

export const backendStatusMock: BackendStatus = {
  head: "6c10118",
  origin_head: "6c10118",
  health: "OK",
  container_status: "running",
  dry_run_gate_enabled: true,
  phase1_closeout: "BACKEND_PHASE1_CLOSEOUT_READY_WITH_WARN",
};

export const taskQueueMock: AssistantTask[] = [
  {
    id: "task-001",
    title: "가비아 DNS 레코드 조회",
    status: "DRY_RUN",
    risk: "LOW",
    provider: "GABIA",
    action_type: "READ",
    dry_run: true,
    approval_token_exists: false,
    created_at: "2026-05-18T09:00:00Z",
    updated_at: "2026-05-18T09:00:01Z",
  },
  {
    id: "task-002",
    title: "나라장터 공고 목록 조회",
    status: "DRY_RUN",
    risk: "LOW",
    provider: "G2B_NARA",
    action_type: "READ",
    dry_run: true,
    approval_token_exists: false,
    created_at: "2026-05-18T09:05:00Z",
    updated_at: "2026-05-18T09:05:01Z",
  },
  {
    id: "task-003",
    title: "네이버 스마트스토어 주문 조회",
    status: "BLOCKED",
    risk: "CRITICAL",
    provider: "NAVER_SMARTSTORE",
    action_type: "READ_BLOCKED",
    dry_run: true,
    approval_token_exists: false,
    created_at: "2026-05-18T09:10:00Z",
    updated_at: "2026-05-18T09:10:01Z",
  },
  {
    id: "task-004",
    title: "히웍스 메일 목록 조회",
    status: "APPROVAL_DISPLAY_ONLY",
    risk: "MEDIUM",
    provider: "HIWORKS",
    action_type: "READ",
    dry_run: true,
    approval_token_exists: true,
    created_at: "2026-05-18T09:15:00Z",
    updated_at: "2026-05-18T09:15:01Z",
  },
];

export const taskDetailMock: AssistantTask = taskQueueMock[0];

export const approvalGatesMock: ApprovalGate[] = [
  {
    gate_id: "DNS_RECORD_SAVE",
    risk_level: "HIGH",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "BLOCKED",
  },
  {
    gate_id: "PAYMENT",
    risk_level: "CRITICAL",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "BLOCKED",
  },
  {
    gate_id: "BID_SUBMIT",
    risk_level: "CRITICAL",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "BLOCKED",
  },
  {
    gate_id: "POST_TASKS_DRY_RUN_DISABLE",
    risk_level: "CRITICAL",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "BLOCKED",
  },
  {
    gate_id: "APPROVE_EXECUTE_CONNECT",
    risk_level: "CRITICAL",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "NOT_CONNECTED",
  },
  {
    gate_id: "SERVER_RESTART",
    risk_level: "HIGH",
    user_approval_required: true,
    auto_execute_allowed: false,
    evidence_required: true,
    state: "HIDDEN",
    current_behavior: "BLOCKED",
  },
];

export const externalProvidersMock: ExternalProvider[] = [
  { id: "GABIA", label: "가비아", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "KAKAO", label: "카카오", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "NAVER", label: "네이버", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "NAVER_SMARTSTORE", label: "스마트스토어", risk: "CRITICAL", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "GOOGLE", label: "구글", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: false, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "HIWORKS", label: "히웍스", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "G2B_NARA", label: "나라장터", risk: "CRITICAL", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true, certificate_required: true },
  { id: "HOMETAX", label: "홈택스", risk: "CRITICAL", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "WETAX", label: "위택스", risk: "CRITICAL", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "GOVERNMENT24", label: "정부24", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "EMAIL_GENERIC", label: "이메일(범용)", risk: "HIGH", status: "CURRENT", user_present_required: true, desktop_required: false, cookie_storage_forbidden: true, approval_gate_required: true },
  { id: "BANK_GENERIC", label: "인터넷뱅킹", risk: "CRITICAL", status: "CURRENT", user_present_required: true, desktop_required: true, cookie_storage_forbidden: true, approval_gate_required: true },
];

export const auditLogsMock: AuditLogEntry[] = [
  { id: "log-001", timestamp: "2026-05-18T09:00:00Z", source: "storage", level: "INFO", message: "POST /api/v1/tasks dry-run PASS — token 발행 차단됨", redacted: true },
  { id: "log-002", timestamp: "2026-05-18T09:05:00Z", source: "app-logs", level: "INFO", message: "GET /api/v1/health — OK", redacted: true },
  { id: "log-003", timestamp: "2026-05-18T09:10:00Z", source: "storage", level: "WARN", message: "approval_tokens.json legacy 내용 감사 미완 (B-3)", redacted: true },
  { id: "log-004", timestamp: "2026-05-18T09:15:00Z", source: "app-logs", level: "INFO", message: "Server started — POST_TASKS_DRY_RUN_ENABLED=True", redacted: true },
];

export const storageStatusMock: StorageMount[] = [
  { label: "운영 스토리지 (named volume)", path: "/app/ai_orchestrator/storage", persistence: "PERSISTENT", description: "approval_tokens, execution_history, audit_log" },
  { label: "앱 로그 (bind mount)", path: "/app/logs", host_path: "./data/app-logs", persistence: "PERSISTENT", description: "RotatingFileHandler 로그. 컨테이너 재생성 후 유지" },
  { label: "런타임 캐시", path: "scripts/archive/data/chrome_ui_monitor_state.json", persistence: "DISPOSABLE", description: "KW-1: git M 정상. 오류 아님" },
];

export const deploymentStatusMock: DeploymentStatus = {
  server_head: "6c10118",
  origin_head: "6c10118",
  state: "SYNCED",
  build_required: false,
  sop_steps: [
    "git pull origin master",
    "docker compose build",
    "docker compose up -d",
  ],
};

export const knownBacklogMock = [
  { id: "B-1", title: "approve → execute 미연결", status: "known_safe_incomplete", app_note: "실행 버튼 없음" },
  { id: "B-2", title: "DRY_RUN=True 해제 미승인", status: "known_safe_incomplete", app_note: "DRY_RUN 해제 버튼 없음" },
  { id: "B-3", title: "approval_tokens.json 감사 미완", status: "audit_pending", app_note: "token 원문 표시 금지" },
  { id: "KW-1", title: "chrome_ui_monitor_state.json M", status: "runtime_cache", app_note: "오류 아님" },
  { id: "KW-4", title: "docker-compose version 경고", status: "hygiene_backlog", app_note: "compose 버튼 없음" },
];
