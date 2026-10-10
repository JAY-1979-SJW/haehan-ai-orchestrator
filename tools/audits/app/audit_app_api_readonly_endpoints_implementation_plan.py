"""APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01 감사 스크립트.

Priority 1 read-only endpoint 3개의 구현 계획이 안전한지 검증한다.
실제 구현 없음 — 시공계획서 단계.
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
AUDIT_ID = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN"

IMPLEMENTATION_ALLOWED = False
ROUTER_MODIFICATION_ALLOWED = False
FRONTEND_WIRING_ALLOWED = False
MUTATION_ENDPOINT_ALLOWED = False
SERVER_ACTION_ALLOWED = False

VERDICT_READY = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_READY"
VERDICT_WARN = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_WITH_WARN"
VERDICT_BLOCKED = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_BLOCKED"

# ── router location plan ──────────────────────────────────────────────────────
# router.py 정적 분석 결과:
# - ai_orchestrator/routers/registry.py: 311줄, prefix=/api/v1, 이미 9개 sub-router include
# - 추가 app status route를 직접 router.py에 넣으면 누적 비대화 위험
# → 별도 thin router 파일 신설 권장

ROUTER_LOCATION_PLAN = {
    "selected_router_file": "ai_orchestrator/routers/app_status_router.py",
    "selected_reason": (
        "router.py(311줄)가 이미 9개 sub-router를 include. "
        "app status(health/providers/storage) read-only route를 별도 thin router로 분리해 "
        "단일 책임 원칙 유지. router.py에는 include_router 1줄만 추가."
    ),
    "alternative_router_files": [
        "ai_orchestrator/routers/registry.py (직접 추가 — 권장 안 함, 파일 비대화)",
        "ai_orchestrator/routers/admin_ui_router.py (기존 admin UI route 파일 — 역할 혼합 비권장)",
    ],
    "import_dependencies": [
        "fastapi.APIRouter",
        "ai_orchestrator.core.config (dry_run_gate_enabled 등)",
        "ai_orchestrator.storage_policy (storage path/policy)",
        "ai_orchestrator.external_sites.canonical_provider_registry (providers)",
    ],
    "read_only_guard_needed": True,
    "router_modification_allowed_now": False,
    "implementation_risk": "LOW — read-only GET, no DB write, no external call",
}

# ── priority1 endpoint plan matrix ───────────────────────────────────────────

PRIORITY1_ENDPOINT_PLAN_MATRIX: list[dict[str, Any]] = [
    {
        "endpoint": "GET /api/v1/app/health/summary",
        "method": "GET",
        "priority": 1,
        "implementation_allowed_now": False,
        "selected_router_file": "ai_orchestrator/routers/app_status_router.py",
        "response_schema_frozen": True,
        "response_schema": {
            "ok": True,
            "data": {
                "service": "string",
                "health_status": "string",
                "server_head": "string",
                "origin_head": "string",
                "sync_status": "string",
                "post_tasks_dry_run_enabled": "boolean",
                "phase1_closeout_status": "string",
                "container_health_source": "string",
                "generated_at": "string",
            },
            "meta": {
                "source": "string",
                "read_only": True,
                "mutation_allowed": False,
            },
        },
        "redaction_required": True,
        "redacted_fields": ["env_secret_values", "git_remote_token", "server_private_ip_if_sensitive"],
        "forbidden_response_fields": [
            "restart_allowed=true",
            "docker_compose_allowed=true",
            "raw_token",
            "cookie",
            "password",
        ],
        "read_only_guard_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "server_action_allowed": False,
        "db_write_allowed": False,
        "external_http_call_allowed": False,
        "secret_value_output_allowed": False,
        "implementation_order": 1,
        "tests_required": True,
        "smoke_required": True,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01",
        "verdict": "PLAN_READY",
    },
    {
        "endpoint": "GET /api/v1/app/providers",
        "method": "GET",
        "priority": 1,
        "implementation_allowed_now": False,
        "selected_router_file": "ai_orchestrator/routers/app_status_router.py",
        "response_schema_frozen": True,
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
                        "automation_status": "string",
                    }
                ],
            },
            "meta": {
                "provider_count": "integer",
                "read_only": True,
                "mutation_allowed": False,
            },
        },
        "redaction_required": False,
        "redacted_fields": ["login_credential", "cookie_value", "token_value"],
        "forbidden_response_fields": ["login_password", "session_cookie", "access_token", "raw_token"],
        "read_only_guard_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "server_action_allowed": False,
        "db_write_allowed": False,
        "external_http_call_allowed": False,
        "secret_value_output_allowed": False,
        "provider_count_required": 12,
        "cookie_storage_allowed_all": False,
        "implementation_order": 2,
        "tests_required": True,
        "smoke_required": True,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01",
        "verdict": "PLAN_READY",
    },
    {
        "endpoint": "GET /api/v1/app/storage/status",
        "method": "GET",
        "priority": 1,
        "implementation_allowed_now": False,
        "selected_router_file": "ai_orchestrator/routers/app_status_router.py",
        "response_schema_frozen": True,
        "response_schema": {
            "ok": True,
            "data": {
                "storage_paths": "list[string]",
                "named_volume_status": {
                    "ai_orchestrator_storage": "string",
                    "description": "/app/ai_orchestrator/storage named volume",
                },
                "app_logs_bind_mount_status": {
                    "host_path": "string (path only)",
                    "container_path": "/app/logs",
                    "persistent": "boolean",
                },
                "app_logs_path": "string",
                "storage_path": "string",
                "audit_log_policy": "string",
                "execution_history_policy": "string",
                "approval_token_policy": "string",
                "runtime_cache_policy": "DISPOSABLE",
            },
            "meta": {
                "read_only": True,
                "mutation_allowed": False,
            },
        },
        "redaction_required": True,
        "redacted_fields": ["file_contents", "approval_token_raw", "log_raw_content"],
        "forbidden_response_fields": ["approval_token_raw", "file_content", "raw_token", "password"],
        "read_only_guard_required": True,
        "mutation_allowed": False,
        "side_effect_allowed": False,
        "server_action_allowed": False,
        "db_write_allowed": False,
        "external_http_call_allowed": False,
        "secret_value_output_allowed": False,
        "schema_includes_named_volume": True,
        "schema_includes_bind_mount": True,
        "schema_includes_approval_token_policy": True,
        "runtime_cache_policy": "DISPOSABLE",
        "implementation_order": 3,
        "tests_required": True,
        "smoke_required": True,
        "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01",
        "verdict": "PLAN_READY",
    },
]

# ── response schema matrix (frozen) ─────────────────────────────────────────

RESPONSE_SCHEMA_MATRIX = {ep["endpoint"]: ep["response_schema"] for ep in PRIORITY1_ENDPOINT_PLAN_MATRIX}

# ── redaction policy matrix ────────────────────────────────────────────────────

REDACTION_POLICY_MATRIX = [
    {"field": "raw_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "access_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "refresh_token", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "cookie", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "session_secret", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "password", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "approval_token_raw", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "private_key", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "secret_value", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "all"},
    {"field": "env_secret_value", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "health"},
    {"field": "git_remote_token", "policy": "REDACTED_OR_OMITTED", "applies_to": "health"},
    {"field": "file_content", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "storage"},
    {"field": "log_raw_content", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "storage"},
    {"field": "login_credential", "policy": "FORBIDDEN_IN_RESPONSE", "applies_to": "providers"},
]

# ── read_only guard matrix ─────────────────────────────────────────────────────

READ_ONLY_GUARD_MATRIX = {
    "method": "GET",
    "mutation_allowed": False,
    "side_effect_allowed": False,
    "db_write_allowed": False,
    "external_http_call_allowed": False,
    "server_action_allowed": False,
    "docker_action_allowed": False,
    "secret_value_output_allowed": False,
    "common_response_meta": {
        "read_only": True,
        "mutation_allowed": False,
        "generated_at": "ISO8601",
        "source": "string",
    },
}

# ── implementation order matrix ───────────────────────────────────────────────

IMPLEMENTATION_ORDER_MATRIX = [
    {
        "order": 1,
        "endpoint": "GET /api/v1/app/health/summary",
        "reason": "기존 GET /health 확장, 의존성 최소, mutation 위험 없음",
        "preconditions": ["app_status_router.py 신설", "read-only guard decorator 확인"],
        "tests_required": [
            "test_health_summary_returns_ok",
            "test_health_no_secret_in_response",
            "test_health_dry_run_enabled_present",
        ],
    },
    {
        "order": 2,
        "endpoint": "GET /api/v1/app/providers",
        "reason": "canonical_provider_registry import 기반, 12개 provider 확인 용이",
        "preconditions": ["app_status_router.py 존재", "canonical_provider_registry import 확인"],
        "tests_required": ["test_providers_12_count", "test_providers_no_cookie", "test_providers_no_token"],
    },
    {
        "order": 3,
        "endpoint": "GET /api/v1/app/storage/status",
        "reason": "storage path/policy는 config 기반, DB read 없음, 가장 단순한 정적 응답 가능",
        "preconditions": ["app_status_router.py 존재", "storage path config 확인"],
        "tests_required": [
            "test_storage_named_volume_present",
            "test_storage_bind_mount_present",
            "test_storage_approval_token_policy_present",
            "test_storage_no_file_content",
        ],
    },
]

# ── next phase readiness ───────────────────────────────────────────────────────

NEXT_PHASE_READINESS = {
    "current_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_PLAN_01",
    "next_phase": "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01",
    "readiness_conditions": [
        "PLAN_READY verdict",
        "router 위치 확정 (app_status_router.py)",
        "response schema frozen",
        "redaction policy 확정",
        "implementation order 확정",
        "tests_required 목록 확정",
    ],
    "blocked_until": [
        "IMPLEMENTATION_ALLOWED=True 승인",
        "ROUTER_MODIFICATION_ALLOWED=True 승인",
    ],
    "alternative_next": "APP_UI_READONLY_BACKEND_STATUS_CARDS_API_BIND_01",
}


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
        (IMPLEMENTATION_ALLOWED, False, "implementation_allowed"),
        (ROUTER_MODIFICATION_ALLOWED, False, "router_modification_allowed"),
        (FRONTEND_WIRING_ALLOWED, False, "frontend_wiring_allowed"),
        (MUTATION_ENDPOINT_ALLOWED, False, "mutation_endpoint_allowed"),
        (SERVER_ACTION_ALLOWED, False, "server_action_allowed"),
    ]:
        if flag == val:
            report.add(f"flag_{name}_false", "PASS", f"{name}=false 확인")
        else:
            report.add(f"flag_{name}_false", "FAIL", f"{name} 위반 — 값={flag}")


def check_priority1_plan(report: AuditReport) -> None:
    if len(PRIORITY1_ENDPOINT_PLAN_MATRIX) == 3:
        report.add("priority1_plan_3_endpoints", "PASS", "Priority 1 endpoint 3개 계획")
    else:
        report.add(
            "priority1_plan_3_endpoints", "FAIL", f"Priority 1 {len(PRIORITY1_ENDPOINT_PLAN_MATRIX)}개 — 3개 필요"
        )

    required = [
        "GET /api/v1/app/health/summary",
        "GET /api/v1/app/providers",
        "GET /api/v1/app/storage/status",
    ]
    eps = {e["endpoint"] for e in PRIORITY1_ENDPOINT_PLAN_MATRIX}
    for req in required:
        slug = req.replace("/", "_").replace(" ", "_").lower()
        if req in eps:
            report.add(f"plan_{slug[:50]}", "PASS", f"{req} plan 존재")
        else:
            report.add(f"plan_{slug[:50]}", "FAIL", f"{req} plan 없음")

    for ep in PRIORITY1_ENDPOINT_PLAN_MATRIX:
        _check_priority1_endpoint(report, ep)


def _check_priority1_endpoint(report: AuditReport, ep: dict) -> None:
    name = ep["endpoint"].split("/")[-1]
    if ep.get("method") != "GET":
        report.add(f"method_get_{name}", "FAIL", f"{ep['endpoint']} method != GET")
    else:
        report.add(f"method_get_{name}", "PASS", f"{ep['endpoint']} method=GET")

    if ep.get("priority") == 1:
        report.add(f"priority1_{name}", "PASS", f"{ep['endpoint']} priority=1")
    else:
        report.add(f"priority1_{name}", "FAIL", f"{ep['endpoint']} priority != 1")

    for flag in ["mutation_allowed", "side_effect_allowed", "server_action_allowed"]:
        if ep.get(flag) is False:
            report.add(f"{flag}_{name}", "PASS", f"{ep['endpoint']} {flag}=false")
        else:
            report.add(f"{flag}_{name}", "FAIL", f"{ep['endpoint']} {flag} 위반")

    _check_priority1_endpoint_gates(report, ep, name)


def _check_priority1_endpoint_gates(report: AuditReport, ep: dict, name: str) -> None:
    if ep.get("implementation_allowed_now") is False:
        report.add(f"impl_not_allowed_{name}", "PASS", f"{ep['endpoint']} implementation_allowed_now=false")
    else:
        report.add(f"impl_not_allowed_{name}", "FAIL", f"{ep['endpoint']} implementation_allowed_now 위반")

    if ep.get("response_schema_frozen"):
        report.add(f"schema_frozen_{name}", "PASS", f"{ep['endpoint']} response_schema_frozen=true")
    else:
        report.add(f"schema_frozen_{name}", "FAIL", f"{ep['endpoint']} schema 미확정")

    if ep.get("read_only_guard_required"):
        report.add(f"guard_{name}", "PASS", f"{ep['endpoint']} read_only_guard_required=true")
    else:
        report.add(f"guard_{name}", "WARN", f"{ep['endpoint']} read_only_guard_required 미설정")


def check_router_location(report: AuditReport) -> None:
    if ROUTER_LOCATION_PLAN.get("selected_router_file"):
        report.add("router_location_selected", "PASS", f"selected: {ROUTER_LOCATION_PLAN['selected_router_file']}")
    else:
        report.add("router_location_selected", "FAIL", "router location 미선택")

    if ROUTER_LOCATION_PLAN.get("router_modification_allowed_now") is False:
        report.add("router_modification_not_allowed_now", "PASS", "router 수정 금지 확인")
    else:
        report.add("router_modification_not_allowed_now", "FAIL", "router 수정 금지 위반")


def check_health_schema(report: AuditReport) -> None:
    health_ep = next((e for e in PRIORITY1_ENDPOINT_PLAN_MATRIX if "health" in e["endpoint"]), None)
    if not health_ep:
        report.add("health_schema", "FAIL", "health endpoint plan 없음")
        return
    schema_data = health_ep["response_schema"].get("data", {})
    if "post_tasks_dry_run_enabled" in schema_data:
        report.add("health_dry_run_field", "PASS", "health schema: post_tasks_dry_run_enabled 포함")
    else:
        report.add("health_dry_run_field", "FAIL", "health schema: post_tasks_dry_run_enabled 없음")

    forbidden = health_ep.get("forbidden_response_fields", [])
    if any("restart_allowed=true" in f for f in forbidden):
        report.add("health_no_restart_true", "PASS", "health schema: restart_allowed=true 금지")
    else:
        report.add("health_no_restart_true", "WARN", "health schema: restart_allowed 금지 명시 미확인")


def check_providers_schema(report: AuditReport) -> None:
    prov_ep = next((e for e in PRIORITY1_ENDPOINT_PLAN_MATRIX if "providers" in e["endpoint"]), None)
    if not prov_ep:
        report.add("providers_schema", "FAIL", "providers endpoint plan 없음")
        return
    if prov_ep.get("provider_count_required") == 12:
        report.add("providers_12", "PASS", "providers 12개 요구")
    else:
        report.add("providers_12", "FAIL", "providers 12개 요구 미설정")
    if prov_ep.get("cookie_storage_allowed_all") is False:
        report.add("providers_cookie_false", "PASS", "cookie_storage_allowed_all=false")
    else:
        report.add("providers_cookie_false", "FAIL", "cookie_storage_allowed_all 미설정")


def check_storage_schema(report: AuditReport) -> None:
    stor_ep = next((e for e in PRIORITY1_ENDPOINT_PLAN_MATRIX if "storage" in e["endpoint"]), None)
    if not stor_ep:
        report.add("storage_schema", "FAIL", "storage endpoint plan 없음")
        return
    for flag, label in [
        ("schema_includes_named_volume", "named volume 반영"),
        ("schema_includes_bind_mount", "bind mount 반영"),
        ("schema_includes_approval_token_policy", "approval token policy 반영"),
    ]:
        if stor_ep.get(flag):
            report.add(f"storage_{flag}", "PASS", f"storage schema: {label}")
        else:
            report.add(f"storage_{flag}", "FAIL", f"storage schema: {label} 미확인")
    if stor_ep.get("runtime_cache_policy") == "DISPOSABLE":
        report.add("storage_runtime_disposable", "PASS", "runtime_cache_policy=DISPOSABLE")
    else:
        report.add("storage_runtime_disposable", "WARN", "runtime_cache_policy 미설정")


def check_redaction_policy(report: AuditReport) -> None:
    required = ["raw_token", "access_token", "cookie", "password", "approval_token_raw", "secret_value"]
    fields = {r["field"] for r in REDACTION_POLICY_MATRIX}
    for f in required:
        if f in fields:
            report.add(f"redaction_{f}", "PASS", f"{f} redaction 정책 존재")
        else:
            report.add(f"redaction_{f}", "FAIL", f"{f} redaction 정책 없음")


def check_read_only_guard(report: AuditReport) -> None:
    for flag in [
        "mutation_allowed",
        "side_effect_allowed",
        "server_action_allowed",
        "db_write_allowed",
        "secret_value_output_allowed",
    ]:
        if READ_ONLY_GUARD_MATRIX.get(flag) is False:
            report.add(f"guard_{flag}_false", "PASS", f"guard: {flag}=false")
        else:
            report.add(f"guard_{flag}_false", "FAIL", f"guard: {flag} 위반")


def check_implementation_order(report: AuditReport) -> None:
    if len(IMPLEMENTATION_ORDER_MATRIX) == 3:
        report.add("impl_order_3", "PASS", "구현 순서 3단계 정의")
    else:
        report.add("impl_order_3", "FAIL", "구현 순서 미완")

    for expected_order, expected_endpoint in [
        (1, "GET /api/v1/app/health/summary"),
        (2, "GET /api/v1/app/providers"),
        (3, "GET /api/v1/app/storage/status"),
    ]:
        entry = next((e for e in IMPLEMENTATION_ORDER_MATRIX if e["order"] == expected_order), None)
        if entry and entry["endpoint"] == expected_endpoint:
            report.add(
                f"order_{expected_order}_correct", "PASS", f"order {expected_order}: {entry['endpoint'].split('/')[-1]}"
            )
        else:
            report.add(f"order_{expected_order}_correct", "FAIL", f"order {expected_order} 불일치")


def check_next_phase_readiness(report: AuditReport) -> None:
    if NEXT_PHASE_READINESS.get("next_phase"):
        report.add("next_phase_defined", "PASS", f"next: {NEXT_PHASE_READINESS['next_phase']}")
    else:
        report.add("next_phase_defined", "WARN", "next_phase 미정의")


def run_audit() -> AuditReport:
    report = AuditReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))
    check_global_flags(report)
    check_priority1_plan(report)
    check_router_location(report)
    check_health_schema(report)
    check_providers_schema(report)
    check_storage_schema(report)
    check_redaction_policy(report)
    check_read_only_guard(report)
    check_implementation_order(report)
    check_next_phase_readiness(report)

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

    out_path = REPO_ROOT / "data" / "app_api_readonly_endpoints_implementation_plan_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] Read-Only Endpoints Implementation Plan Audit")
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
