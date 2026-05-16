"""5050 Phase 1-E — adapter implementation plan 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_01

Phase 1-B/1-D에서 확정된 adapter 3개에 대해
구현 설계도면 + 작업 순서 + 위험 게이트 + 테스트 계획 + 롤백 기준을 고정한다.
실제 구현은 금지. 계획만 작성.

실행:
    python scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py
    python scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py --json

절대 금지:
    5050 route 수정/삭제 금지 / 8400 handler 수정 금지 / adapter 실제 구현 금지
    nginx 변경 금지 / 서버 반영 금지 / 실제 HTTP 호출 금지
    실제 email fetch 금지 / 실제 approve/reject 금지 / execute 호출 금지
    webhook 호출 금지 / DB write 금지 / secret 값 출력 금지
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_route_modify":          False,
    "8400_handler_modify":        False,
    "adapter_implementation":     False,
    "nginx_change":               False,
    "server_apply":               False,
    "container_restart":          False,
    "actual_http_call":           False,
    "actual_email_fetch":         False,
    "actual_approve":             False,
    "actual_reject":              False,
    "actual_execute":             False,
    "actual_webhook_call":        False,
    "actual_db_write":            False,
    "secret_value_output":        False,
    "actual_ui_change":           False,
    "route_handler_change":       False,
}

# ── known baseline failures ───────────────────────────────────────────────────

KNOWN_BASELINE_FAILURES = [
    "tests/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
    "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
    "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_fastmcp_call_tool_invokes_local_cad_bridge_health",
]

# ── 단계별 구현 로드맵 ────────────────────────────────────────────────────────

IMPLEMENTATION_PHASE_PLAN: list[dict[str, Any]] = [
    {
        "phase":       "PHASE_1F",
        "label":       "adapter skeleton only",
        "description": (
            "adapter 모듈 뼈대 생성만 허용. "
            "실제 route 연결 금지. 실제 호출 금지. "
            "함수 단위 테스트만 허용."
        ),
        "allowed":     ["skeleton_creation", "unit_test_only"],
        "forbidden":   ["route_connection", "live_call", "db_write"],
    },
    {
        "phase":       "PHASE_1G",
        "label":       "adapter unit implementation",
        "description": (
            "adapter 함수 단위 구현. "
            "fixture 기반 변환 테스트만 허용. "
            "실제 route 연결 금지."
        ),
        "allowed":     ["unit_implementation", "fixture_based_tests"],
        "forbidden":   ["route_connection", "live_call"],
    },
    {
        "phase":       "PHASE_1H",
        "label":       "route wrapper candidate",
        "description": (
            "route wrapper 후보 작성. "
            "feature flag 기본 OFF. "
            "실제 운영 traffic 연결 금지."
        ),
        "allowed":     ["route_wrapper_candidate", "feature_flag_off_default"],
        "forbidden":   ["live_traffic_connection", "feature_flag_on"],
    },
    {
        "phase":       "PHASE_1I",
        "label":       "staging/dry-run internal smoke",
        "description": (
            "staging 환경 dry-run internal smoke만 허용. "
            "실제 approve/reject/email fetch 금지. "
            "DB write 금지."
        ),
        "allowed":     ["staging_internal_smoke"],
        "forbidden":   ["actual_approve_reject_fetch", "db_write"],
    },
    {
        "phase":       "PHASE_1J",
        "label":       "SAME_CONTRACT legacy deactivation review",
        "description": (
            "SAME_CONTRACT 2개 (/api/v1/inbox, /api/v1/tasks) "
            "legacy 비활성화 후보 재검토. "
            "단, adapter 3개 안정화 후 진행."
        ),
        "allowed":     ["legacy_deactivation_candidate_review"],
        "forbidden":   ["deactivation_before_adapter_stable"],
        "precondition": "Phase 1-F/G/H/I adapter 3개 안정화 완료 필수",
    },
]

# ── Phase 1-E Implementation Plan Matrix ─────────────────────────────────────

PHASE1E_IMPLEMENTATION_PLANS: list[dict[str, Any]] = [

    # A. INBOX_EMAIL_FETCH_ADAPTER ────────────────────────────────────────────
    {
        # 식별
        "phase":                 "PHASE_1E",
        "implementation_plan_id": "PLAN_INBOX_EMAIL_FETCH_ADAPTER_IMPLEMENTATION",
        "adapter_id":            "INBOX_EMAIL_FETCH_ADAPTER",

        # 경로 template
        "legacy_method":           "POST",
        "legacy_path_template":    "/api/v1/inbox/email/fetch",
        "fastapi_method":          "POST",
        "fastapi_path_template":   "/api/v1/inbox/email/fetch",

        # 분류
        "adapter_type":  "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER",
        "risk_level":    "MEDIUM",

        # 구현 금지 플래그
        "implementation_allowed":        False,
        "live_call_allowed":             False,
        "side_effect_allowed":           False,
        "db_write_allowed":              False,
        "secret_value_allowed":          False,
        "server_apply_allowed":          False,
        "route_handler_change_allowed":  False,
        "nginx_change_allowed":          False,
        "approval_gate_required":        False,
        "rollback_required":             True,

        # 상태
        "implementation_plan_status": "PLAN_ONLY_READY",
        "verdict":                    "IMPLEMENTATION_PLAN_READY",

        # 구현 후보
        "proposed_adapter_module":   "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
        "proposed_adapter_function": "adapt_inbox_email_fetch_request_response",
        "proposed_test_module":      "tests/test_5050_phase1f_inbox_email_fetch_adapter_impl_20260517.py",
        "proposed_audit_module":     "scripts/ops/audit_5050_phase1f_inbox_email_fetch_adapter.py",
        "proposed_integration_point": "FastAPI route wrapper 또는 service boundary 앞단",
        "forbidden_files": [
            "app_5050.py",
            "app.py",
            "backend/routes/",
            "backend/api/",
            "nginx/conf.d/",
            "backend/auth/",
            "backend/db/",
        ],
        "allowed_files_for_next_phase": [
            "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
            "tests/test_5050_phase1f_inbox_email_fetch_adapter_impl_20260517.py",
        ],
        "required_feature_flag": "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED",
        "required_safety_gate":  "NO_LIVE_EMAIL_FETCH_IN_TESTS",

        # 요청/응답 매핑 계획
        "request_mapping_plan":    "map static request fixture only — no live credential",
        "path_mapping_plan":       "NO_PATH_PARAM_REQUIRED — same path both sides",
        "response_mapping_plan":   "normalize legacy and fastapi email fetch response shape",
        "error_mapping_plan":      "STANDARD_ERROR_ENVELOPE passthrough",
        "status_code_mapping_plan": "COMPAT_STATUS_ONLY — 200/4xx/5xx",
        "auth_mapping_plan":       "compare existing auth expectation only — no bypass",
        "permission_mapping_plan": "INBOX_ACCESS_REQUIRED — no approval gate",

        # 검증/롤백 계획
        "required_unit_tests":       ["fixture request/response shape test", "credential name only test"],
        "required_contract_tests":   ["Phase 1-B contract consistency check"],
        "required_dry_run_tests":    ["Phase 1-D dry-run compat consistency check"],
        "required_regression_tests": ["test_5050_phase1b_adapter_contract_detail_20260517.py",
                                      "test_5050_phase1d_adapter_dry_run_compat_20260517.py"],
        "required_audit_checks":     ["audit_5050_phase1b_adapter_contract_detail.py",
                                      "audit_5050_phase1d_adapter_dry_run_compat.py"],
        "rollback_plan": (
            "1. LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED 플래그 OFF "
            "2. 5050 route 그대로 유지 "
            "3. adapter 모듈만 비활성화 — 라우터/nginx 변경 없음"
        ),
        "stop_conditions": [
            "실제 email fetch 호출 발생 시",
            "credential value 코드에 하드코딩 시",
            "5050 route handler 변경 시",
            "8400 handler 변경 시",
            "DB write 발생 시",
        ],
        "next_phase": "PHASE_1F",
    },

    # B. TASK_APPROVE_PATH_AUTH_ADAPTER ───────────────────────────────────────
    {
        # 식별
        "phase":                 "PHASE_1E",
        "implementation_plan_id": "PLAN_TASK_APPROVE_PATH_AUTH_ADAPTER_IMPLEMENTATION",
        "adapter_id":            "TASK_APPROVE_PATH_AUTH_ADAPTER",

        # 경로 template — <id> 표기 보존 (double slash 절대 금지)
        "legacy_method":           "POST",
        "legacy_path_template":    "/api/v1/tasks/<id>/approve",
        "fastapi_method":          "POST",
        "fastapi_path_template":   "/api/v1/tasks/{id}/approve",

        # 분류
        "adapter_type":  "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",
        "risk_level":    "HIGH",

        # 구현 금지 플래그
        "implementation_allowed":        False,
        "live_call_allowed":             False,
        "side_effect_allowed":           False,
        "db_write_allowed":              False,
        "secret_value_allowed":          False,
        "server_apply_allowed":          False,
        "route_handler_change_allowed":  False,
        "nginx_change_allowed":          False,
        "approval_gate_required":        True,
        "rollback_required":             True,

        # 상태
        "implementation_plan_status": "PLAN_ONLY_READY",
        "verdict":                    "IMPLEMENTATION_PLAN_READY",

        # 구현 후보
        "proposed_adapter_module":   "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
        "proposed_adapter_function": "adapt_task_approve_path_auth_response",
        "proposed_test_module":      "tests/test_5050_phase1f_task_approve_adapter_impl_20260517.py",
        "proposed_audit_module":     "scripts/ops/audit_5050_phase1f_task_approve_adapter.py",
        "proposed_integration_point": "approval service boundary 앞단 또는 route wrapper",
        "forbidden_files": [
            "app_5050.py",
            "app.py",
            "backend/routes/",
            "backend/api/",
            "nginx/conf.d/",
            "backend/auth/",
            "backend/db/",
            "/api/v1/tasks//approve",
        ],
        "allowed_files_for_next_phase": [
            "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
            "tests/test_5050_phase1f_task_approve_adapter_impl_20260517.py",
        ],
        "required_feature_flag": "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED",
        "required_safety_gate":  "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS",

        # 요청/응답 매핑 계획
        "request_mapping_plan":    "static approval request fixture only — <id> → {id} conversion",
        "path_mapping_plan":       "LEGACY_<id>_TO_FASTAPI_{id} — angle bracket to curly brace",
        "response_mapping_plan":   "normalize approval response {status, task_id}",
        "error_mapping_plan":      "STANDARD_ERROR_ENVELOPE passthrough",
        "status_code_mapping_plan": "200/401/403/404 compat mapping",
        "auth_mapping_plan":       "COMPARE_ONLY_NO_BYPASS — both sides auth policy compare",
        "permission_mapping_plan": "APPROVAL_ACTION_REQUIRES_EXPLICIT_GATE — gate check before adapter",

        # 검증/롤백 계획
        "required_unit_tests":       ["path param <id>→{id} conversion test",
                                      "approval gate check test",
                                      "double slash prevention test"],
        "required_contract_tests":   ["Phase 1-B contract consistency check"],
        "required_dry_run_tests":    ["Phase 1-D DRYRUN_TASK_APPROVE_COMPAT consistency check"],
        "required_regression_tests": ["test_5050_phase1b_adapter_contract_detail_20260517.py",
                                      "test_5050_phase1d_adapter_dry_run_compat_20260517.py"],
        "required_audit_checks":     ["audit_5050_phase1b_adapter_contract_detail.py",
                                      "audit_5050_phase1d_adapter_dry_run_compat.py"],
        "rollback_plan": (
            "1. LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED 플래그 OFF "
            "2. 5050 approve route 그대로 유지 "
            "3. adapter 모듈만 비활성화 — 라우터/nginx 변경 없음 "
            "4. approval gate 우회 없음 확인"
        ),
        "stop_conditions": [
            "실제 approve 호출 발생 시",
            "task 상태 변경 발생 시",
            "approval gate 우회 코드 발생 시",
            "/api/v1/tasks//approve 경로 생성 시",
            "5050 route handler 변경 시",
            "8400 handler 변경 시",
            "DB write 발생 시",
        ],
        "next_phase": "PHASE_1F",
    },

    # C. TASK_REJECT_PATH_AUTH_ADAPTER ────────────────────────────────────────
    {
        # 식별
        "phase":                 "PHASE_1E",
        "implementation_plan_id": "PLAN_TASK_REJECT_PATH_AUTH_ADAPTER_IMPLEMENTATION",
        "adapter_id":            "TASK_REJECT_PATH_AUTH_ADAPTER",

        # 경로 template — <id> 표기 보존 (double slash 절대 금지)
        "legacy_method":           "POST",
        "legacy_path_template":    "/api/v1/tasks/<id>/reject",
        "fastapi_method":          "POST",
        "fastapi_path_template":   "/api/v1/tasks/{id}/reject",

        # 분류
        "adapter_type":  "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",
        "risk_level":    "HIGH",

        # 구현 금지 플래그
        "implementation_allowed":        False,
        "live_call_allowed":             False,
        "side_effect_allowed":           False,
        "db_write_allowed":              False,
        "secret_value_allowed":          False,
        "server_apply_allowed":          False,
        "route_handler_change_allowed":  False,
        "nginx_change_allowed":          False,
        "approval_gate_required":        True,
        "rollback_required":             True,

        # 상태
        "implementation_plan_status": "PLAN_ONLY_READY",
        "verdict":                    "IMPLEMENTATION_PLAN_READY",

        # 구현 후보
        "proposed_adapter_module":   "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
        "proposed_adapter_function": "adapt_task_reject_path_auth_response",
        "proposed_test_module":      "tests/test_5050_phase1f_task_reject_adapter_impl_20260517.py",
        "proposed_audit_module":     "scripts/ops/audit_5050_phase1f_task_reject_adapter.py",
        "proposed_integration_point": "approval service boundary 앞단 또는 route wrapper",
        "forbidden_files": [
            "app_5050.py",
            "app.py",
            "backend/routes/",
            "backend/api/",
            "nginx/conf.d/",
            "backend/auth/",
            "backend/db/",
            "/api/v1/tasks//reject",
        ],
        "allowed_files_for_next_phase": [
            "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
            "tests/test_5050_phase1f_task_reject_adapter_impl_20260517.py",
        ],
        "required_feature_flag": "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED",
        "required_safety_gate":  "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS",

        # 요청/응답 매핑 계획
        "request_mapping_plan":    "static reject request fixture only — <id> → {id} conversion",
        "path_mapping_plan":       "LEGACY_<id>_TO_FASTAPI_{id} — angle bracket to curly brace",
        "response_mapping_plan":   "normalize reject response {status, task_id}",
        "error_mapping_plan":      "STANDARD_ERROR_ENVELOPE passthrough",
        "status_code_mapping_plan": "200/401/403/404 compat mapping",
        "auth_mapping_plan":       "COMPARE_ONLY_NO_BYPASS — both sides auth policy compare",
        "permission_mapping_plan": "REJECT_ACTION_REQUIRES_EXPLICIT_GATE — gate check before adapter",

        # 검증/롤백 계획
        "required_unit_tests":       ["path param <id>→{id} conversion test",
                                      "reject gate check test",
                                      "double slash prevention test"],
        "required_contract_tests":   ["Phase 1-B contract consistency check"],
        "required_dry_run_tests":    ["Phase 1-D DRYRUN_TASK_REJECT_COMPAT consistency check"],
        "required_regression_tests": ["test_5050_phase1b_adapter_contract_detail_20260517.py",
                                      "test_5050_phase1d_adapter_dry_run_compat_20260517.py"],
        "required_audit_checks":     ["audit_5050_phase1b_adapter_contract_detail.py",
                                      "audit_5050_phase1d_adapter_dry_run_compat.py"],
        "rollback_plan": (
            "1. LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED 플래그 OFF "
            "2. 5050 reject route 그대로 유지 "
            "3. adapter 모듈만 비활성화 — 라우터/nginx 변경 없음 "
            "4. rejection gate 우회 없음 확인"
        ),
        "stop_conditions": [
            "실제 reject 호출 발생 시",
            "task 상태 변경 발생 시",
            "approval gate 우회 코드 발생 시",
            "/api/v1/tasks//reject 경로 생성 시",
            "5050 route handler 변경 시",
            "8400 handler 변경 시",
            "DB write 발생 시",
        ],
        "next_phase": "PHASE_1F",
    },
]

# ── 명시적 제외 목록 ──────────────────────────────────────────────────────────

PHASE1E_EXCLUDED = {
    "HOLD_DANGEROUS":        ["/api/v1/tasks/<task_id>/execute"],
    "DO_NOT_TOUCH":          ["/api/v1/webhooks/kakaowork",
                              "/api/v1/webhooks/kakaotalk-channel"],
    "HOLD_DASHBOARD":        ["/dashboard", "/dashboard/tasks/<task_id>",
                              "/dashboard/approve", "/dashboard/reject"],
    "SAME_CONTRACT_HOLD":    ["/api/v1/inbox", "/api/v1/tasks"],
    "DOUBLE_SLASH_FORBIDDEN": [
        "/api/v1/tasks//approve",
        "/api/v1/tasks//reject",
    ],
}


# ── 유효성 검사 헬퍼 ──────────────────────────────────────────────────────────

def _no_double_slash() -> bool:
    for p in PHASE1E_IMPLEMENTATION_PLANS:
        for field in ("legacy_path_template", "fastapi_path_template"):
            if "//" in p[field]:
                return False
    return True


def _no_forbidden_in_plans() -> bool:
    paths = [p["legacy_path_template"] for p in PHASE1E_IMPLEMENTATION_PLANS]
    for path in paths:
        if "execute" in path:
            return False
        if "webhook" in path:
            return False
        if "/dashboard" in path:
            return False
        if path in ("/api/v1/inbox", "/api/v1/tasks"):
            return False
    return True


# ── 감사 함수 ─────────────────────────────────────────────────────────────────

def run_audit() -> dict[str, Any]:
    plans = PHASE1E_IMPLEMENTATION_PLANS

    total                    = len(plans)
    impl_false               = sum(1 for p in plans if p["implementation_allowed"] is False)
    live_false               = sum(1 for p in plans if p["live_call_allowed"] is False)
    side_false               = sum(1 for p in plans if p["side_effect_allowed"] is False)
    db_false                 = sum(1 for p in plans if p["db_write_allowed"] is False)
    secret_false             = sum(1 for p in plans if p["secret_value_allowed"] is False)
    route_handler_false      = sum(1 for p in plans if p["route_handler_change_allowed"] is False)
    server_apply_false       = sum(1 for p in plans if p["server_apply_allowed"] is False)
    nginx_false              = sum(1 for p in plans if p["nginx_change_allowed"] is False)
    rollback_true            = sum(1 for p in plans if p["rollback_required"] is True)
    gate_true                = sum(1 for p in plans if p["approval_gate_required"] is True)
    high_risk                = sum(1 for p in plans if p["risk_level"] == "HIGH")
    medium_risk              = sum(1 for p in plans if p["risk_level"] == "MEDIUM")
    feature_flag_cnt         = sum(1 for p in plans if p.get("required_feature_flag"))
    verdict_ready            = sum(1 for p in plans if p["verdict"] == "IMPLEMENTATION_PLAN_READY")

    no_double_slash  = _no_double_slash()
    no_forbidden     = _no_forbidden_in_plans()
    phase_plan_count = len(IMPLEMENTATION_PHASE_PLAN)

    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]

    success = (
        total == 3
        and impl_false == 3
        and live_false == 3
        and side_false == 3
        and db_false == 3
        and secret_false == 3
        and route_handler_false == 3
        and server_apply_false == 3
        and nginx_false == 3
        and rollback_true == 3
        and gate_true == 2
        and high_risk == 2
        and medium_risk == 1
        and feature_flag_cnt == 3
        and verdict_ready == 3
        and no_double_slash
        and no_forbidden
        and phase_plan_count == 5
        and len(boundary_violations) == 0
    )

    return {
        "audit_id":  "ASSISTANT_BACKEND_5050_LEGACY_PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_01",
        "verdict":   "PHASE1E_ADAPTER_IMPLEMENTATION_PLAN_READY" if success else "FAIL",
        "success":   success,
        "implementation_plans":    plans,
        "implementation_phase_plan": IMPLEMENTATION_PHASE_PLAN,
        "excluded":                PHASE1E_EXCLUDED,
        "safe_boundary":           {**SAFE_BOUNDARY, "violations": boundary_violations},
        "known_baseline_failures": KNOWN_BASELINE_FAILURES,
        "summary": {
            "total_plans":                   total,
            "implementation_allowed_false":  impl_false,
            "live_call_allowed_false":       live_false,
            "side_effect_allowed_false":     side_false,
            "db_write_allowed_false":        db_false,
            "secret_value_allowed_false":    secret_false,
            "route_handler_change_false":    route_handler_false,
            "server_apply_allowed_false":    server_apply_false,
            "nginx_change_allowed_false":    nginx_false,
            "rollback_required_true":        rollback_true,
            "approval_gate_required_true":   gate_true,
            "risk_level_HIGH":               high_risk,
            "risk_level_MEDIUM":             medium_risk,
            "feature_flag_plan_count":       feature_flag_cnt,
            "verdict_ready":                 verdict_ready,
            "no_double_slash":               no_double_slash,
            "no_forbidden_route":            no_forbidden,
            "phase_plan_count":              phase_plan_count,
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    print("\n[Phase 1-E Implementation Plan Matrix]")
    header = (f"{'PLAN_ID':<52} {'ADAPTER_ID':<36} "
              f"{'RISK':<8} {'GATE':<6} {'IMPL_OK':<8} {'VERDICT'}")
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for p in audit["implementation_plans"]:
        print(
            f"  {p['implementation_plan_id']:<52} {p['adapter_id']:<36} "
            f"{p['risk_level']:<8} {str(p['approval_gate_required']):<6} "
            f"{str(p['implementation_allowed']):<8} {p['verdict']}"
        )

    print("\n[구현 후보 파일]")
    for p in audit["implementation_plans"]:
        print(f"  {p['adapter_id']}:")
        print(f"    module  : {p['proposed_adapter_module']}")
        print(f"    function: {p['proposed_adapter_function']}")
        print(f"    test    : {p['proposed_test_module']}")
        print(f"    flag    : {p['required_feature_flag']}")
        print(f"    gate    : {p['required_safety_gate']}")
        print()

    print("[단계별 구현 로드맵]")
    for phase in audit["implementation_phase_plan"]:
        print(f"  {phase['phase']}: {phase['label']}")

    s = audit["summary"]
    print("\n[집계]")
    items = [
        ("총 plan 수",                    s["total_plans"],                  3),
        ("implementation_allowed=False",  s["implementation_allowed_false"], 3),
        ("live_call_allowed=False",       s["live_call_allowed_false"],      3),
        ("side_effect_allowed=False",     s["side_effect_allowed_false"],    3),
        ("db_write_allowed=False",        s["db_write_allowed_false"],       3),
        ("secret_value_allowed=False",    s["secret_value_allowed_false"],   3),
        ("route_handler_change=False",    s["route_handler_change_false"],   3),
        ("server_apply_allowed=False",    s["server_apply_allowed_false"],   3),
        ("nginx_change_allowed=False",    s["nginx_change_allowed_false"],   3),
        ("rollback_required=True",        s["rollback_required_true"],       3),
        ("approval_gate_required=True",   s["approval_gate_required_true"],  2),
        ("risk_level=HIGH",               s["risk_level_HIGH"],              2),
        ("risk_level=MEDIUM",             s["risk_level_MEDIUM"],            1),
        ("feature flag plan",             s["feature_flag_plan_count"],      3),
        ("phase plan count",              s["phase_plan_count"],             5),
        ("double slash 없음",             s["no_double_slash"],              True),
        ("forbidden route 제외",          s["no_forbidden_route"],           True),
    ]
    for label, val, expected in items:
        mark = "✅" if val == expected else "❌"
        print(f"  {mark} {label}: {val} (기준: {expected})")

    print("\n[제외 확인]")
    for label, paths in audit["excluded"].items():
        for p in paths:
            print(f"  ✅ 제외됨: [{label}] {p}")

    sb = audit["safe_boundary"]
    print("\n[SAFE BOUNDARY]")
    if sb["violations"]:
        print(f"  ❌ 위반: {sb['violations']}")
    else:
        print("  ✅ 위반 없음")

    print("\n[known baseline failures (이번 공정 무관)]")
    for f in audit["known_baseline_failures"]:
        print(f"  - {f}")

    print("=" * 70)
    print(f"VERDICT: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="5050 Phase 1-E adapter implementation plan 감사"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = run_audit()
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        _print_report(audit)
    sys.exit(0 if audit["success"] else 1)


if __name__ == "__main__":
    main()
