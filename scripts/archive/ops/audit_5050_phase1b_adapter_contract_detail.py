"""5050 Phase 1-B — COMPATIBLE_WITH_ADAPTER 3개 adapter 상세 계약 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1B_ADAPTER_CONTRACT_DETAIL_01

Phase 1-B 대상 3개 route의 adapter 상세 계약을 machine-readable하게 고정한다.
실제 HTTP 호출 없이 정적 계약 검증만 수행한다.

실행:
    python scripts/archive/ops/audit_5050_phase1b_adapter_contract_detail.py
    python scripts/archive/ops/audit_5050_phase1b_adapter_contract_detail.py --json

절대 금지:
    실제 HTTP 호출 금지 / email fetch 실행 금지 / approve/reject 실행 금지
    execute 호출 금지 / webhook 호출 금지 / DB write 금지
    5050 route 수정 금지 / 8400 handler 수정 금지 / nginx 변경 금지
    secret 값 출력 금지 / 서버 반영 금지
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_route_modify":       False,
    "8400_handler_modify":     False,
    "nginx_change":            False,
    "server_apply":            False,
    "actual_http_call":        False,
    "actual_email_fetch":      False,
    "actual_approve":          False,
    "actual_reject":           False,
    "actual_execute":          False,
    "actual_webhook_call":     False,
    "actual_db_write":         False,
    "secret_value_output":     False,
    "actual_ui_change":        False,
}

# ── Phase 1-B Adapter Detail Matrix ──────────────────────────────────────────

PHASE1B_ADAPTERS: list[dict[str, Any]] = [

    # A. POST /api/v1/inbox/email/fetch ──────────────────────────────────────
    {
        # 식별
        "phase":              "PHASE_1B",
        "adapter_id":         "INBOX_EMAIL_FETCH_ADAPTER",

        # 경로
        "legacy_method":      "POST",
        "legacy_path":        "/api/v1/inbox/email/fetch",
        "fastapi_method":     "POST",
        "fastapi_path":       "/api/v1/inbox/email/fetch",

        # 분류
        "overlap_class":      "COMPATIBLE_WITH_ADAPTER",
        "adapter_required":   True,
        "adapter_type":       "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER",

        # 위험도
        "risk_level":         "MEDIUM",

        # 실행 금지
        "live_call_allowed":  False,
        "do_not_call_live":   True,
        "side_effect_allowed": False,

        # 보안
        "secret_value_allowed": False,
        "db_write_allowed":     False,
        "server_apply_allowed": False,

        # 상태
        "contract_detail_status": "DETAIL_FROZEN_CANDIDATE",
        "verdict":                "ADAPTER_DETAIL_READY",

        # 요청 계약
        "request_body_policy":   "STATIC_ONLY_NO_LIVE_CREDENTIAL",
        "request_param_policy":  "NONE_REQUIRED",
        "path_param_policy":     "NO_PATH_PARAM",
        "query_param_policy":    "NONE_REQUIRED",
        "header_policy":         "AUTH_HEADER_ONLY_NO_SECRET_VALUE",
        "content_type_policy":   "application/json",

        # 응답 계약
        "response_status_policy": "200_ON_SUCCESS_4XX_ON_AUTH_5XX_ON_FETCH_FAIL",
        "response_schema_policy": "FREEZE_COMPAT_RESPONSE_SHAPE",
        "error_schema_policy":    "STANDARD_ERROR_ENVELOPE",
        "legacy_response_shape":  "{'fetched': int, 'items': list}  # 구체값은 live test 후 확정",
        "fastapi_response_shape": "{'fetched': int, 'items': list}  # 8400 schema 동일 예상",
        "adapter_response_action": "NORMALIZE_LEGACY_FASTAPI_RESPONSE",

        # 인증/권한
        "auth_expected":     True,
        "auth_policy":       "BEARER_OR_SESSION_TOKEN_REQUIRED",
        "permission_policy": "INBOX_ACCESS_REQUIRED",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "secret_policy":     "NEVER_PRINT_SECRET_VALUE",

        # 위험 경계
        "forbidden_live_actions": [
            "ACTUAL_EMAIL_SERVER_CONNECT",
            "ACTUAL_IMAP_POP3_REQUEST",
            "CREDENTIAL_VALUE_OUTPUT",
        ],
        "forbidden_routes":      [],
        "excluded_from_phase":   ["PHASE_1C", "HOLD_DANGEROUS", "DO_NOT_TOUCH"],
        "approval_gate_required": False,
        "executor_boundary":      "NOT_EXECUTOR_ROUTE",

        # 다음 액션
        "do_not_stop_5050":   True,
        "nginx_unchanged":    True,
        "next_action":        (
            "1. 8400 /api/v1/inbox/email/fetch response schema 정적 확인 "
            "2. credential env key 목록 확인 (값 출력 금지) "
            "3. NORMALIZE_LEGACY_FASTAPI_RESPONSE adapter 설계 "
            "4. 5050 해당 route 비활성화는 adapter 구현 완료 후"
        ),
    },

    # B. POST /api/v1/tasks/<id>/approve ─────────────────────────────────────
    {
        # 식별
        "phase":              "PHASE_1B",
        "adapter_id":         "TASK_APPROVE_PATH_AUTH_ADAPTER",

        # 경로 — <id> 표기 보존 (double slash 절대 금지)
        "legacy_method":      "POST",
        "legacy_path":        "/api/v1/tasks/<id>/approve",
        "fastapi_method":     "POST",
        "fastapi_path":       "/api/v1/tasks/{id}/approve",

        # 분류
        "overlap_class":      "COMPATIBLE_WITH_ADAPTER",
        "adapter_required":   True,
        "adapter_type":       "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",

        # 위험도
        "risk_level":         "HIGH",

        # 실행 금지
        "live_call_allowed":  False,
        "do_not_call_live":   True,
        "side_effect_allowed": False,

        # 보안
        "secret_value_allowed": False,
        "db_write_allowed":     False,
        "server_apply_allowed": False,

        # 상태
        "contract_detail_status": "DETAIL_FROZEN_CANDIDATE",
        "verdict":                "ADAPTER_DETAIL_READY",

        # 요청 계약
        "request_body_policy":   "STATIC_CONTRACT_ONLY",
        "request_param_policy":  "NONE_REQUIRED",
        "path_param_policy":     "LEGACY_ANGLE_BRACKET_TO_FASTAPI_CURLY_BRACE",
        "query_param_policy":    "NONE_REQUIRED",
        "header_policy":         "AUTH_HEADER_REQUIRED",
        "content_type_policy":   "application/json",

        # 응답 계약
        "response_status_policy": "200_ON_SUCCESS_401_ON_UNAUTH_403_ON_FORBIDDEN_404_ON_NOT_FOUND",
        "response_schema_policy": "FREEZE_COMPAT_RESPONSE_SHAPE",
        "error_schema_policy":    "STANDARD_ERROR_ENVELOPE",
        "legacy_response_shape":  "{'status': 'approved', 'task_id': str}  # 구체값은 contract 비교 후 확정",
        "fastapi_response_shape": "{'status': 'approved', 'task_id': str}  # 8400 schema 비교 필요",
        "adapter_response_action": "NORMALIZE_APPROVAL_RESPONSE",

        # 인증/권한
        "auth_expected":     True,
        "auth_policy":       "COMPARE_ONLY_NO_BYPASS",
        "permission_policy": "APPROVAL_ACTION_REQUIRES_EXPLICIT_GATE",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "secret_policy":     "NEVER_PRINT_SECRET_VALUE",

        # 위험 경계
        "forbidden_live_actions": [
            "ACTUAL_TASK_STATE_CHANGE",
            "ACTUAL_APPROVAL_EXECUTION",
            "AUTH_POLICY_BYPASS",
            "DB_WRITE",
        ],
        "forbidden_routes": [
            "/api/v1/tasks//approve",   # double slash 금지
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
            "/api/v1/webhooks/kakaotalk-channel",
        ],
        "excluded_from_phase":   ["HOLD_DANGEROUS", "DO_NOT_TOUCH", "HOLD_DASHBOARD"],
        "approval_gate_required": True,
        "executor_boundary":      "APPROVAL_ROUTE_NOT_EXECUTOR",

        # 다음 액션
        "do_not_stop_5050":   True,
        "nginx_unchanged":    True,
        "next_action":        (
            "1. 5050 approve handler auth policy 정적 확인 "
            "2. 8400 approve handler auth policy 정적 확인 "
            "3. path param 표기 차이 (<id> vs {id}) adapter 구현 설계 "
            "4. approval gate 구현 확인 "
            "5. 5050 해당 route 비활성화는 adapter 구현 완료 후"
        ),
    },

    # C. POST /api/v1/tasks/<id>/reject ──────────────────────────────────────
    {
        # 식별
        "phase":              "PHASE_1B",
        "adapter_id":         "TASK_REJECT_PATH_AUTH_ADAPTER",

        # 경로 — <id> 표기 보존 (double slash 절대 금지)
        "legacy_method":      "POST",
        "legacy_path":        "/api/v1/tasks/<id>/reject",
        "fastapi_method":     "POST",
        "fastapi_path":       "/api/v1/tasks/{id}/reject",

        # 분류
        "overlap_class":      "COMPATIBLE_WITH_ADAPTER",
        "adapter_required":   True,
        "adapter_type":       "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",

        # 위험도
        "risk_level":         "HIGH",

        # 실행 금지
        "live_call_allowed":  False,
        "do_not_call_live":   True,
        "side_effect_allowed": False,

        # 보안
        "secret_value_allowed": False,
        "db_write_allowed":     False,
        "server_apply_allowed": False,

        # 상태
        "contract_detail_status": "DETAIL_FROZEN_CANDIDATE",
        "verdict":                "ADAPTER_DETAIL_READY",

        # 요청 계약
        "request_body_policy":   "STATIC_CONTRACT_ONLY",
        "request_param_policy":  "NONE_REQUIRED",
        "path_param_policy":     "LEGACY_ANGLE_BRACKET_TO_FASTAPI_CURLY_BRACE",
        "query_param_policy":    "NONE_REQUIRED",
        "header_policy":         "AUTH_HEADER_REQUIRED",
        "content_type_policy":   "application/json",

        # 응답 계약
        "response_status_policy": "200_ON_SUCCESS_401_ON_UNAUTH_403_ON_FORBIDDEN_404_ON_NOT_FOUND",
        "response_schema_policy": "FREEZE_COMPAT_RESPONSE_SHAPE",
        "error_schema_policy":    "STANDARD_ERROR_ENVELOPE",
        "legacy_response_shape":  "{'status': 'rejected', 'task_id': str}  # 구체값은 contract 비교 후 확정",
        "fastapi_response_shape": "{'status': 'rejected', 'task_id': str}  # 8400 schema 비교 필요",
        "adapter_response_action": "NORMALIZE_REJECT_RESPONSE",

        # 인증/권한
        "auth_expected":     True,
        "auth_policy":       "COMPARE_ONLY_NO_BYPASS",
        "permission_policy": "REJECT_ACTION_REQUIRES_EXPLICIT_GATE",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "secret_policy":     "NEVER_PRINT_SECRET_VALUE",

        # 위험 경계
        "forbidden_live_actions": [
            "ACTUAL_TASK_STATE_CHANGE",
            "ACTUAL_REJECT_EXECUTION",
            "AUTH_POLICY_BYPASS",
            "DB_WRITE",
        ],
        "forbidden_routes": [
            "/api/v1/tasks//reject",    # double slash 금지
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
            "/api/v1/webhooks/kakaotalk-channel",
        ],
        "excluded_from_phase":   ["HOLD_DANGEROUS", "DO_NOT_TOUCH", "HOLD_DASHBOARD"],
        "approval_gate_required": True,
        "executor_boundary":      "APPROVAL_ROUTE_NOT_EXECUTOR",

        # 다음 액션
        "do_not_stop_5050":   True,
        "nginx_unchanged":    True,
        "next_action":        (
            "1. 5050 reject handler auth policy 정적 확인 "
            "2. 8400 reject handler auth policy 정적 확인 "
            "3. path param 표기 차이 (<id> vs {id}) adapter 구현 설계 "
            "4. approval(reject) gate 구현 확인 "
            "5. 5050 해당 route 비활성화는 adapter 구현 완료 후"
        ),
    },
]

# ── SAME_CONTRACT routes (Phase 1-B 제외 확인용) ─────────────────────────────

SAME_CONTRACT_EXCLUDED = [
    {"path": "/api/v1/inbox", "method": "GET",  "reason": "Phase 1-C 대상"},
    {"path": "/api/v1/tasks", "method": "POST", "reason": "Phase 1-C 대상"},
]

# ── 명시적 제외 목록 ──────────────────────────────────────────────────────────

PHASE1B_EXCLUDED = {
    "HOLD_DANGEROUS":  ["/api/v1/tasks/<task_id>/execute"],
    "DO_NOT_TOUCH":    ["/api/v1/webhooks/kakaowork",
                        "/api/v1/webhooks/kakaotalk-channel"],
    "HOLD_DASHBOARD":  ["/dashboard", "/dashboard/tasks/<task_id>",
                        "/dashboard/approve", "/dashboard/reject"],
    "SAME_CONTRACT":   ["/api/v1/inbox", "/api/v1/tasks"],
    "DOUBLE_SLASH_FORBIDDEN": [
        "/api/v1/tasks//approve",
        "/api/v1/tasks//reject",
    ],
}


# ── 감사 함수 ─────────────────────────────────────────────────────────────────

def _no_double_slash_in_paths() -> bool:
    for adapter in PHASE1B_ADAPTERS:
        for field in ("legacy_path", "fastapi_path"):
            if "//" in adapter[field]:
                return False
    return True


def run_audit() -> dict[str, Any]:
    adapters = PHASE1B_ADAPTERS
    total               = len(adapters)
    adapter_req_cnt     = sum(1 for a in adapters if a["adapter_required"] is True)
    live_false          = sum(1 for a in adapters if a["live_call_allowed"] is False)
    side_effect_false   = sum(1 for a in adapters if a["side_effect_allowed"] is False)
    secret_false        = sum(1 for a in adapters if a["secret_value_allowed"] is False)
    db_false            = sum(1 for a in adapters if a["db_write_allowed"] is False)
    gate_true           = sum(1 for a in adapters if a["approval_gate_required"] is True)
    high_risk           = sum(1 for a in adapters if a["risk_level"] == "HIGH")
    medium_risk         = sum(1 for a in adapters if a["risk_level"] == "MEDIUM")
    path_param_adapter  = sum(1 for a in adapters if a["adapter_type"] == "PATH_PARAM_AND_AUTH_POLICY_ADAPTER")
    cred_adapter        = sum(1 for a in adapters if a["adapter_type"] == "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER")
    verdict_ready       = sum(1 for a in adapters if a["verdict"] == "ADAPTER_DETAIL_READY")

    phase1b_paths = [a["legacy_path"] for a in adapters]
    excluded_clean = (
        not any("execute" in p for p in phase1b_paths)
        and not any("webhook" in p for p in phase1b_paths)
        and not any("/dashboard" in p for p in phase1b_paths)
        and not any(p in ["/api/v1/inbox", "/api/v1/tasks"] for p in phase1b_paths)
    )
    no_double_slash = _no_double_slash_in_paths()

    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]

    success = (
        total == 3
        and adapter_req_cnt == 3
        and live_false == 3
        and side_effect_false == 3
        and secret_false == 3
        and db_false == 3
        and gate_true == 2
        and high_risk == 2
        and medium_risk == 1
        and path_param_adapter == 2
        and cred_adapter == 1
        and verdict_ready == 3
        and excluded_clean
        and no_double_slash
        and len(boundary_violations) == 0
    )

    return {
        "audit_id":    "ASSISTANT_BACKEND_5050_LEGACY_PHASE1B_ADAPTER_CONTRACT_DETAIL_01",
        "verdict":     "PHASE1B_ADAPTER_CONTRACT_DETAIL_READY" if success else "FAIL",
        "success":     success,
        "adapters":    adapters,
        "excluded":    PHASE1B_EXCLUDED,
        "same_contract_excluded": SAME_CONTRACT_EXCLUDED,
        "safe_boundary": {**SAFE_BOUNDARY, "violations": boundary_violations},
        "summary": {
            "total_adapters":            total,
            "adapter_required_true":     adapter_req_cnt,
            "live_call_allowed_false":   live_false,
            "side_effect_allowed_false": side_effect_false,
            "secret_value_allowed_false": secret_false,
            "db_write_allowed_false":    db_false,
            "approval_gate_required_true": gate_true,
            "risk_level_HIGH":           high_risk,
            "risk_level_MEDIUM":         medium_risk,
            "path_param_adapter":        path_param_adapter,
            "credential_env_adapter":    cred_adapter,
            "verdict_ready":             verdict_ready,
            "excluded_clean":            excluded_clean,
            "no_double_slash":           no_double_slash,
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    print("\n[Phase 1-B Adapter Contract Matrix]")
    header = f"{'ADAPTER_ID':<40} {'METHOD':<6} {'LEGACY PATH':<36} {'TYPE':<38} {'RISK':<8} {'GATE'}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for a in audit["adapters"]:
        print(
            f"  {a['adapter_id']:<40} {a['legacy_method']:<6} "
            f"{a['legacy_path']:<36} {a['adapter_type']:<38} "
            f"{a['risk_level']:<8} {a['approval_gate_required']}"
        )

    print("\n[경로 표기 확인]")
    for a in audit["adapters"]:
        print(f"  legacy : {a['legacy_path']}")
        print(f"  fastapi: {a['fastapi_path']}")
        print()

    s = audit["summary"]
    print("[집계]")
    items = [
        ("총 adapter 수",              s["total_adapters"],            3),
        ("adapter_required=True",      s["adapter_required_true"],     3),
        ("live_call_allowed=False",     s["live_call_allowed_false"],   3),
        ("side_effect_allowed=False",   s["side_effect_allowed_false"], 3),
        ("secret_value_allowed=False",  s["secret_value_allowed_false"],3),
        ("db_write_allowed=False",      s["db_write_allowed_false"],    3),
        ("approval_gate_required=True", s["approval_gate_required_true"],2),
        ("risk_level=HIGH",             s["risk_level_HIGH"],           2),
        ("risk_level=MEDIUM",           s["risk_level_MEDIUM"],         1),
        ("path_param adapter",          s["path_param_adapter"],        2),
        ("credential/env adapter",      s["credential_env_adapter"],    1),
        ("excluded_clean",              s["excluded_clean"],            True),
        ("no_double_slash",             s["no_double_slash"],           True),
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

    print("=" * 70)
    print(f"VERDICT: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    from scripts.common.audit_cli import run_json_or_report_cli

    run_json_or_report_cli("5050 Phase 1-B adapter contract detail 감사", run_audit, _print_report, "success")


if __name__ == "__main__":
    main()
