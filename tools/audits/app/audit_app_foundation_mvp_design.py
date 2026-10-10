"""APP_FOUNDATION_MVP_DESIGN_01 감사 스크립트.

비서앱 MVP UI shell 착공 전 상세 설계(화면 레이아웃, 컴포넌트, 상태 모델,
API 연결 정책, 금지 버튼 정책)가 백엔드 Phase1 기준선과 충돌하지 않는지 검증.

이 스크립트는 설계/감리 전용 — 실제 앱 코드를 생성하거나 수정하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Literal

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
AUDIT_ID = "APP_FOUNDATION_MVP_DESIGN"

# 이번 공정 안전 잠금
IMPLEMENTATION_ALLOWED = False
FRONTEND_CODE_CHANGE_ALLOWED = False
BACKEND_CODE_CHANGE_ALLOWED = False
SERVER_APPLY_ALLOWED = False

VERDICT_READY = "APP_FOUNDATION_MVP_DESIGN_READY"
VERDICT_WARN = "APP_FOUNDATION_MVP_DESIGN_WITH_WARN"
VERDICT_BLOCKED = "APP_FOUNDATION_MVP_DESIGN_BLOCKED"

# ── 화면 설계 Matrix ──────────────────────────────────────────────────────────

SCREEN_DESIGN_MATRIX = [
    {
        "id": "dashboard",
        "name": "Dashboard",
        "layout": "top-cards + grid-summary",
        "sections": [
            "system_status_cards",
            "backend_phase1_status_card",
            "server_head_card",
            "container_health_card",
            "dry_run_gate_status_card",
            "storage_status_card",
            "known_backlog_summary",
        ],
        "forbidden_buttons": [],
        "api_calls": ["GET /api/v1/health"],
        "api_policy": "CONNECT_NOW",
        "notes": "위험 작업 버튼 없음. 모든 카드는 읽기 전용",
    },
    {
        "id": "task_queue",
        "name": "Task Queue",
        "layout": "filter-bar + table",
        "sections": [
            "filter_bar",
            "task_table",
            "status_badge",
            "risk_badge",
            "provider_badge",
        ],
        "forbidden_buttons": ["execute", "approve_execute"],
        "row_action": "navigate_to_task_detail_only",
        "api_calls": ["GET /api/v1/tasks (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "row 클릭 시 Task Detail 이동만. execute 버튼 없음",
    },
    {
        "id": "task_detail",
        "name": "Task Detail",
        "layout": "header + two-column (summary | evidence)",
        "sections": [
            "request_summary",
            "risk_level_display",
            "dry_run_result",
            "allowed_blocked_status",
            "approval_token_existence_only",
            "audit_trail_link",
            "evidence_panel",
        ],
        "forbidden_buttons": ["execute", "approve_execute", "dry_run_disable"],
        "forbidden_display": ["token_raw", "cookie_raw", "password_raw"],
        "api_calls": ["GET /api/v1/tasks/{id} (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "token 존재 여부만 표시. 원문 표시 금지. 실행 버튼 없음",
    },
    {
        "id": "approval_gate",
        "name": "Approval Gate",
        "layout": "gate-list + detail-panel",
        "sections": [
            "gate_id_display",
            "risk_level_badge",
            "user_approval_required_badge",
            "auto_execute_forbidden_notice",
            "evidence_required_badge",
            "current_behavior_display",
            "approve_execute_unconnected_notice",
        ],
        "forbidden_buttons": ["approve_execute", "reject_execute", "dry_run_disable"],
        "button_state": "display_only",
        "api_calls": ["GET /api/v1/tasks/{id}/approve-status (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "approve→execute 미연결 표시. 실제 승인 실행 버튼 없음",
    },
    {
        "id": "external_sites",
        "name": "External Sites",
        "layout": "provider-grid (12 cards)",
        "sections": [
            "provider_card_grid",
            "user_present_required_badge",
            "desktop_required_badge",
            "cookie_forbidden_badge",
            "token_forbidden_badge",
            "approval_gate_required_badge",
            "risk_level_badge",
            "site_status_display",
        ],
        "forbidden_buttons": ["final_submit", "payment", "dns_save", "certificate_sign", "login_auto"],
        "login_button_state": "display_only",
        "api_calls": ["GET /api/v1/providers (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "login/open 버튼은 display_only 또는 future. 자동 로그인 금지",
    },
    {
        "id": "logs_audit",
        "name": "Logs & Audit",
        "layout": "tab (audit | execution | app-logs)",
        "sections": [
            "audit_log_list",
            "execution_history_list",
            "app_log_tail",
            "log_source_badge",
            "secret_redaction_status",
        ],
        "forbidden_buttons": ["clear_log", "export_raw_token", "show_cookie"],
        "redaction_policy": "all_secret_token_cookie_password_redacted",
        "api_calls": ["GET /api/v1/logs (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "secret/token/cookie/password 원문 표시 금지. detail view = redacted only",
    },
    {
        "id": "storage_status",
        "name": "Storage Status",
        "layout": "storage-cards + ttl-policy",
        "sections": [
            "named_volume_card",
            "bind_mount_card",
            "runtime_cache_card",
            "ttl_policy_display",
            "persistence_badge",
        ],
        "forbidden_buttons": ["delete_storage", "clear_tokens", "reset_db"],
        "api_calls": ["GET /api/v1/storage/status (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "/app/ai_orchestrator/storage named volume, /app/logs bind mount, runtime cache",
    },
    {
        "id": "deployment_status",
        "name": "Deployment Status",
        "layout": "head-diff + sop-steps + container-status",
        "sections": [
            "server_head_display",
            "origin_head_display",
            "head_diff_status",
            "deployment_sop_panel",
            "container_status_list",
            "build_required_notice",
        ],
        "forbidden_buttons": ["restart_server", "docker_compose_action", "force_deploy"],
        "deploy_action_state": "display_only",
        "api_calls": ["GET /api/v1/deployment/status (future)"],
        "api_policy": "FUTURE_ENDPOINT_REQUIRED",
        "notes": "서버 HEAD/origin HEAD diff만 표시. restart/compose 버튼 없음",
    },
]

# ── 컴포넌트 설계 Matrix ──────────────────────────────────────────────────────

COMPONENT_DESIGN_MATRIX = [
    {
        "id": "StatusBadge",
        "props": ["status: OK|WARN|BLOCKED|DRY_RUN|DISPLAY_ONLY|FUTURE"],
        "variants": ["ok", "warn", "blocked", "dry_run", "display_only", "future"],
        "used_in": ["dashboard", "task_queue", "task_detail", "approval_gate"],
    },
    {
        "id": "RiskBadge",
        "props": ["level: LOW|MEDIUM|HIGH|CRITICAL"],
        "variants": ["low", "medium", "high", "critical"],
        "used_in": ["task_queue", "task_detail", "approval_gate", "external_sites"],
    },
    {
        "id": "GateBadge",
        "props": ["state: APPROVAL_REQUIRED|AUTO_EXECUTE_FORBIDDEN|EVIDENCE_REQUIRED"],
        "variants": ["approval_required", "auto_execute_forbidden", "evidence_required"],
        "used_in": ["approval_gate", "task_detail"],
    },
    {
        "id": "BackendStatusCard",
        "props": ["head: str", "health: BackendHealth", "container_status: str"],
        "used_in": ["dashboard"],
    },
    {
        "id": "StorageStatusCard",
        "props": ["named_volume: StoragePersistence", "bind_mount: bool", "runtime_cache: str"],
        "used_in": ["dashboard", "storage_status"],
    },
    {
        "id": "ProviderCard",
        "props": [
            "provider_id: str",
            "risk: ActionRisk",
            "user_present_required: bool",
            "cookie_forbidden: bool",
            "approval_gate_required: bool",
        ],
        "used_in": ["external_sites"],
    },
    {
        "id": "TaskTable",
        "props": ["tasks: Task[]", "on_row_click: navigate_only"],
        "forbidden_actions": ["execute", "approve_execute"],
        "used_in": ["task_queue"],
    },
    {
        "id": "TaskDetailPanel",
        "props": [
            "task_id: str",
            "risk_level: ActionRisk",
            "dry_run_result: dict",
            "token_exists: bool",
        ],
        "forbidden_display": ["token_raw", "cookie_raw"],
        "used_in": ["task_detail"],
    },
    {
        "id": "AuditLogList",
        "props": ["logs: AuditLog[]", "redacted: bool = True"],
        "redaction_policy": "always_redacted",
        "used_in": ["logs_audit"],
    },
    {
        "id": "ForbiddenActionBanner",
        "props": ["action_id: str", "reason: str"],
        "used_in": ["task_detail", "approval_gate", "deployment_status"],
    },
    {
        "id": "DryRunNotice",
        "props": ["enabled: bool", "gate_status: str"],
        "used_in": ["task_queue", "task_detail", "dashboard"],
    },
    {
        "id": "DeploymentSopPanel",
        "props": ["current_head: str", "origin_head: str", "sop_steps: str[]"],
        "forbidden_actions": ["restart", "compose_action"],
        "used_in": ["deployment_status"],
    },
]

# ── 상태 모델 ─────────────────────────────────────────────────────────────────

STATE_MODEL_MATRIX = {
    "TaskStatus": ["READ_ONLY", "DRY_RUN", "BLOCKED", "APPROVAL_DISPLAY_ONLY", "FUTURE", "ERROR"],
    "ActionRisk": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    "ProviderStatus": ["CURRENT", "PLANNED", "HOLD", "DISABLED"],
    "GateState": ["DISPLAY_ONLY", "DISABLED", "HIDDEN", "DRY_RUN_ONLY"],
    "BackendHealth": ["OK", "WARN", "BLOCKED", "UNKNOWN"],
    "StoragePersistence": ["PERSISTENT", "EPHEMERAL", "DISPOSABLE", "UNKNOWN"],
    "DeploymentState": ["SYNCED", "BUILD_REQUIRED", "DEPLOYED", "RESTART_REQUIRED", "BLOCKED"],
}

# ── API 연결 정책 Matrix ──────────────────────────────────────────────────────

API_CONNECTION_POLICY_MATRIX = [
    {"endpoint": "GET /api/v1/health", "policy": "CONNECT_NOW", "note": "MVP 1차 연결 대상"},
    {"endpoint": "GET /api/v1/inbox", "policy": "MOCK_ONLY", "note": "실제 fetch 실행 금지"},
    {
        "endpoint": "POST /api/v1/tasks",
        "policy": "DRY_RUN_ONLY",
        "note": "POST_TASKS_DRY_RUN_ENABLED=True. 실제 실행 금지",
    },
    {"endpoint": "POST /api/v1/inbox/email/fetch", "policy": "MOCK_ONLY", "note": "NO_OP_ONLY"},
    {"endpoint": "POST /api/v1/tasks/{id}/approve", "policy": "BLOCKED", "note": "approve→execute 미연결"},
    {"endpoint": "POST /api/v1/tasks/{id}/reject", "policy": "BLOCKED", "note": "reject→execute 미연결"},
    {"endpoint": "POST /api/v1/tasks/{id}/execute", "policy": "BLOCKED", "note": "실행 완전 차단"},
    {"endpoint": "POST /api/v1/external/*/submit", "policy": "BLOCKED", "note": "외부 사이트 최종 제출 완전 차단"},
    {"endpoint": "GET /api/v1/logs", "policy": "FUTURE_ENDPOINT_REQUIRED", "note": "Phase 2 후보"},
    {"endpoint": "GET /api/v1/storage/status", "policy": "FUTURE_ENDPOINT_REQUIRED", "note": "Phase 2 후보"},
    {"endpoint": "GET /api/v1/providers", "policy": "FUTURE_ENDPOINT_REQUIRED", "note": "Phase 2 후보"},
    {"endpoint": "GET /api/v1/deployment/status", "policy": "FUTURE_ENDPOINT_REQUIRED", "note": "Phase 2 후보"},
    {"endpoint": "GET /api/v1/tasks", "policy": "FUTURE_ENDPOINT_REQUIRED", "note": "task queue Phase 2 후보"},
]

# ── 금지 버튼 정책 Matrix ─────────────────────────────────────────────────────

FORBIDDEN_ACTION_MATRIX = [
    {
        "action_id": "execute",
        "target_screens": ["task_queue", "task_detail"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "POST /tasks dry-run-only. approve→execute 미연결",
        "future_unlock_condition": "APPROVE_EXECUTE_CONNECT gate 해제 + DRY_RUN 해제 별도 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "approve_execute",
        "target_screens": ["approval_gate", "task_detail"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "B-1: approve→execute 미연결. 현재 상태 표시만",
        "future_unlock_condition": "APPROVE_EXECUTE_CONNECT gate 별도 공정 완료",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "dry_run_disable",
        "target_screens": ["dashboard", "task_detail"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "B-2: DRY_RUN=True 해제 미승인. 해제 버튼 없음",
        "future_unlock_condition": "POST_TASKS_DRY_RUN_DISABLE gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "final_submit",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "외부 사이트 최종 제출 완전 차단",
        "future_unlock_condition": "외부 사이트별 gate 별도 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "payment",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "결제 완전 차단. PAYMENT gate critical",
        "future_unlock_condition": "PAYMENT gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "dns_save",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "DNS_RECORD_SAVE gate high. 저장 버튼 없음",
        "future_unlock_condition": "DNS_RECORD_SAVE gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "certificate_sign",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "CERTIFICATE_SIGN gate critical. G2B_NARA 관련",
        "future_unlock_condition": "CERTIFICATE_SIGN gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "server_restart",
        "target_screens": ["deployment_status"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "SERVER_RESTART gate high. baked-in 이미지 구조상 restart 단독 금지",
        "future_unlock_condition": "SERVER_RESTART gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "docker_compose_action",
        "target_screens": ["deployment_status"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "DOCKER_COMPOSE_ACTION gate high. 앱에서 compose 조작 금지",
        "future_unlock_condition": "DOCKER_COMPOSE_ACTION gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "external_site_final_action",
        "target_screens": ["external_sites", "task_detail"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "외부 사이트 최종 제출 완전 차단 (범용)",
        "future_unlock_condition": "외부 사이트별 gate 별도 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "smartstore_product_update",
        "target_screens": ["external_sites", "task_detail"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "SMARTSTORE_PRODUCT_UPDATE gate critical",
        "future_unlock_condition": "SMARTSTORE_PRODUCT_UPDATE gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "bid_submit",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "BID_SUBMIT gate critical. 나라장터 투찰 완전 차단",
        "future_unlock_condition": "BID_SUBMIT gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
    {
        "action_id": "tax_submit",
        "target_screens": ["external_sites"],
        "button_state": "hidden",
        "auto_execute_allowed": False,
        "reason": "TAX_SUBMIT gate critical. 홈택스/위택스 신고 완전 차단",
        "future_unlock_condition": "TAX_SUBMIT gate 별도 공정 승인",
        "approval_required": True,
        "audit_required": True,
    },
]

# ── Known Backlog 매핑 ────────────────────────────────────────────────────────

KNOWN_BACKLOG_MAPPING = [
    {
        "id": "B-1",
        "title": "approve → execute 미연결",
        "design_impact": "approve_execute 버튼 hidden. Approval Gate 화면에 '승인 후 실행 미연결' 표시",
        "screens_affected": ["approval_gate", "task_detail"],
    },
    {
        "id": "B-2",
        "title": "DRY_RUN=True 해제 미승인",
        "design_impact": "dry_run_disable 버튼 hidden. DryRunNotice 컴포넌트로 dry-run-only 표시",
        "screens_affected": ["dashboard", "task_queue", "task_detail"],
    },
    {
        "id": "B-3",
        "title": "approval_tokens.json 내용 감사 미완",
        "design_impact": "token 원문 표시 금지. token 존재 여부만 TaskDetailPanel에 표시",
        "screens_affected": ["task_detail", "logs_audit"],
    },
    {
        "id": "KW-1",
        "title": "chrome_ui_monitor_state.json git M 상태",
        "design_impact": "Storage Status 화면에서 RUNTIME_CACHE_DISPOSABLE로 표시. 오류 아님",
        "screens_affected": ["storage_status", "dashboard"],
    },
    {
        "id": "KW-4",
        "title": "docker-compose.yml version obsolete 경고",
        "design_impact": "Deployment Status 화면에서 hygiene backlog로 표시. compose 조작 버튼 없음",
        "screens_affected": ["deployment_status"],
    },
    {
        "id": "EXT-CAD",
        "title": "external_cad 14개 deselected",
        "design_impact": "앱 MVP 범위 밖. CAD는 별도 환경 공정. 앱 화면에 CAD 미포함",
        "screens_affected": [],
    },
]

# ── 다음 공정 준비 ────────────────────────────────────────────────────────────

NEXT_PHASE_READINESS = {
    "phase": "APP_UI_SHELL_SKELETON_01",
    "conditions": [
        "screen_design_matrix 8개 확정",
        "component_design_matrix 12개 확정",
        "state_model_matrix 7개 확정",
        "api_connection_policy_matrix 확정",
        "forbidden_action_matrix 13개 확정",
        "known_backlog_mapping 확정",
        "implementation_allowed=False 확인",
        "frontend_code_change_allowed=False 확인",
    ],
    "blocked_until": "APP_FOUNDATION_MVP_DESIGN_READY 판정",
    "next_after_skeleton": "APP_API_CONTRACT_ENDPOINTS_PREP_01",
}

# ── Audit 함수 ────────────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str = ""


@dataclass
class AuditReport:
    generated_at: str = ""
    audit_id: str = AUDIT_ID
    checks: list[CheckResult] = field(default_factory=list)
    verdict: str = ""

    def add(self, name: str, status: Literal["PASS", "WARN", "FAIL"], message: str = "") -> None:
        self.checks.append(CheckResult(name, status, message))

    def summary(self) -> dict:
        passed = sum(1 for c in self.checks if c.status == "PASS")
        warned = sum(1 for c in self.checks if c.status == "WARN")
        failed = sum(1 for c in self.checks if c.status == "FAIL")
        return {
            "audit_id": self.audit_id,
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "total": len(self.checks),
            "checks": [{"name": c.name, "status": c.status, "message": c.message} for c in self.checks],
        }


def check_safety_locks(report: AuditReport) -> None:
    for flag, name in [
        (IMPLEMENTATION_ALLOWED, "IMPLEMENTATION_ALLOWED"),
        (FRONTEND_CODE_CHANGE_ALLOWED, "FRONTEND_CODE_CHANGE_ALLOWED"),
        (BACKEND_CODE_CHANGE_ALLOWED, "BACKEND_CODE_CHANGE_ALLOWED"),
        (SERVER_APPLY_ALLOWED, "SERVER_APPLY_ALLOWED"),
    ]:
        if flag is False:
            report.add(f"lock_{name.lower()}", "PASS", f"{name}=False 확인됨")
        else:
            report.add(f"lock_{name.lower()}", "FAIL", f"{name}=True — 이번 공정에서 허용 불가")


def check_screens(report: AuditReport) -> None:
    if len(SCREEN_DESIGN_MATRIX) >= 8:
        report.add("screen_count", "PASS", f"{len(SCREEN_DESIGN_MATRIX)}개 화면 설계됨")
    else:
        report.add("screen_count", "FAIL", f"화면 {len(SCREEN_DESIGN_MATRIX)}개 < 8개 필수")

    required_ids = {
        "dashboard",
        "task_queue",
        "task_detail",
        "approval_gate",
        "external_sites",
        "logs_audit",
        "storage_status",
        "deployment_status",
    }
    defined_ids = {s["id"] for s in SCREEN_DESIGN_MATRIX}
    missing = required_ids - defined_ids
    if not missing:
        report.add("screen_required_ids", "PASS", "필수 8개 화면 ID 설계됨")
    else:
        report.add("screen_required_ids", "FAIL", f"누락 화면 설계: {missing}")

    execute_screens = [s for s in SCREEN_DESIGN_MATRIX if "execute" in s.get("forbidden_buttons", [])]
    if execute_screens:
        report.add("screen_execute_forbidden", "PASS", f"{len(execute_screens)}개 화면에 execute forbidden 설계됨")
    else:
        report.add("screen_execute_forbidden", "WARN", "execute forbidden 화면 설계 확인 필요")


def check_components(report: AuditReport) -> None:
    if len(COMPONENT_DESIGN_MATRIX) >= 10:
        report.add("component_count", "PASS", f"{len(COMPONENT_DESIGN_MATRIX)}개 컴포넌트 설계됨")
    else:
        report.add("component_count", "FAIL", f"컴포넌트 {len(COMPONENT_DESIGN_MATRIX)}개 < 10개 필수")

    required_components = {
        "StatusBadge",
        "RiskBadge",
        "ProviderCard",
        "TaskTable",
        "TaskDetailPanel",
        "AuditLogList",
        "DryRunNotice",
    }
    defined = {c["id"] for c in COMPONENT_DESIGN_MATRIX}
    missing = required_components - defined
    if not missing:
        report.add("component_required_ids", "PASS", f"필수 컴포넌트 {len(required_components)}개 설계됨")
    else:
        report.add("component_required_ids", "FAIL", f"누락 컴포넌트: {missing}")


def check_state_models(report: AuditReport) -> None:
    if len(STATE_MODEL_MATRIX) >= 6:
        report.add("state_model_count", "PASS", f"{len(STATE_MODEL_MATRIX)}개 상태 모델 정의됨")
    else:
        report.add("state_model_count", "FAIL", f"상태 모델 {len(STATE_MODEL_MATRIX)}개 < 6개 필수")

    for model_name in [
        "TaskStatus",
        "ActionRisk",
        "ProviderStatus",
        "GateState",
        "BackendHealth",
        "StoragePersistence",
        "DeploymentState",
    ]:
        if model_name in STATE_MODEL_MATRIX:
            report.add(f"state_{model_name}", "PASS", f"{model_name} 정의됨: {STATE_MODEL_MATRIX[model_name]}")
        else:
            report.add(f"state_{model_name}", "FAIL", f"{model_name} 미정의")


def check_api_policy(report: AuditReport) -> None:
    health = next((a for a in API_CONNECTION_POLICY_MATRIX if a["endpoint"] == "GET /api/v1/health"), None)
    if health and health["policy"] == "CONNECT_NOW":
        report.add("api_health_connect_now", "PASS", "GET /health = CONNECT_NOW")
    else:
        report.add("api_health_connect_now", "FAIL", "GET /health CONNECT_NOW 미설정")

    tasks = next((a for a in API_CONNECTION_POLICY_MATRIX if a["endpoint"] == "POST /api/v1/tasks"), None)
    if tasks and tasks["policy"] in ("DRY_RUN_ONLY", "MOCK_ONLY"):
        report.add("api_post_tasks_dry_run_only", "PASS", f"POST /tasks = {tasks['policy']}")
    else:
        report.add("api_post_tasks_dry_run_only", "FAIL", "POST /tasks DRY_RUN_ONLY/MOCK_ONLY 미설정")

    for ep in ["POST /api/v1/tasks/{id}/approve", "POST /api/v1/tasks/{id}/reject"]:
        a = next((x for x in API_CONNECTION_POLICY_MATRIX if x["endpoint"] == ep), None)
        if a and a["policy"] in ("BLOCKED", "DISPLAY_ONLY"):
            report.add(f"api_{ep.split('/')[-1]}_blocked", "PASS", f"{ep} = {a['policy']}")
        else:
            report.add(f"api_{ep}_blocked", "FAIL", f"{ep} BLOCKED/DISPLAY_ONLY 미설정")

    execute = next((a for a in API_CONNECTION_POLICY_MATRIX if "execute" in a["endpoint"]), None)
    if execute and execute["policy"] == "BLOCKED":
        report.add("api_execute_blocked", "PASS", "execute API = BLOCKED")
    else:
        report.add("api_execute_blocked", "FAIL", "execute API BLOCKED 미설정")


def check_forbidden_actions(report: AuditReport) -> None:
    if len(FORBIDDEN_ACTION_MATRIX) >= 10:
        report.add("forbidden_action_count", "PASS", f"{len(FORBIDDEN_ACTION_MATRIX)}개 금지 액션 설계됨")
    else:
        report.add("forbidden_action_count", "FAIL", f"금지 액션 {len(FORBIDDEN_ACTION_MATRIX)}개 < 10개 필수")

    required_actions = {
        "execute",
        "approve_execute",
        "dry_run_disable",
        "dns_save",
        "payment",
        "server_restart",
        "docker_compose_action",
    }
    defined = {a["action_id"] for a in FORBIDDEN_ACTION_MATRIX}
    for action_id in required_actions:
        if action_id in defined:
            report.add(f"forbidden_{action_id}", "PASS", f"{action_id} forbidden 설계됨")
        else:
            report.add(f"forbidden_{action_id}", "FAIL", f"{action_id} forbidden 미설계")

    bad = [a for a in FORBIDDEN_ACTION_MATRIX if a.get("auto_execute_allowed") is not False]
    if not bad:
        report.add("forbidden_auto_execute_all_false", "PASS", "전체 금지 액션 auto_execute_allowed=False")
    else:
        report.add(
            "forbidden_auto_execute_all_false",
            "FAIL",
            f"auto_execute_allowed=True 존재: {[a['action_id'] for a in bad]}",
        )


def check_known_backlog(report: AuditReport) -> None:
    backlog_ids = {b["id"] for b in KNOWN_BACKLOG_MAPPING}
    required = {"B-1", "B-2", "B-3", "KW-1", "KW-4", "EXT-CAD"}
    missing = required - backlog_ids
    if not missing:
        report.add("known_backlog_all_mapped", "PASS", f"known backlog {len(required)}개 설계 반영됨")
    else:
        report.add("known_backlog_all_mapped", "FAIL", f"누락 backlog: {missing}")


def check_next_phase(report: AuditReport) -> None:
    if NEXT_PHASE_READINESS.get("phase") == "APP_UI_SHELL_SKELETON_01":
        report.add("next_phase_skeleton_defined", "PASS", "다음 공정 APP_UI_SHELL_SKELETON_01 정의됨")
    else:
        report.add("next_phase_skeleton_defined", "WARN", "다음 공정 미정의")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_safety_locks(report)
    check_screens(report)
    check_components(report)
    check_state_models(report)
    check_api_policy(report)
    check_forbidden_actions(report)
    check_known_backlog(report)
    check_next_phase(report)

    summary = report.summary()
    if summary["failed"] > 0:
        report.verdict = VERDICT_BLOCKED
    elif summary["warned"] > 0:
        report.verdict = VERDICT_WARN
    else:
        report.verdict = VERDICT_READY
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()

    out_path = REPO_ROOT / "data" / "app_foundation_mvp_design_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] MVP Design Audit")
    print("=" * 70)
    for c in report.checks:
        mark = "✓" if c.status == "PASS" else ("△" if c.status == "WARN" else "✗")
        print(f"  [{c.status:<4}] {mark} {c.name}: {c.message}")
    print("=" * 70)
    print(f"PASS={summary['passed']} WARN={summary['warned']} FAIL={summary['failed']}")
    print(f"VERDICT: {report.verdict}")
    print("=" * 70)

    if summary["failed"] > 0:
        raise SystemExit(1)
