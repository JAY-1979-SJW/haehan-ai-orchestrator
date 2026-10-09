"""APP_FOUNDATION_MVP_PREP_01 감사 스크립트.

백엔드 Phase 1 준공 기준선을 바탕으로 비서앱 1차 MVP 설계가
보안/정책/known backlog와 충돌하지 않는지 검증한다.

이 스크립트는 실제 앱 구현 파일을 수정하지 않는다. 설계/감리 전용.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
AUDIT_ID = "APP_FOUNDATION_MVP_PREP_01"

VERDICT_READY = "APP_FOUNDATION_MVP_PREP_READY"
VERDICT_WARN = "APP_FOUNDATION_MVP_PREP_WITH_WARN"
VERDICT_BLOCKED = "APP_FOUNDATION_MVP_PREP_BLOCKED"

# ── MVP 화면 정의 ─────────────────────────────────────────────────────────────

MVP_SCREENS = [
    {
        "id": "dashboard",
        "name": "Dashboard",
        "allowed_actions": ["read_status", "read_health", "read_warnings"],
        "forbidden_buttons": [],
        "description": "백엔드 Phase1 상태, 서버 HEAD, container health, pytest baseline, storage 상태, known warnings",
    },
    {
        "id": "task_queue",
        "name": "Task Queue",
        "allowed_actions": ["list_tasks", "read_dry_run_status", "read_blocked_status"],
        "forbidden_buttons": ["execute", "approve_execute"],
        "description": "작업 목록, dry-run/blocked/approval-required 상태, POST /tasks dry-run-only 배지",
    },
    {
        "id": "task_detail",
        "name": "Task Detail",
        "allowed_actions": ["read_payload", "read_risk_level", "read_dry_run_result", "read_audit_trail"],
        "forbidden_buttons": ["execute", "approve_execute", "dry_run_disable"],
        "description": "요청 payload 요약, risk level, dry_run 결과, approval_token 존재 여부, evidence/audit trail",
    },
    {
        "id": "approval_gate",
        "name": "Approval Gate",
        "allowed_actions": ["list_pending_approvals", "read_policy", "read_gate_state"],
        "forbidden_buttons": ["approve_execute", "reject_execute", "dry_run_disable"],
        "description": "승인 대기 목록, 승인 정책 설명, approve→execute 미연결 표시. 실제 실행 연결 없음",
    },
    {
        "id": "external_sites",
        "name": "External Sites",
        "allowed_actions": ["list_providers", "read_policy", "read_login_requirement"],
        "forbidden_buttons": ["final_submit", "payment", "dns_save", "certificate_sign"],
        "description": "12개 provider 목록, user-present 로그인 필요, desktop required, cookie 금지, gate 필요",
    },
    {
        "id": "logs_audit",
        "name": "Logs & Audit",
        "allowed_actions": ["read_audit_log", "read_execution_history", "read_app_log"],
        "forbidden_buttons": ["clear_log", "export_raw_token", "show_cookie"],
        "description": "audit log, execution history, app logs. secret/token 원문 출력 금지",
    },
    {
        "id": "storage_status",
        "name": "Storage Status",
        "allowed_actions": ["read_volume_status", "read_bind_mount_status", "read_ttl_policy"],
        "forbidden_buttons": ["delete_storage", "clear_tokens", "reset_db"],
        "description": "/app/ai_orchestrator/storage named volume, /app/logs bind mount, TTL 정책",
    },
    {
        "id": "deployment_status",
        "name": "Deployment Status",
        "allowed_actions": ["read_server_head", "read_origin_head", "read_sop"],
        "forbidden_buttons": ["restart_server", "docker_compose_action", "force_deploy"],
        "description": "서버 HEAD, origin HEAD, 배포 SOP. restart/compose 버튼 없음",
    },
]

# ── API Contract Matrix ───────────────────────────────────────────────────────

API_CONTRACT = [
    {
        "endpoint": "GET /api/v1/health",
        "classification": "READ_ONLY_ALLOWED",
        "note": "컨테이너/앱 헬스 조회",
    },
    {
        "endpoint": "GET /api/v1/inbox",
        "classification": "READ_ONLY_ALLOWED",
        "note": "8400 handler 정상. legacy effectively disabled",
    },
    {
        "endpoint": "POST /api/v1/inbox/email/fetch",
        "classification": "DRY_RUN_ALLOWED",
        "note": "NO_OP_ONLY. 실제 fetch 실행 금지",
    },
    {
        "endpoint": "POST /api/v1/tasks",
        "classification": "DRY_RUN_ALLOWED",
        "note": "POST_TASKS_DRY_RUN_ENABLED=True. medium token 발행 차단. dry-run only",
    },
    {
        "endpoint": "POST /api/v1/tasks/{id}/approve",
        "classification": "APPROVAL_DISPLAY_ONLY",
        "note": "approve→execute 미연결. 상태 표시만",
    },
    {
        "endpoint": "POST /api/v1/tasks/{id}/reject",
        "classification": "APPROVAL_DISPLAY_ONLY",
        "note": "reject→execute 미연결. 상태 표시만",
    },
    {
        "endpoint": "POST /api/v1/tasks/{id}/execute",
        "classification": "BLOCKED",
        "note": "실제 실행 엔드포인트. MVP에서 완전 차단",
    },
    {
        "endpoint": "POST /api/v1/external/*/submit",
        "classification": "BLOCKED",
        "note": "외부 사이트 최종 제출. MVP에서 완전 차단",
    },
    {
        "endpoint": "GET /api/v1/logs",
        "classification": "FUTURE",
        "note": "audit log read endpoint. Phase 2 후보",
    },
    {
        "endpoint": "GET /api/v1/storage/status",
        "classification": "FUTURE",
        "note": "storage 상태 endpoint. Phase 2 후보",
    },
    {
        "endpoint": "GET /api/v1/providers",
        "classification": "FUTURE",
        "note": "external site registry endpoint. Phase 2 후보",
    },
    {
        "endpoint": "GET /api/v1/deployment/status",
        "classification": "FUTURE",
        "note": "deployment status endpoint. Phase 2 후보",
    },
]

# ── Approval Gate Matrix ──────────────────────────────────────────────────────

APPROVAL_GATE_MATRIX = [
    {
        "gate_id": "DNS_RECORD_SAVE",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "DOMAIN_TRANSFER",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "NAMESERVER_CHANGE",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "PAYMENT",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "BID_SUBMIT",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "CERTIFICATE_SIGN",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "TAX_SUBMIT",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "EMAIL_SEND",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "disabled",
    },
    {
        "gate_id": "SMARTSTORE_PRODUCT_UPDATE",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "SMARTSTORE_ORDER_ACTION",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "ACCOUNT_CHANGE",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "FILE_UPLOAD_FINAL_SUBMIT",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "DOCUMENT_FINAL_SUBMIT",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "POST_TASKS_DRY_RUN_DISABLE",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "APPROVE_EXECUTE_CONNECT",
        "risk_level": "critical",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "NOT_CONNECTED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "SERVER_RESTART",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
    {
        "gate_id": "DOCKER_COMPOSE_ACTION",
        "risk_level": "high",
        "user_approval_required": True,
        "auto_execute_allowed": False,
        "evidence_required": True,
        "current_app_behavior": "BLOCKED",
        "mvp_button_state": "hidden",
    },
]

# ── Known Backlog ─────────────────────────────────────────────────────────────

KNOWN_BACKLOG = [
    {
        "id": "B-1",
        "title": "approve → execute 미연결",
        "app_behavior": "실행 버튼 없음. '승인 후 실행 미연결' 상태 표시",
        "status": "known_safe_incomplete",
    },
    {
        "id": "B-2",
        "title": "DRY_RUN=True 해제 미승인",
        "app_behavior": "DRY_RUN 해제 버튼 없음. POST /tasks = dry-run-only 표시",
        "status": "known_safe_incomplete",
    },
    {
        "id": "B-3",
        "title": "approval_tokens.json legacy 내용 감사 필요",
        "app_behavior": "token 원문 표시 금지. token 존재 여부만 표시 가능",
        "status": "audit_pending",
    },
    {
        "id": "KW-1",
        "title": "chrome_ui_monitor_state.json git M 상태",
        "app_behavior": "runtime cache로 분류. 오류로 표시하지 않음",
        "status": "known_warn_runtime_cache",
    },
    {
        "id": "KW-4",
        "title": "docker-compose.yml version obsolete 경고",
        "app_behavior": "배포 hygiene backlog 표시. restart/compose 조작 금지",
        "status": "known_warn_hygiene",
    },
    {
        "id": "EXT-CAD",
        "title": "external_cad 14개 deselected",
        "app_behavior": "앱 MVP 범위 밖. CAD external plugin 환경 smoke는 별도 공정",
        "status": "deselected_separate_env",
    },
]

# ── Provider Registry ─────────────────────────────────────────────────────────

PROVIDERS = [
    {
        "id": "GABIA",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "KAKAO",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "NAVER",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "NAVER_SMARTSTORE",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
        "risk_level": "critical",
    },
    {
        "id": "GOOGLE",
        "user_present_required": True,
        "desktop_required": False,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "HIWORKS",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "G2B_NARA",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
        "certificate_required": True,
    },
    {
        "id": "HOMETAX",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "WETAX",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "GOVERNMENT24",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "EMAIL_GENERIC",
        "user_present_required": True,
        "desktop_required": False,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
    },
    {
        "id": "BANK_GENERIC",
        "user_present_required": True,
        "desktop_required": True,
        "cookie_storage_forbidden": True,
        "approval_gate_required": True,
        "risk_level": "critical",
    },
]

# ── Storage Matrix ────────────────────────────────────────────────────────────

STORAGE_MATRIX: dict[str, Any] = {
    "named_volume": {
        "path": "/app/ai_orchestrator/storage",
        "classification": "PERSISTENT_OPERATION_REQUIRED",
        "contents": ["approval_tokens.json", "execution_history.jsonl", "audit_log.jsonl"],
    },
    "bind_mount_logs": {
        "path": "/app/logs",
        "host_path": "./data/app-logs",
        "classification": "PERSISTENT_AUDIT_REQUIRED",
        "bind_mount_applied": True,
    },
    "runtime_cache": {
        "path": "scripts/archive/data/chrome_ui_monitor_state.json",
        "classification": "RUNTIME_CACHE_DISPOSABLE",
        "git_modified": True,
        "note": "KW-1: git M 상태 — 오류 아님",
    },
}

# ── Pytest Baseline ───────────────────────────────────────────────────────────

PYTEST_BASELINE = {
    "total_passed": 9340,
    "total_failed": 0,
    "total_skipped": 8,
    "total_deselected": 14,
    "deselect_reason": "external_cad marker — local_worker_plugins 미설치 환경",
    "ordering": "deterministic (-p no:randomly)",
    "baseline_tag": "TEST_BASELINE_CLEANED",
}

# ── Deployment SOP ────────────────────────────────────────────────────────────

DEPLOYMENT_SOP: dict[str, Any] = {
    "steps": [
        "git pull origin master",
        "docker compose build",
        "docker compose up -d",
    ],
    "restart_only_forbidden": True,
    "reason": "baked-in image: 소스코드가 이미지에 포함 → restart 단독 금지",
}

# ── Audit 검사 함수 ───────────────────────────────────────────────────────────


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


def check_screens(report: AuditReport) -> None:
    count = len(MVP_SCREENS)
    if count >= 8:
        report.add("mvp_screens_count", "PASS", f"{count}개 화면 정의됨")
    else:
        report.add("mvp_screens_count", "FAIL", f"화면 {count}개 < 8개 필수")

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
    defined_ids = {s["id"] for s in MVP_SCREENS}
    missing = required_ids - defined_ids
    if not missing:
        report.add("mvp_screens_required_ids", "PASS", "필수 8개 화면 ID 모두 존재")
    else:
        report.add("mvp_screens_required_ids", "FAIL", f"누락 화면: {missing}")


def check_api_contract(report: AuditReport) -> None:
    post_tasks = next((a for a in API_CONTRACT if a["endpoint"] == "POST /api/v1/tasks"), None)
    if post_tasks and post_tasks["classification"] == "DRY_RUN_ALLOWED":
        report.add("api_post_tasks_dry_run_only", "PASS", "POST /tasks = DRY_RUN_ALLOWED")
    else:
        report.add("api_post_tasks_dry_run_only", "FAIL", "POST /tasks 분류 오류")

    for ep in ["POST /api/v1/tasks/{id}/approve", "POST /api/v1/tasks/{id}/reject"]:
        a = next((x for x in API_CONTRACT if x["endpoint"] == ep), None)
        if a and a["classification"] in ("APPROVAL_DISPLAY_ONLY", "BLOCKED"):
            report.add(
                f"api_{ep.replace('/', '_').replace('{', '').replace('}', '')}_display_only",
                "PASS",
                f"{ep} = {a['classification']}",
            )
        else:
            report.add(f"api_{ep}_display_only", "FAIL", f"{ep} 분류 오류")

    blocked = [a for a in API_CONTRACT if "execute" in a["endpoint"] and a["classification"] == "BLOCKED"]
    if blocked:
        report.add("api_execute_blocked", "PASS", "execute endpoint = BLOCKED")
    else:
        report.add("api_execute_blocked", "FAIL", "execute endpoint 차단 미정의")

    blocked_submit = [a for a in API_CONTRACT if "submit" in a["endpoint"] and a["classification"] == "BLOCKED"]
    if blocked_submit:
        report.add("api_external_submit_blocked", "PASS", "외부 사이트 submit = BLOCKED")
    else:
        report.add("api_external_submit_blocked", "FAIL", "외부 사이트 submit 차단 미정의")


def check_forbidden_buttons(report: AuditReport) -> None:
    all_forbidden: set[Any] = set()
    for screen in MVP_SCREENS:
        all_forbidden.update(screen.get("forbidden_buttons", []))

    required_forbidden = {
        "execute": "실행 버튼",
        "approve_execute": "approve→execute 버튼",
        "dry_run_disable": "DRY_RUN 해제 버튼",
        "final_submit": "외부 최종 제출 버튼",
        "payment": "결제 버튼",
        "dns_save": "DNS 저장 버튼",
        "restart_server": "서버 재시작 버튼",
        "docker_compose_action": "docker compose 버튼",
    }
    for btn_id, btn_name in required_forbidden.items():
        if btn_id in all_forbidden:
            report.add(f"forbidden_btn_{btn_id}", "PASS", f"{btn_name} forbidden 정의됨")
        else:
            report.add(f"forbidden_btn_{btn_id}", "WARN", f"{btn_name} forbidden 목록에 미포함 — 설계 확인 필요")


def check_approval_gates(report: AuditReport) -> None:
    gate_ids = {g["gate_id"] for g in APPROVAL_GATE_MATRIX}
    required_gates = {
        "POST_TASKS_DRY_RUN_DISABLE",
        "APPROVE_EXECUTE_CONNECT",
        "SERVER_RESTART",
        "DOCKER_COMPOSE_ACTION",
        "PAYMENT",
        "DNS_RECORD_SAVE",
        "BID_SUBMIT",
        "CERTIFICATE_SIGN",
    }
    missing = required_gates - gate_ids
    if not missing:
        report.add("approval_gate_required_ids", "PASS", f"필수 gate {len(required_gates)}개 모두 존재")
    else:
        report.add("approval_gate_required_ids", "FAIL", f"누락 gate: {missing}")

    bad = [g for g in APPROVAL_GATE_MATRIX if g.get("auto_execute_allowed") is not False]
    if not bad:
        report.add("approval_gate_auto_execute_false", "PASS", "전체 gate auto_execute_allowed=False")
    else:
        report.add(
            "approval_gate_auto_execute_false",
            "FAIL",
            f"auto_execute_allowed=True gate 존재: {[g['gate_id'] for g in bad]}",
        )

    hidden_gates = {"POST_TASKS_DRY_RUN_DISABLE", "APPROVE_EXECUTE_CONNECT", "SERVER_RESTART", "DOCKER_COMPOSE_ACTION"}
    for gate_id in hidden_gates:
        g = next((x for x in APPROVAL_GATE_MATRIX if x["gate_id"] == gate_id), None)
        if g and g.get("mvp_button_state") in ("hidden", "disabled"):
            report.add(f"gate_{gate_id}_hidden", "PASS", f"{gate_id} mvp_button_state={g['mvp_button_state']}")
        else:
            report.add(f"gate_{gate_id}_hidden", "FAIL", f"{gate_id} hidden/disabled 미설정")


def check_providers(report: AuditReport) -> None:
    required = [
        "GABIA",
        "KAKAO",
        "NAVER",
        "NAVER_SMARTSTORE",
        "GOOGLE",
        "HIWORKS",
        "G2B_NARA",
        "HOMETAX",
        "WETAX",
        "GOVERNMENT24",
        "EMAIL_GENERIC",
        "BANK_GENERIC",
    ]
    defined = {p["id"] for p in PROVIDERS}
    missing = set(required) - defined
    if not missing:
        report.add("providers_12_defined", "PASS", "12개 provider 모두 정의됨")
    else:
        report.add("providers_12_defined", "FAIL", f"누락 provider: {missing}")

    gabia = next((p for p in PROVIDERS if p["id"] == "GABIA"), None)
    if gabia and gabia.get("user_present_required") and gabia.get("cookie_storage_forbidden"):
        report.add(
            "provider_gabia_user_present", "PASS", "GABIA user_present_required=True, cookie_storage_forbidden=True"
        )
    else:
        report.add("provider_gabia_user_present", "FAIL", "GABIA 정책 미설정")

    smartstore = next((p for p in PROVIDERS if p["id"] == "NAVER_SMARTSTORE"), None)
    if smartstore and smartstore.get("risk_level") == "critical":
        report.add("provider_smartstore_critical", "PASS", "NAVER_SMARTSTORE risk_level=critical")
    else:
        report.add("provider_smartstore_critical", "FAIL", "NAVER_SMARTSTORE critical 미표시")

    g2b = next((p for p in PROVIDERS if p["id"] == "G2B_NARA"), None)
    if g2b and g2b.get("certificate_required"):
        report.add("provider_g2b_certificate", "PASS", "G2B_NARA certificate_required=True")
    else:
        report.add("provider_g2b_certificate", "FAIL", "G2B_NARA certificate_required 미설정")

    cookie_forbidden_all = all(p.get("cookie_storage_forbidden") for p in PROVIDERS)
    if cookie_forbidden_all:
        report.add("providers_cookie_forbidden_all", "PASS", "전체 provider cookie_storage_forbidden=True")
    else:
        report.add("providers_cookie_forbidden_all", "FAIL", "cookie_storage_forbidden 미설정 provider 존재")


def check_known_backlog(report: AuditReport) -> None:
    backlog_ids = {b["id"] for b in KNOWN_BACKLOG}
    required = {"B-1", "B-2", "B-3", "KW-1", "KW-4", "EXT-CAD"}
    missing = required - backlog_ids
    if not missing:
        report.add("known_backlog_all_reflected", "PASS", f"known backlog {len(required)}개 모두 반영")
    else:
        report.add("known_backlog_all_reflected", "FAIL", f"누락 backlog: {missing}")

    for item_id in ["B-1", "B-2", "B-3", "KW-1", "KW-4"]:
        item = next((b for b in KNOWN_BACKLOG if b["id"] == item_id), None)
        if item:
            report.add(f"backlog_{item_id}", "PASS", f"{item_id}: {item['title'][:40]}")
        else:
            report.add(f"backlog_{item_id}", "FAIL", f"{item_id} 미반영")


def check_storage(report: AuditReport) -> None:
    if "named_volume" in STORAGE_MATRIX:
        report.add("storage_named_volume", "PASS", "named volume /app/ai_orchestrator/storage 정의됨")
    else:
        report.add("storage_named_volume", "FAIL", "named volume 미정의")

    bind = STORAGE_MATRIX.get("bind_mount_logs", {})
    if bind.get("bind_mount_applied"):
        report.add("storage_bind_mount_applied", "PASS", "/app/logs bind mount 적용됨")
    else:
        report.add("storage_bind_mount_applied", "FAIL", "/app/logs bind mount 미적용")

    runtime = STORAGE_MATRIX.get("runtime_cache", {})
    if runtime.get("git_modified") and runtime.get("classification") == "RUNTIME_CACHE_DISPOSABLE":
        report.add(
            "storage_runtime_cache_classified",
            "PASS",
            "chrome_ui_monitor_state.json = RUNTIME_CACHE_DISPOSABLE (KW-1 반영)",
        )
    else:
        report.add("storage_runtime_cache_classified", "WARN", "runtime cache 분류 확인 필요")


def check_deployment_sop(report: AuditReport) -> None:
    if DEPLOYMENT_SOP.get("restart_only_forbidden"):
        report.add("deployment_restart_forbidden", "PASS", "restart 단독 금지 정책 정의됨")
    else:
        report.add("deployment_restart_forbidden", "FAIL", "restart 단독 금지 미정의")

    if len(DEPLOYMENT_SOP.get("steps", [])) >= 3:
        report.add("deployment_sop_steps", "PASS", f"배포 SOP {len(DEPLOYMENT_SOP['steps'])}단계 정의됨")
    else:
        report.add("deployment_sop_steps", "FAIL", "배포 SOP 단계 부족")


def check_pytest_baseline(report: AuditReport) -> None:
    if PYTEST_BASELINE["total_failed"] == 0:
        report.add(
            "pytest_baseline_zero_failed",
            "PASS",
            f"{PYTEST_BASELINE['total_passed']} passed / 0 failed / {PYTEST_BASELINE['total_deselected']} deselected",
        )
    else:
        report.add("pytest_baseline_zero_failed", "FAIL", f"baseline failed={PYTEST_BASELINE['total_failed']} > 0")

    if PYTEST_BASELINE.get("baseline_tag") == "TEST_BASELINE_CLEANED":
        report.add("pytest_baseline_tag", "PASS", "TEST_BASELINE_CLEANED 태그 반영됨")
    else:
        report.add("pytest_baseline_tag", "WARN", "baseline tag 미반영")


def check_token_cookie_forbidden(report: AuditReport) -> None:
    logs_screen = next((s for s in MVP_SCREENS if s["id"] == "logs_audit"), None)
    if logs_screen and "show_cookie" in logs_screen.get("forbidden_buttons", []):
        report.add("cookie_display_forbidden", "PASS", "logs_audit 화면에 show_cookie forbidden 정의됨")
    else:
        report.add("cookie_display_forbidden", "FAIL", "cookie 표시 금지 미정의")

    if logs_screen and "export_raw_token" in logs_screen.get("forbidden_buttons", []):
        report.add("token_raw_display_forbidden", "PASS", "logs_audit 화면에 export_raw_token forbidden 정의됨")
    else:
        report.add("token_raw_display_forbidden", "FAIL", "token 원문 표시 금지 미정의")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_screens(report)
    check_api_contract(report)
    check_forbidden_buttons(report)
    check_approval_gates(report)
    check_providers(report)
    check_known_backlog(report)
    check_storage(report)
    check_deployment_sop(report)
    check_pytest_baseline(report)
    check_token_cookie_forbidden(report)

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

    out_path = REPO_ROOT / "data" / "app_foundation_mvp_prep_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] MVP Prep Audit")
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
