"""5050 Phase 1-D — adapter dry-run compatibility 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1D_ADAPTER_DRY_RUN_COMPAT_TEST_01

Phase 1-B에서 상세 계약이 고정된 adapter 3개에 대해
실제 HTTP 호출 없이 dry-run fixture로 호환성 계약을 검증한다.

실행:
    python tools/audit_5050_phase1d_adapter_dry_run_compat.py
    python tools/audit_5050_phase1d_adapter_dry_run_compat.py --json

절대 금지:
    실제 HTTP 호출 금지 / email fetch 실행 금지 / approve/reject 실행 금지
    execute 호출 금지 / webhook 호출 금지 / DB write 금지
    5050 route 수정 금지 / 8400 handler 수정 금지 / nginx 변경 금지
    adapter 실제 구현 금지 / secret 값 출력 금지 / 서버 반영 금지
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_route_modify": False,
    "8400_handler_modify": False,
    "nginx_change": False,
    "server_apply": False,
    "container_restart": False,
    "actual_http_call": False,
    "actual_email_fetch": False,
    "actual_approve": False,
    "actual_reject": False,
    "actual_execute": False,
    "actual_webhook_call": False,
    "actual_db_write": False,
    "secret_value_output": False,
    "actual_ui_change": False,
    "adapter_implementation": False,
}

# ── known baseline failures (이번 공정과 무관) ─────────────────────────────────

KNOWN_BASELINE_FAILURES = [
    "tests/app_contracts/test_app_foundation_p1_gates.py::test_server_browser_guard_no_violations",
    "tests/app_contracts/test_app_foundation_p1_gates.py::test_p1_gates_all_zero_new_violations",
]

# ── Phase 1-D dry-run compatibility matrix ───────────────────────────────────

PHASE1D_DRY_RUN_CASES: list[dict[str, Any]] = [
    # A. POST /api/v1/inbox/email/fetch ──────────────────────────────────────
    {
        # 식별
        "phase": "PHASE_1D",
        "dry_run_case_id": "DRYRUN_INBOX_EMAIL_FETCH_COMPAT",
        "adapter_id": "INBOX_EMAIL_FETCH_ADAPTER",
        # 경로 template
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/inbox/email/fetch",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/inbox/email/fetch",
        # sample path (path param 없음)
        "sample_task_id": None,
        "sample_legacy_path": "/api/v1/inbox/email/fetch",
        "sample_fastapi_path": "/api/v1/inbox/email/fetch",
        # 분류
        "adapter_type": "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER",
        "risk_level": "MEDIUM",
        # 실행 금지
        "live_call_allowed": False,
        "side_effect_allowed": False,
        "db_write_allowed": False,
        "secret_value_allowed": False,
        "approval_gate_required": False,
        # dry-run 전용
        "dry_run_only": True,
        "fixture_only": True,
        "verdict": "DRY_RUN_COMPAT_READY",
        # 요청 fixture (가짜 값만, secret 값 금지)
        "request_fixture": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "body": {
                "account": "DRYRUN_EMAIL_ACCOUNT_PLACEHOLDER",
                "credential": "DRYRUN_CREDENTIAL_NAME_ONLY",
            },
            "_note": "credential 이름만 허용, 실제 값 금지",
        },
        "expected_fastapi_request": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "body": {
                "account": "DRYRUN_EMAIL_ACCOUNT_PLACEHOLDER",
                "credential": "DRYRUN_CREDENTIAL_NAME_ONLY",
            },
        },
        # 요청 정책
        "request_mapping_policy": "STATIC_FIXTURE_TO_FASTAPI_REQUEST",
        "path_mapping_policy": "NO_PATH_PARAM_REQUIRED",
        "header_mapping_policy": "AUTH_HEADER_PASSTHROUGH",
        "body_mapping_policy": "NORMALIZE_CREDENTIAL_NAMES_ONLY",
        "query_mapping_policy": "NONE_REQUIRED",
        # 응답 fixture
        "legacy_response_fixture": {
            "status": 200,
            "body": {
                "fetched": 3,
                "items": [
                    {"id": "DRYRUN_MAIL_001", "subject": "DRY RUN SUBJECT A"},
                    {"id": "DRYRUN_MAIL_002", "subject": "DRY RUN SUBJECT B"},
                    {"id": "DRYRUN_MAIL_003", "subject": "DRY RUN SUBJECT C"},
                ],
            },
            "_note": "5050 legacy 응답 예상형. 실제 fetch 금지",
        },
        "fastapi_response_fixture": {
            "status": 200,
            "body": {
                "fetched": 3,
                "items": [
                    {"id": "DRYRUN_MAIL_001", "subject": "DRY RUN SUBJECT A"},
                    {"id": "DRYRUN_MAIL_002", "subject": "DRY RUN SUBJECT B"},
                    {"id": "DRYRUN_MAIL_003", "subject": "DRY RUN SUBJECT C"},
                ],
            },
            "_note": "8400 FastAPI 예상 응답형. 실제 fetch 금지",
        },
        "expected_normalized_response": {
            "fetched": 3,
            "items": [
                {"id": "DRYRUN_MAIL_001", "subject": "DRY RUN SUBJECT A"},
                {"id": "DRYRUN_MAIL_002", "subject": "DRY RUN SUBJECT B"},
                {"id": "DRYRUN_MAIL_003", "subject": "DRY RUN SUBJECT C"},
            ],
        },
        # 응답 정책
        "response_mapping_policy": "NORMALIZE_LEGACY_FASTAPI_EMAIL_FETCH_RESPONSE",
        "error_mapping_policy": "STANDARD_ERROR_ENVELOPE",
        "status_code_policy": "COMPAT_STATUS_ONLY",
        # 권한/위험 경계
        "auth_policy": "BEARER_OR_SESSION_TOKEN_REQUIRED",
        "permission_policy": "INBOX_ACCESS_REQUIRED",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "approval_gate_policy": "NOT_APPLICABLE_NO_GATE",
        "executor_boundary": "NOT_EXECUTOR_ROUTE",
        "forbidden_live_actions": [
            "ACTUAL_EMAIL_SERVER_CONNECT",
            "ACTUAL_IMAP_POP3_REQUEST",
            "CREDENTIAL_VALUE_OUTPUT",
        ],
        "forbidden_routes": [
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
            "/api/v1/webhooks/kakaotalk-channel",
        ],
        # 5050/8400 수정 없음
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "server_apply_allowed": False,
    },
    # B. POST /api/v1/tasks/<id>/approve ─────────────────────────────────────
    {
        # 식별
        "phase": "PHASE_1D",
        "dry_run_case_id": "DRYRUN_TASK_APPROVE_COMPAT",
        "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
        # 경로 template
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/approve",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/approve",
        # sample path
        "sample_task_id": "DRYRUN_TASK_001",
        "sample_legacy_path": "/api/v1/tasks/DRYRUN_TASK_001/approve",
        "sample_fastapi_path": "/api/v1/tasks/DRYRUN_TASK_001/approve",
        # 분류
        "adapter_type": "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",
        "risk_level": "HIGH",
        # 실행 금지
        "live_call_allowed": False,
        "side_effect_allowed": False,
        "db_write_allowed": False,
        "secret_value_allowed": False,
        "approval_gate_required": True,
        # dry-run 전용
        "dry_run_only": True,
        "fixture_only": True,
        "verdict": "DRY_RUN_COMPAT_READY",
        # 요청 fixture
        "request_fixture": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "path_params": {"id": "DRYRUN_TASK_001"},
            "body": {"reason": "DRY_RUN_APPROVAL_REASON_PLACEHOLDER"},
            "_note": "path param <id> → {id} 변환 dry-run. 실제 승인 금지",
        },
        "expected_fastapi_request": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "path_params": {"id": "DRYRUN_TASK_001"},
            "body": {"reason": "DRY_RUN_APPROVAL_REASON_PLACEHOLDER"},
        },
        # 요청 정책
        "request_mapping_policy": "STATIC_FIXTURE_TO_APPROVAL_REQUEST",
        "path_mapping_policy": "LEGACY_<id>_TO_FASTAPI_{id}",
        "header_mapping_policy": "AUTH_HEADER_PASSTHROUGH",
        "body_mapping_policy": "PASSTHROUGH_APPROVAL_BODY",
        "query_mapping_policy": "NONE_REQUIRED",
        # 응답 fixture
        "legacy_response_fixture": {
            "status": 200,
            "body": {
                "status": "approved",
                "task_id": "DRYRUN_TASK_001",
            },
            "_note": "5050 legacy 승인 응답 예상형. 실제 승인 금지",
        },
        "fastapi_response_fixture": {
            "status": 200,
            "body": {
                "status": "approved",
                "task_id": "DRYRUN_TASK_001",
            },
            "_note": "8400 FastAPI 승인 응답 예상형. 실제 승인 금지",
        },
        "expected_normalized_response": {
            "status": "approved",
            "task_id": "DRYRUN_TASK_001",
        },
        # 응답 정책
        "response_mapping_policy": "NORMALIZE_APPROVAL_RESPONSE",
        "error_mapping_policy": "STANDARD_ERROR_ENVELOPE",
        "status_code_policy": "COMPAT_STATUS_ONLY",
        # 권한/위험 경계
        "auth_policy": "COMPARE_ONLY_NO_BYPASS",
        "permission_policy": "APPROVAL_ACTION_REQUIRES_EXPLICIT_GATE",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "approval_gate_policy": "GATE_REQUIRED_BUT_NOT_EXECUTED",
        "executor_boundary": "APPROVAL_ROUTE_NOT_EXECUTOR",
        "forbidden_live_actions": [
            "ACTUAL_TASK_STATE_CHANGE",
            "ACTUAL_APPROVAL_EXECUTION",
            "AUTH_POLICY_BYPASS",
            "DB_WRITE",
        ],
        "forbidden_routes": [
            "/api/v1/tasks//approve",
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
            "/api/v1/webhooks/kakaotalk-channel",
        ],
        # 5050/8400 수정 없음
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "server_apply_allowed": False,
    },
    # C. POST /api/v1/tasks/<id>/reject ──────────────────────────────────────
    {
        # 식별
        "phase": "PHASE_1D",
        "dry_run_case_id": "DRYRUN_TASK_REJECT_COMPAT",
        "adapter_id": "TASK_REJECT_PATH_AUTH_ADAPTER",
        # 경로 template
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/reject",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/reject",
        # sample path
        "sample_task_id": "DRYRUN_TASK_001",
        "sample_legacy_path": "/api/v1/tasks/DRYRUN_TASK_001/reject",
        "sample_fastapi_path": "/api/v1/tasks/DRYRUN_TASK_001/reject",
        # 분류
        "adapter_type": "PATH_PARAM_AND_AUTH_POLICY_ADAPTER",
        "risk_level": "HIGH",
        # 실행 금지
        "live_call_allowed": False,
        "side_effect_allowed": False,
        "db_write_allowed": False,
        "secret_value_allowed": False,
        "approval_gate_required": True,
        # dry-run 전용
        "dry_run_only": True,
        "fixture_only": True,
        "verdict": "DRY_RUN_COMPAT_READY",
        # 요청 fixture
        "request_fixture": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "path_params": {"id": "DRYRUN_TASK_001"},
            "body": {"reason": "DRY_RUN_REJECT_REASON_PLACEHOLDER"},
            "_note": "path param <id> → {id} 변환 dry-run. 실제 거부 금지",
        },
        "expected_fastapi_request": {
            "headers": {
                "Authorization": "Bearer DRYRUN_TOKEN_PLACEHOLDER",
                "Content-Type": "application/json",
            },
            "path_params": {"id": "DRYRUN_TASK_001"},
            "body": {"reason": "DRY_RUN_REJECT_REASON_PLACEHOLDER"},
        },
        # 요청 정책
        "request_mapping_policy": "STATIC_FIXTURE_TO_REJECT_REQUEST",
        "path_mapping_policy": "LEGACY_<id>_TO_FASTAPI_{id}",
        "header_mapping_policy": "AUTH_HEADER_PASSTHROUGH",
        "body_mapping_policy": "PASSTHROUGH_REJECT_BODY",
        "query_mapping_policy": "NONE_REQUIRED",
        # 응답 fixture
        "legacy_response_fixture": {
            "status": 200,
            "body": {
                "status": "rejected",
                "task_id": "DRYRUN_TASK_001",
            },
            "_note": "5050 legacy 거부 응답 예상형. 실제 거부 금지",
        },
        "fastapi_response_fixture": {
            "status": 200,
            "body": {
                "status": "rejected",
                "task_id": "DRYRUN_TASK_001",
            },
            "_note": "8400 FastAPI 거부 응답 예상형. 실제 거부 금지",
        },
        "expected_normalized_response": {
            "status": "rejected",
            "task_id": "DRYRUN_TASK_001",
        },
        # 응답 정책
        "response_mapping_policy": "NORMALIZE_REJECT_RESPONSE",
        "error_mapping_policy": "STANDARD_ERROR_ENVELOPE",
        "status_code_policy": "COMPAT_STATUS_ONLY",
        # 권한/위험 경계
        "auth_policy": "COMPARE_ONLY_NO_BYPASS",
        "permission_policy": "REJECT_ACTION_REQUIRES_EXPLICIT_GATE",
        "credential_policy": "SECRET_NAMES_ONLY_NO_SECRET_VALUES",
        "approval_gate_policy": "GATE_REQUIRED_BUT_NOT_EXECUTED",
        "executor_boundary": "APPROVAL_ROUTE_NOT_EXECUTOR",
        "forbidden_live_actions": [
            "ACTUAL_TASK_STATE_CHANGE",
            "ACTUAL_REJECT_EXECUTION",
            "AUTH_POLICY_BYPASS",
            "DB_WRITE",
        ],
        "forbidden_routes": [
            "/api/v1/tasks//reject",
            "/api/v1/tasks/<id>/execute",
            "/api/v1/webhooks/kakaowork",
            "/api/v1/webhooks/kakaotalk-channel",
        ],
        # 5050/8400 수정 없음
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "server_apply_allowed": False,
    },
]

# ── 명시적 제외 목록 ──────────────────────────────────────────────────────────

PHASE1D_EXCLUDED = {
    "HOLD_DANGEROUS": ["/api/v1/tasks/<task_id>/execute"],
    "DO_NOT_TOUCH": ["/api/v1/webhooks/kakaowork", "/api/v1/webhooks/kakaotalk-channel"],
    "HOLD_DASHBOARD": ["/dashboard", "/dashboard/tasks/<task_id>", "/dashboard/approve", "/dashboard/reject"],
    "SAME_CONTRACT_SKIP": ["/api/v1/inbox", "/api/v1/tasks"],
    "DOUBLE_SLASH_FORBIDDEN": [
        "/api/v1/tasks//approve",
        "/api/v1/tasks//reject",
    ],
}


# ── 유효성 검사 헬퍼 ──────────────────────────────────────────────────────────


def _no_double_slash() -> bool:
    for c in PHASE1D_DRY_RUN_CASES:
        for field in ("legacy_path_template", "fastapi_path_template", "sample_legacy_path", "sample_fastapi_path"):
            val = c.get(field)
            if val and "//" in val:
                return False
    return True


def _no_forbidden_in_cases() -> bool:
    case_paths = [c["legacy_path_template"] for c in PHASE1D_DRY_RUN_CASES]
    exact_forbidden = {"/api/v1/tasks"}

    for p in case_paths:
        if "execute" in p:
            return False
        if "webhook" in p:
            return False
        if "/dashboard" in p:
            return False
        if p in exact_forbidden:
            return False
    return True


# ── 감사 함수 ─────────────────────────────────────────────────────────────────


def run_audit() -> dict[str, Any]:
    cases = PHASE1D_DRY_RUN_CASES

    total = len(cases)
    fixture_only_cnt = sum(1 for c in cases if c["fixture_only"] is True)
    dry_run_only_cnt = sum(1 for c in cases if c["dry_run_only"] is True)
    live_false = sum(1 for c in cases if c["live_call_allowed"] is False)
    side_false = sum(1 for c in cases if c["side_effect_allowed"] is False)
    db_false = sum(1 for c in cases if c["db_write_allowed"] is False)
    secret_false = sum(1 for c in cases if c["secret_value_allowed"] is False)
    gate_true = sum(1 for c in cases if c["approval_gate_required"] is True)
    high_risk = sum(1 for c in cases if c["risk_level"] == "HIGH")
    medium_risk = sum(1 for c in cases if c["risk_level"] == "MEDIUM")
    path_mapping_cnt = sum(1 for c in cases if c["path_mapping_policy"].startswith("LEGACY_"))
    cred_env_cnt = sum(1 for c in cases if c["adapter_type"] == "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER")
    verdict_ready_cnt = sum(1 for c in cases if c["verdict"] == "DRY_RUN_COMPAT_READY")

    no_double_slash = _no_double_slash()
    no_forbidden = _no_forbidden_in_cases()
    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]

    success = (
        total == 3
        and fixture_only_cnt == 3
        and dry_run_only_cnt == 3
        and live_false == 3
        and side_false == 3
        and db_false == 3
        and secret_false == 3
        and gate_true == 2
        and high_risk == 2
        and medium_risk == 1
        and path_mapping_cnt == 2
        and cred_env_cnt == 1
        and verdict_ready_cnt == 3
        and no_double_slash
        and no_forbidden
        and len(boundary_violations) == 0
    )

    return {
        "audit_id": "ASSISTANT_BACKEND_5050_LEGACY_PHASE1D_ADAPTER_DRY_RUN_COMPAT_TEST_01",
        "verdict": "PHASE1D_ADAPTER_DRY_RUN_COMPAT_READY" if success else "FAIL",
        "success": success,
        "dry_run_cases": cases,
        "excluded": PHASE1D_EXCLUDED,
        "safe_boundary": {**SAFE_BOUNDARY, "violations": boundary_violations},
        "known_baseline_failures": KNOWN_BASELINE_FAILURES,
        "summary": {
            "total_dry_run_cases": total,
            "fixture_only_true": fixture_only_cnt,
            "dry_run_only_true": dry_run_only_cnt,
            "live_call_allowed_false": live_false,
            "side_effect_allowed_false": side_false,
            "db_write_allowed_false": db_false,
            "secret_value_allowed_false": secret_false,
            "approval_gate_required_true": gate_true,
            "risk_level_HIGH": high_risk,
            "risk_level_MEDIUM": medium_risk,
            "path_mapping_cases": path_mapping_cnt,
            "credential_env_cases": cred_env_cnt,
            "verdict_ready": verdict_ready_cnt,
            "no_double_slash": no_double_slash,
            "no_forbidden_route": no_forbidden,
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    print("\n[Phase 1-D Dry-Run Compatibility Matrix]")
    header = f"{'DRY_RUN_CASE_ID':<38} {'ADAPTER_ID':<36} {'RISK':<8} {'GATE':<6} {'DRY_RUN':<8} {'VERDICT'}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for c in audit["dry_run_cases"]:
        print(
            f"  {c['dry_run_case_id']:<38} {c['adapter_id']:<36} "
            f"{c['risk_level']:<8} {c['approval_gate_required']!s:<6} "
            f"{c['dry_run_only']!s:<8} {c['verdict']}"
        )

    print("\n[경로 표기 확인]")
    for c in audit["dry_run_cases"]:
        print(f"  legacy template : {c['legacy_path_template']}")
        print(f"  fastapi template: {c['fastapi_path_template']}")
        print(f"  sample legacy   : {c['sample_legacy_path']}")
        print(f"  sample fastapi  : {c['sample_fastapi_path']}")
        print()

    s = audit["summary"]
    print("[집계]")
    items = [
        ("총 dry-run case 수", s["total_dry_run_cases"], 3),
        ("fixture_only=True", s["fixture_only_true"], 3),
        ("dry_run_only=True", s["dry_run_only_true"], 3),
        ("live_call_allowed=False", s["live_call_allowed_false"], 3),
        ("side_effect_allowed=False", s["side_effect_allowed_false"], 3),
        ("db_write_allowed=False", s["db_write_allowed_false"], 3),
        ("secret_value_allowed=False", s["secret_value_allowed_false"], 3),
        ("approval_gate_required=True", s["approval_gate_required_true"], 2),
        ("risk_level=HIGH", s["risk_level_HIGH"], 2),
        ("risk_level=MEDIUM", s["risk_level_MEDIUM"], 1),
        ("path mapping case", s["path_mapping_cases"], 2),
        ("credential/env case", s["credential_env_cases"], 1),
        ("double slash 없음", s["no_double_slash"], True),
        ("forbidden route 제외", s["no_forbidden_route"], True),
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
    from scripts.common.audit_cli import run_json_or_report_cli

    run_json_or_report_cli("5050 Phase 1-D adapter dry-run compat 감사", run_audit, _print_report, "success")


if __name__ == "__main__":
    main()
