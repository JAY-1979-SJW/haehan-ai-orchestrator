"""
Phase 1-K: Wrapper Route Integration Preflight Audit
이 스크립트는 wrapper candidate를 실제 route에 연결하기 전
정적 감리표를 생성하고 검증한다. 실제 route 연결 없음.
"""

import os
import ast
import sys
from pathlib import Path

# ──────────────────────────────────────────────
# 전역 상수
# ──────────────────────────────────────────────

PHASE = "PHASE_1K"
PREFLIGHT_ID = "PHASE1K_WRAPPER_ROUTE_INTEGRATION_PREFLIGHT"
INTEGRATION_ALLOWED = False
ROUTE_FILE_CHANGE_ALLOWED = False
ROUTER_IMPORT_ALLOWED = False
FEATURE_FLAG_RUNTIME_HOOK_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ONLY = True

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ──────────────────────────────────────────────
# Preflight Matrix
# ──────────────────────────────────────────────

PREFLIGHT_MATRIX = [
    {
        "phase": PHASE,
        "preflight_id": PREFLIGHT_ID,
        "wrapper_id": "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "INBOX_EMAIL_FETCH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/inbox/email/fetch",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/inbox/email/fetch",
        "wrapper_module": "backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate",
        "wrapper_function": "inbox_email_fetch_wrapper_candidate",
        "proposed_future_integration_point": "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY",
        "proposed_future_route_boundary": "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_connected_now": False,
        "integration_allowed_now": False,
        "router_import_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": False,
        "approval_gate_executed_allowed": False,
        "rollback_required": True,
        "required_pre_integration_checks": [
            "feature_flag_default_false_confirmed",
            "no_route_import_confirmed",
            "no_http_client_import_confirmed",
            "no_db_client_import_confirmed",
            "no_secret_env_access_confirmed",
            "dry_run_smoke_14_14_confirmed",
        ],
        "required_post_integration_checks": [
            "feature_flag_still_false_after_connect",
            "no_live_traffic_activated",
            "rollback_plan_verified",
        ],
        "stop_conditions": [
            "feature_flag_default_true_발견_시_STOP",
            "route_import_발생_시_STOP",
            "http_client_import_발생_시_STOP",
            "db_client_import_발생_시_STOP",
            "secret_env_value_접근_발생_시_STOP",
            "actual_email_fetch_발생_시_STOP",
        ],
        "forbidden_routes": [
            "/api/v1/tasks/execute",
            "/api/v1/webhook",
            "/api/v1/dashboard",
            "/api/v1/tasks//approve",
            "/api/v1/tasks//reject",
        ],
        "forbidden_files": [
            "routers/",
            "routes/",
            "services/",
            "usecases/",
        ],
        "next_phase": "PHASE_1L_OR_PHASE_1J_AFTER_PREFLIGHT",
        "verdict": "PREFLIGHT_READY",
    },
    {
        "phase": PHASE,
        "preflight_id": PREFLIGHT_ID,
        "wrapper_id": "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/approve",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/approve",
        "wrapper_module": "backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate",
        "wrapper_function": "task_approve_wrapper_candidate",
        "proposed_future_integration_point": "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY",
        "proposed_future_route_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_connected_now": False,
        "integration_allowed_now": False,
        "router_import_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": True,
        "approval_gate_executed_allowed": False,
        "rollback_required": True,
        "required_pre_integration_checks": [
            "feature_flag_default_false_confirmed",
            "no_route_import_confirmed",
            "no_db_write_confirmed",
            "approval_gate_executed_false_confirmed",
            "no_execute_boundary_violation",
            "no_double_slash_path",
        ],
        "required_post_integration_checks": [
            "feature_flag_still_false_after_connect",
            "no_live_traffic_activated",
            "rollback_plan_verified",
            "approval_gate_not_auto_executed",
        ],
        "stop_conditions": [
            "feature_flag_default_true_발견_시_STOP",
            "route_import_발생_시_STOP",
            "approval_gate_executed_true_발생_시_STOP",
            "actual_approve_발생_시_STOP",
            "db_write_발생_시_STOP",
            "secret_env_value_접근_발생_시_STOP",
            "double_slash_생성_시_STOP",
            "execute_boundary_침범_시_STOP",
        ],
        "forbidden_routes": [
            "/api/v1/tasks/execute",
            "/api/v1/webhook",
            "/api/v1/dashboard",
            "/api/v1/tasks//approve",
            "/api/v1/tasks//reject",
        ],
        "forbidden_files": [
            "routers/",
            "routes/",
            "services/",
            "usecases/",
        ],
        "next_phase": "PHASE_1L_OR_PHASE_1J_AFTER_PREFLIGHT",
        "verdict": "PREFLIGHT_READY",
    },
    {
        "phase": PHASE,
        "preflight_id": PREFLIGHT_ID,
        "wrapper_id": "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_REJECT_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/reject",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/reject",
        "wrapper_module": "backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate",
        "wrapper_function": "task_reject_wrapper_candidate",
        "proposed_future_integration_point": "FASTAPI_ROUTE_WRAPPER_CANDIDATE_ONLY",
        "proposed_future_route_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_connected_now": False,
        "integration_allowed_now": False,
        "router_import_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": True,
        "approval_gate_executed_allowed": False,
        "rollback_required": True,
        "required_pre_integration_checks": [
            "feature_flag_default_false_confirmed",
            "no_route_import_confirmed",
            "no_db_write_confirmed",
            "approval_gate_executed_false_confirmed",
            "no_execute_boundary_violation",
            "no_double_slash_path",
        ],
        "required_post_integration_checks": [
            "feature_flag_still_false_after_connect",
            "no_live_traffic_activated",
            "rollback_plan_verified",
            "approval_gate_not_auto_executed",
        ],
        "stop_conditions": [
            "feature_flag_default_true_발견_시_STOP",
            "route_import_발생_시_STOP",
            "approval_gate_executed_true_발생_시_STOP",
            "actual_reject_발생_시_STOP",
            "db_write_발생_시_STOP",
            "secret_env_value_접근_발생_시_STOP",
            "double_slash_생성_시_STOP",
            "execute_boundary_침범_시_STOP",
        ],
        "forbidden_routes": [
            "/api/v1/tasks/execute",
            "/api/v1/webhook",
            "/api/v1/dashboard",
            "/api/v1/tasks//approve",
            "/api/v1/tasks//reject",
        ],
        "forbidden_files": [
            "routers/",
            "routes/",
            "services/",
            "usecases/",
        ],
        "next_phase": "PHASE_1L_OR_PHASE_1J_AFTER_PREFLIGHT",
        "verdict": "PREFLIGHT_READY",
    },
]

# ──────────────────────────────────────────────
# 정적 route import scan
# ──────────────────────────────────────────────

SCAN_DIRS = [
    "backend",
    "ai_orchestrator",
    "app",
    "routers",
    "routes",
    "services",
    "usecases",
]

FORBIDDEN_PATTERNS = [
    "legacy_5050.wrappers",
    "inbox_email_fetch_wrapper_candidate",
    "task_approval_wrapper_candidate",
    "inbox_email_fetch_wrapper_candidate(",
    "task_approve_wrapper_candidate(",
    "task_reject_wrapper_candidate(",
]

ALLOWED_PATHS_CONTAINING = [
    "wrappers",
    "route_integration",  # Phase 1-L designated wrapper consumer layer
    "tests",
    "scripts/ops/audit_",
    "scripts/ops/smoke_",
    "scripts\\ops\\audit_",
    "scripts\\ops\\smoke_",
]


def _is_allowed_path(filepath: str) -> bool:
    fp = filepath.replace("\\", "/")
    for allowed in ALLOWED_PATHS_CONTAINING:
        if allowed.replace("\\", "/") in fp:
            return True
    return False


def run_static_route_import_scan() -> dict:
    results = {
        "scanned_dirs": [],
        "skipped_missing_dirs": [],
        "violations": [],
        "allowed_occurrences": [],
        "verdict": "PASS",
    }

    for scan_dir in SCAN_DIRS:
        dirpath = REPO_ROOT / scan_dir
        if not dirpath.exists():
            results["skipped_missing_dirs"].append(scan_dir)
            continue
        results["scanned_dirs"].append(scan_dir)
        for py_file in dirpath.rglob("*.py"):
            rel = str(py_file.relative_to(REPO_ROOT))
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in content:
                    if _is_allowed_path(rel):
                        results["allowed_occurrences"].append(
                            {"file": rel, "pattern": pattern}
                        )
                    else:
                        results["violations"].append(
                            {"file": rel, "pattern": pattern}
                        )

    if results["violations"]:
        results["verdict"] = "FAIL"
    return results


# ──────────────────────────────────────────────
# 검증 함수
# ──────────────────────────────────────────────

def validate_matrix() -> list[str]:
    errors = []

    if len(PREFLIGHT_MATRIX) != 3:
        errors.append(f"preflight row 수 오류: {len(PREFLIGHT_MATRIX)} (expected 3)")

    expected_ids = {
        "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE",
        "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE",
    }
    actual_ids = {r["wrapper_id"] for r in PREFLIGHT_MATRIX}
    if actual_ids != expected_ids:
        errors.append(f"wrapper_id 불일치: {actual_ids}")

    for row in PREFLIGHT_MATRIX:
        wid = row["wrapper_id"]
        if row["feature_flag_default"] is not False:
            errors.append(f"{wid}: feature_flag_default != false")
        if row["route_connected_now"] is not False:
            errors.append(f"{wid}: route_connected_now != false")
        if row["integration_allowed_now"] is not False:
            errors.append(f"{wid}: integration_allowed_now != false")
        if row["router_import_allowed_now"] is not False:
            errors.append(f"{wid}: router_import_allowed_now != false")
        if row["live_traffic_allowed_now"] is not False:
            errors.append(f"{wid}: live_traffic_allowed_now != false")
        if row["dry_run_only_now"] is not True:
            errors.append(f"{wid}: dry_run_only_now != true")
        if row["approval_gate_executed_allowed"] is not False:
            errors.append(f"{wid}: approval_gate_executed_allowed != false")
        if row["rollback_required"] is not True:
            errors.append(f"{wid}: rollback_required != true")
        if row["verdict"] != "PREFLIGHT_READY":
            errors.append(f"{wid}: verdict != PREFLIGHT_READY")

        # double slash
        for path in [row["legacy_path_template"], row["fastapi_path_template"]]:
            if "//" in path:
                errors.append(f"{wid}: double slash in path: {path}")

        # /execute 제외
        for fr in row["forbidden_routes"]:
            if "execute" not in " ".join(row["forbidden_routes"]):
                errors.append(f"{wid}: /execute not in forbidden_routes")
                break

    # approval_gate_required: approve/reject만 true
    inbox = next(r for r in PREFLIGHT_MATRIX if r["wrapper_id"] == "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE")
    approve = next(r for r in PREFLIGHT_MATRIX if r["wrapper_id"] == "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE")
    reject = next(r for r in PREFLIGHT_MATRIX if r["wrapper_id"] == "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE")

    if inbox["approval_gate_required"] is not False:
        errors.append("INBOX approval_gate_required should be false")
    if approve["approval_gate_required"] is not True:
        errors.append("APPROVE approval_gate_required should be true")
    if reject["approval_gate_required"] is not True:
        errors.append("REJECT approval_gate_required should be true")

    return errors


def get_overall_verdict(matrix_errors: list, scan_result: dict) -> str:
    if matrix_errors:
        return "FAIL"
    if scan_result["verdict"] == "FAIL":
        return "FAIL"
    return "PHASE1K_WRAPPER_ROUTE_INTEGRATION_PREFLIGHT_READY"


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────

def main():
    print(f"[{PHASE}] {PREFLIGHT_ID}")
    print(f"  INTEGRATION_ALLOWED          : {INTEGRATION_ALLOWED}")
    print(f"  ROUTE_FILE_CHANGE_ALLOWED    : {ROUTE_FILE_CHANGE_ALLOWED}")
    print(f"  ROUTER_IMPORT_ALLOWED        : {ROUTER_IMPORT_ALLOWED}")
    print(f"  FEATURE_FLAG_RUNTIME_HOOK    : {FEATURE_FLAG_RUNTIME_HOOK_ALLOWED}")
    print(f"  SERVER_APPLY_ALLOWED         : {SERVER_APPLY_ALLOWED}")
    print(f"  LIVE_TRAFFIC_ALLOWED         : {LIVE_TRAFFIC_ALLOWED}")
    print(f"  DRY_RUN_ONLY                 : {DRY_RUN_ONLY}")
    print()

    # matrix 검증
    matrix_errors = validate_matrix()
    print(f"[matrix] preflight row 수: {len(PREFLIGHT_MATRIX)}")
    for row in PREFLIGHT_MATRIX:
        print(f"  {row['wrapper_id']}: verdict={row['verdict']}")
    if matrix_errors:
        print(f"  [FAIL] matrix errors: {matrix_errors}")
    else:
        print("  [PASS] matrix validation")
    print()

    # static scan
    scan = run_static_route_import_scan()
    print(f"[static_scan] scanned: {scan['scanned_dirs']}")
    print(f"  skipped (missing): {scan['skipped_missing_dirs']}")
    print(f"  allowed_occurrences: {len(scan['allowed_occurrences'])}")
    print(f"  violations: {len(scan['violations'])}")
    if scan["violations"]:
        for v in scan["violations"]:
            print(f"    VIOLATION: {v['file']} pattern={v['pattern']}")
    print(f"  scan verdict: {scan['verdict']}")
    print()

    verdict = get_overall_verdict(matrix_errors, scan)
    print(f"[OVERALL] {verdict}")

    if verdict != "PHASE1K_WRAPPER_ROUTE_INTEGRATION_PREFLIGHT_READY":
        sys.exit(1)


if __name__ == "__main__":
    main()
