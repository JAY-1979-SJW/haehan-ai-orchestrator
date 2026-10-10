"""APP_API_CONTRACT_ENDPOINTS_PREP_01 감사 스크립트.

앱 MVP용 read-only endpoint 후보와 계약이 안전한지 검증한다.
실제 구현 공정이 아님 — 계약·schema·보안경계 확정 prep 공정.
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
AUDIT_ID = "APP_API_CONTRACT_ENDPOINTS_PREP"

IMPLEMENTATION_ALLOWED = False
FRONTEND_WIRING_ALLOWED = False
MUTATION_ENDPOINT_ALLOWED = False
SERVER_ACTION_ALLOWED = False

VERDICT_READY = "APP_API_CONTRACT_ENDPOINTS_PREP_READY"
VERDICT_WARN = "APP_API_CONTRACT_ENDPOINTS_PREP_WITH_WARN"
VERDICT_BLOCKED = "APP_API_CONTRACT_ENDPOINTS_PREP_BLOCKED"

# ── endpoint contract matrix ──────────────────────────────────────────────────

ENDPOINT_CONTRACT_MATRIX: list[dict[str, Any]] = [
    {
        "endpoint": "GET /api/v1/app/health/summary",
        "method": "GET",
        "category": "health",
        "priority": 1,
        "auth_required": False,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": False,
        "filters": [],
        "response_schema": {
            "ok": True,
            "data": {
                "status": "string",
                "service": "string",
                "version": "string",
                "dry_run_gate_enabled": "boolean",
                "container_health": "string",
                "phase1_closeout": "string",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {
            "ok": False,
            "error_code": "string",
            "message": "string",
            "detail_redacted": True,
        },
        "redaction_required": False,
        "sensitive_fields_forbidden": ["raw_token", "cookie", "password"],
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/providers",
        "method": "GET",
        "category": "external_sites",
        "priority": 1,
        "auth_required": False,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "max-age=300",
        "pagination": False,
        "filters": ["category", "status", "risk_level"],
        "response_schema": {
            "ok": True,
            "data": {
                "providers": [
                    {
                        "provider_id": "string",
                        "display_name": "string",
                        "category": "string",
                        "current_status": "string",
                        "risk_level": "string",
                        "user_present_login_required": "boolean",
                        "desktop_app_required": "boolean",
                        "cookie_storage_allowed": False,
                        "token_storage_allowed": False,
                        "approval_gate_required": "boolean",
                    }
                ],
                "total": "integer",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": False,
        "sensitive_fields_forbidden": ["raw_token", "cookie", "password", "session_secret"],
        "providers_count_required": 12,
        "cookie_storage_allowed": False,
        "token_storage_allowed": False,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/storage/status",
        "method": "GET",
        "category": "storage",
        "priority": 1,
        "auth_required": False,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": False,
        "filters": [],
        "response_schema": {
            "ok": True,
            "data": {
                "storage_paths": "list",
                "named_volume_status": "list",
                "bind_mount_status": "list",
                "app_logs_persistent": "boolean",
                "runtime_cache_status": "string",
                "approval_token_policy": "string",
                "execution_history_policy": "string",
                "audit_log_policy": "string",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": False,
        "sensitive_fields_forbidden": ["raw_token", "cookie", "password"],
        "schema_includes_bind_mount": True,
        "schema_includes_named_volume": True,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/logs/audit",
        "method": "GET",
        "category": "audit",
        "priority": 2,
        "auth_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": {"default_limit": 50, "max_limit": 200, "cursor": True},
        "filters": ["level", "category", "from_ts", "to_ts"],
        "response_schema": {
            "ok": True,
            "data": {
                "items": [
                    {
                        "id": "string",
                        "timestamp": "string",
                        "category": "string",
                        "action": "string",
                        "actor_type": "string",
                        "risk_level": "string",
                        "status": "string",
                        "summary": "string",
                        "redacted": True,
                    }
                ],
                "total": "integer",
                "cursor": "string | null",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": True,
        "sensitive_fields_forbidden": [
            "raw_token",
            "access_token",
            "refresh_token",
            "cookie",
            "session_secret",
            "password",
            "approval_token_raw",
            "private_key",
        ],
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/tasks",
        "method": "GET",
        "category": "task_queue",
        "priority": 2,
        "auth_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": {"default_limit": 50, "max_limit": 200, "cursor": True},
        "filters": ["status", "risk_level", "dry_run", "provider"],
        "response_schema": {
            "ok": True,
            "data": {
                "tasks": [
                    {
                        "task_id": "string",
                        "source": "string",
                        "action_type": "string",
                        "risk_level": "string",
                        "status": "string",
                        "dry_run": "boolean",
                        "allowed": "boolean",
                        "requires_approval": "boolean",
                        "approval_token_present": "boolean",
                        "approval_token_id": "string | null (redacted)",
                        "created_at": "string",
                        "updated_at": "string",
                        "summary": "string",
                    }
                ],
                "total": "integer",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": True,
        "sensitive_fields_forbidden": [
            "approval_token_raw",
            "raw_token",
            "cookie",
            "password",
            "execute_url",
            "approve_action_url",
        ],
        "approval_token_raw_forbidden": True,
        "execute_url_forbidden": True,
        "approval_token_present_boolean_only": True,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/deployment/status",
        "method": "GET",
        "category": "deployment",
        "priority": 3,
        "auth_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": False,
        "filters": [],
        "response_schema": {
            "ok": True,
            "data": {
                "server_head": "string",
                "origin_head": "string",
                "sync_status": "string",
                "build_required": "boolean",
                "container_health": "string",
                "deployment_sop": "list[string]",
                "server_apply_allowed": False,
                "restart_allowed": False,
                "docker_compose_allowed": False,
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": False,
        "sensitive_fields_forbidden": ["raw_token", "cookie", "password"],
        "restart_allowed": False,
        "docker_compose_allowed": False,
        "server_apply_allowed": False,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_REQUIRED",
    },
    {
        "endpoint": "GET /api/v1/app/known-backlog",
        "method": "GET",
        "category": "backlog",
        "priority": 3,
        "auth_required": False,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "max-age=60",
        "pagination": False,
        "filters": [],
        "response_schema": {
            "ok": True,
            "data": {"items": "list", "total": "integer"},
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": False,
        "sensitive_fields_forbidden": ["raw_token", "cookie", "password"],
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_OPTIONAL",
    },
    {
        "endpoint": "GET /api/v1/app/gates",
        "method": "GET",
        "category": "approval_gate",
        "priority": 3,
        "auth_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "implementation_allowed_now": False,
        "frontend_wiring_allowed_now": False,
        "cache_policy": "no-store",
        "pagination": False,
        "filters": ["risk_level", "state"],
        "response_schema": {
            "ok": True,
            "data": {
                "gates": [
                    {
                        "gate_id": "string",
                        "risk_level": "string",
                        "user_approval_required": "boolean",
                        "auto_execute_allowed": False,
                        "evidence_required": "boolean",
                        "state": "string",
                        "current_behavior": "string",
                    }
                ],
                "total": "integer",
            },
            "meta": {"source": "string", "generated_at": "string"},
        },
        "error_schema": {"ok": False, "error_code": "string", "message": "string", "detail_redacted": True},
        "redaction_required": False,
        "sensitive_fields_forbidden": ["approval_token_raw", "raw_token", "cookie", "password"],
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "status": "FUTURE_ENDPOINT_OPTIONAL",
    },
]

# ── forbidden endpoint matrix ─────────────────────────────────────────────────

FORBIDDEN_ENDPOINT_MATRIX = [
    {"endpoint": "POST /api/v1/app/tasks", "reason": "task 실행 금지"},
    {"endpoint": "POST /api/v1/app/tasks/{id}/execute", "reason": "execute 금지"},
    {"endpoint": "POST /api/v1/app/tasks/{id}/approve", "reason": "approve→execute 금지"},
    {"endpoint": "POST /api/v1/app/tasks/{id}/reject", "reason": "reject 금지"},
    {"endpoint": "POST /api/v1/app/deploy", "reason": "배포 trigger 금지"},
    {"endpoint": "POST /api/v1/app/restart", "reason": "서버 재시작 금지"},
    {"endpoint": "POST /api/v1/app/docker-compose", "reason": "docker compose 조작 금지"},
    {"endpoint": "POST /api/v1/app/external-sites/{id}/submit", "reason": "외부 사이트 submit 금지"},
    {"endpoint": "POST /api/v1/app/dns/save", "reason": "DNS 저장 금지"},
    {"endpoint": "POST /api/v1/app/payment", "reason": "결제 금지"},
    {"endpoint": "POST /api/v1/app/execute", "reason": "실행 금지"},
    {"endpoint": "POST /api/v1/inbox/email/fetch", "reason": "inbox fetch mutation 금지"},
    {"endpoint": "DELETE /api/v1/app/tasks/{id}", "reason": "task 삭제 금지"},
    {"endpoint": "PUT /api/v1/app/tasks/{id}", "reason": "task 수정 금지"},
]

# ── redaction policy matrix ────────────────────────────────────────────────────

REDACTION_POLICY_MATRIX = [
    {"field": "raw_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "access_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "refresh_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "cookie", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "session_secret", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "password", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "approval_token_raw", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "private_key", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "certificate_password", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all endpoints"},
    {"field": "approval_token_id", "policy": "REDACTED_OR_NULL", "applies_to": "tasks endpoint"},
    {"field": "audit_log_payload", "policy": "REDACTED_SUMMARY_ONLY", "applies_to": "audit logs endpoint"},
    {"field": "execute_url", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "tasks endpoint"},
    {"field": "approve_action_url", "policy": "FORBIDDEN_AS_ACTION", "applies_to": "tasks endpoint"},
]

# ── priority matrix ─────────────────────────────────────────────────────────────

PRIORITY_MATRIX = {
    1: {
        "endpoints": [
            "GET /api/v1/app/health/summary",
            "GET /api/v1/app/providers",
            "GET /api/v1/app/storage/status",
        ],
        "reason": "mutation 위험 낮음, UI 상태 카드에 즉시 유용",
    },
    2: {
        "endpoints": [
            "GET /api/v1/app/logs/audit",
            "GET /api/v1/app/tasks",
        ],
        "reason": "redaction/pagination 필요, 보안 설계 주의",
    },
    3: {
        "endpoints": [
            "GET /api/v1/app/deployment/status",
            "GET /api/v1/app/known-backlog",
            "GET /api/v1/app/gates",
        ],
        "reason": "deployment는 server action 오해 방지 위해 보수적 진행",
    },
}

# ── next phase matrix ──────────────────────────────────────────────────────────

NEXT_PHASE_MATRIX = [
    {
        "phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
        "triggers": ["PREP_READY"],
        "scope": "Priority 1 endpoint 설계·구현 계획",
    },
    {
        "phase": "APP_TASK_QUEUE_READONLY_LIST_POLISH_01",
        "triggers": ["GET /api/v1/app/tasks 구현 완료"],
        "scope": "Task Queue UI task list 연결",
    },
    {
        "phase": "APP_DESKTOP_AGENT_FOUNDATION_PREP_01",
        "triggers": ["PREP_READY"],
        "scope": "데스크톱 에이전트 기반 구조 준비",
    },
]

PROVIDERS_REQUIRED = [
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


# ── audit logic ────────────────────────────────────────────────────────────────


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


def check_global_flags(report: AuditReport) -> None:
    for flag, val, name in [
        (IMPLEMENTATION_ALLOWED, False, "implementation_allowed=false"),
        (FRONTEND_WIRING_ALLOWED, False, "frontend_wiring_allowed=false"),
        (MUTATION_ENDPOINT_ALLOWED, False, "mutation_endpoint_allowed=false"),
        (SERVER_ACTION_ALLOWED, False, "server_action_allowed=false"),
    ]:
        if flag == val:
            report.add(f"flag_{name.replace('=', '_').replace('.', '_')}", "PASS", name)
        else:
            report.add(f"flag_{name.replace('=', '_').replace('.', '_')}", "FAIL", f"{name} 위반 — 값={flag}")


def _check_endpoint_count(endpoints: list[str], report: AuditReport) -> None:
    if len(endpoints) >= 5:
        report.add("endpoint_count_5plus", "PASS", f"endpoint {len(endpoints)}개 정의")
    else:
        report.add("endpoint_count_5plus", "FAIL", f"endpoint {len(endpoints)}개 — 5개 미만")


def _check_required_endpoints_present(endpoints: list[str], report: AuditReport) -> None:
    required_endpoints = [
        "GET /api/v1/app/health/summary",
        "GET /api/v1/app/providers",
        "GET /api/v1/app/storage/status",
        "GET /api/v1/app/logs/audit",
        "GET /api/v1/app/tasks",
        "GET /api/v1/app/deployment/status",
    ]
    endpoint_set = set(endpoints)
    for req in required_endpoints:
        slug = req.replace("/", "_").replace(" ", "_").lower()
        if req in endpoint_set:
            report.add(f"endpoint_{slug[:50]}", "PASS", f"{req} 존재")
        else:
            report.add(f"endpoint_{slug[:50]}", "FAIL", f"{req} 없음")


def _check_all_endpoints_get(report: AuditReport) -> None:
    non_get = [e["endpoint"] for e in ENDPOINT_CONTRACT_MATRIX if e.get("method") != "GET"]
    if not non_get:
        report.add("all_endpoints_get", "PASS", "모든 endpoint method=GET")
    else:
        report.add("all_endpoints_get", "FAIL", f"GET 아닌 endpoint: {non_get}")


def _check_endpoint_flag_all_false(report: AuditReport, attr: str, check_name: str, pass_msg: str) -> None:
    """mutation_allowed/side_effect_allowed/implementation_allowed_now/frontend_wiring_allowed_now
    전부 False 여야 하는 4개 검사가 같은 모양이라 하나로 묶었다(2026-09-29 STD-08 분리)."""
    violations = [e["endpoint"] for e in ENDPOINT_CONTRACT_MATRIX if e.get(attr) is not False]
    if not violations:
        report.add(check_name, "PASS", pass_msg)
    else:
        report.add(check_name, "FAIL", f"{attr} 위반: {violations}")


def check_endpoint_matrix(report: AuditReport) -> None:
    endpoints = [e["endpoint"] for e in ENDPOINT_CONTRACT_MATRIX]
    _check_endpoint_count(endpoints, report)
    _check_required_endpoints_present(endpoints, report)
    _check_all_endpoints_get(report)
    _check_endpoint_flag_all_false(
        report, "mutation_allowed", "all_mutation_allowed_false", "전체 mutation_allowed=false"
    )
    _check_endpoint_flag_all_false(
        report, "side_effect_allowed", "all_side_effect_false", "전체 side_effect_allowed=false"
    )
    _check_endpoint_flag_all_false(
        report, "implementation_allowed_now", "all_impl_not_allowed", "전체 implementation_allowed_now=false"
    )
    _check_endpoint_flag_all_false(
        report, "frontend_wiring_allowed_now", "all_wiring_not_allowed", "전체 frontend_wiring_allowed_now=false"
    )


def check_forbidden_matrix(report: AuditReport) -> None:
    if len(FORBIDDEN_ENDPOINT_MATRIX) > 0:
        report.add("forbidden_matrix_exists", "PASS", f"forbidden endpoint {len(FORBIDDEN_ENDPOINT_MATRIX)}개 정의")
    else:
        report.add("forbidden_matrix_exists", "FAIL", "forbidden endpoint matrix 없음")

    required_forbidden = [
        "POST /api/v1/app/tasks",
        "POST /api/v1/app/deploy",
        "POST /api/v1/app/restart",
        "POST /api/v1/app/execute",
    ]
    forbidden_endpoints = {e["endpoint"] for e in FORBIDDEN_ENDPOINT_MATRIX}
    for req in required_forbidden:
        if req in forbidden_endpoints:
            report.add(
                f"forbidden_{req.replace('/', '_').replace(' ', '_').lower()[:50]}", "PASS", f"{req} forbidden 등록"
            )
        else:
            report.add(
                f"forbidden_{req.replace('/', '_').replace(' ', '_').lower()[:50]}", "FAIL", f"{req} forbidden 미등록"
            )


def check_redaction_policy(report: AuditReport) -> None:
    required_fields = [
        "raw_token",
        "access_token",
        "refresh_token",
        "cookie",
        "session_secret",
        "password",
        "approval_token_raw",
    ]
    redaction_fields = {r["field"] for r in REDACTION_POLICY_MATRIX}
    for field in required_fields:
        if field in redaction_fields:
            report.add(f"redaction_{field}", "PASS", f"{field} redaction 정책 존재")
        else:
            report.add(f"redaction_{field}", "FAIL", f"{field} redaction 정책 없음")

    # execute_url forbidden
    execute_url_entry = next((r for r in REDACTION_POLICY_MATRIX if r["field"] == "execute_url"), None)
    if execute_url_entry:
        report.add("redaction_execute_url", "PASS", "execute_url FORBIDDEN_IN_RESPONSE")
    else:
        report.add("redaction_execute_url", "FAIL", "execute_url redaction 정책 없음")


def check_providers_schema(report: AuditReport) -> None:
    provider_ep = next((e for e in ENDPOINT_CONTRACT_MATRIX if "providers" in e["endpoint"]), None)
    if not provider_ep:
        report.add("providers_schema", "FAIL", "providers endpoint 없음")
        return

    if provider_ep.get("providers_count_required", 0) == 12:
        report.add("providers_12", "PASS", "providers 12개 요구")
    else:
        report.add("providers_12", "FAIL", "providers 12개 요구 미설정")

    if provider_ep.get("cookie_storage_allowed") is False:
        report.add("providers_cookie_forbidden", "PASS", "cookie_storage_allowed=false")
    else:
        report.add("providers_cookie_forbidden", "FAIL", "cookie_storage_allowed 설정 누락")

    if provider_ep.get("token_storage_allowed") is False:
        report.add("providers_token_forbidden", "PASS", "token_storage_allowed=false")
    else:
        report.add("providers_token_forbidden", "FAIL", "token_storage_allowed 설정 누락")


def check_storage_schema(report: AuditReport) -> None:
    storage_ep = next((e for e in ENDPOINT_CONTRACT_MATRIX if "storage" in e["endpoint"]), None)
    if not storage_ep:
        report.add("storage_schema", "FAIL", "storage endpoint 없음")
        return
    if storage_ep.get("schema_includes_bind_mount"):
        report.add("storage_bind_mount", "PASS", "bind_mount 반영")
    else:
        report.add("storage_bind_mount", "FAIL", "bind_mount 미반영")
    if storage_ep.get("schema_includes_named_volume"):
        report.add("storage_named_volume", "PASS", "named_volume 반영")
    else:
        report.add("storage_named_volume", "FAIL", "named_volume 미반영")


def check_deployment_schema(report: AuditReport) -> None:
    deploy_ep = next((e for e in ENDPOINT_CONTRACT_MATRIX if "deployment" in e["endpoint"]), None)
    if not deploy_ep:
        report.add("deployment_schema", "FAIL", "deployment endpoint 없음")
        return
    for flag in ["restart_allowed", "docker_compose_allowed", "server_apply_allowed"]:
        if deploy_ep.get(flag) is False:
            report.add(f"deployment_{flag}_false", "PASS", f"{flag}=false")
        else:
            report.add(f"deployment_{flag}_false", "FAIL", f"{flag} 설정 누락")


def check_task_schema(report: AuditReport) -> None:
    task_ep = next((e for e in ENDPOINT_CONTRACT_MATRIX if e["endpoint"] == "GET /api/v1/app/tasks"), None)
    if not task_ep:
        report.add("task_schema", "FAIL", "tasks endpoint 없음")
        return
    if task_ep.get("approval_token_raw_forbidden"):
        report.add("task_token_raw_forbidden", "PASS", "approval_token_raw forbidden")
    else:
        report.add("task_token_raw_forbidden", "FAIL", "approval_token_raw forbidden 미설정")
    if task_ep.get("execute_url_forbidden"):
        report.add("task_execute_url_forbidden", "PASS", "execute_url forbidden")
    else:
        report.add("task_execute_url_forbidden", "FAIL", "execute_url forbidden 미설정")
    if task_ep.get("approval_token_present_boolean_only"):
        report.add("task_token_boolean_only", "PASS", "approval_token_present=boolean only")
    else:
        report.add("task_token_boolean_only", "FAIL", "approval_token_present boolean only 미설정")


def check_audit_logs_redaction(report: AuditReport) -> None:
    audit_ep = next((e for e in ENDPOINT_CONTRACT_MATRIX if "logs/audit" in e["endpoint"]), None)
    if not audit_ep:
        report.add("audit_logs_schema", "FAIL", "audit logs endpoint 없음")
        return
    if audit_ep.get("redaction_required"):
        report.add("audit_logs_redaction_required", "PASS", "audit logs redaction_required=true")
    else:
        report.add("audit_logs_redaction_required", "FAIL", "audit logs redaction_required 미설정")


def check_priority_matrix(report: AuditReport) -> None:
    if len(PRIORITY_MATRIX) >= 3:
        report.add("priority_matrix_exists", "PASS", f"priority matrix {len(PRIORITY_MATRIX)}단계 정의")
    else:
        report.add("priority_matrix_exists", "FAIL", "priority matrix 없음")

    priority1_eps = PRIORITY_MATRIX.get(1, {}).get("endpoints", [])
    required_p1 = ["GET /api/v1/app/health/summary", "GET /api/v1/app/providers", "GET /api/v1/app/storage/status"]
    for ep in required_p1:
        if ep in priority1_eps:
            report.add(
                f"p1_{ep.replace('/', '_').replace(' ', '_').lower()[:40]}",
                "PASS",
                f"Priority 1에 {ep.split('/')[-1]} 포함",
            )
        else:
            report.add(f"p1_{ep.replace('/', '_').replace(' ', '_').lower()[:40]}", "WARN", f"Priority 1에 {ep} 미포함")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_global_flags(report)
    check_endpoint_matrix(report)
    check_forbidden_matrix(report)
    check_redaction_policy(report)
    check_providers_schema(report)
    check_storage_schema(report)
    check_deployment_schema(report)
    check_task_schema(report)
    check_audit_logs_redaction(report)
    check_priority_matrix(report)

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

    out_path = REPO_ROOT / "data" / "app_api_contract_endpoints_prep_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] API Contract Endpoints Prep Audit")
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
