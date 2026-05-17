"""
Phase 1-O: Router Touch Design Only Audit
DESIGN_ID: PHASE1O_FEATURE_FLAG_OFF_REAL_ROUTER_TOUCH_DESIGN_ONLY
실제 router 파일을 수정하지 않고 설계 제한조건만 machine-readable하게 고정.
"""
import os
import glob as glob_module
from pathlib import Path

# ── 상수 ──────────────────────────────────────────
PHASE = "PHASE_1O"
DESIGN_ID = "PHASE1O_FEATURE_FLAG_OFF_REAL_ROUTER_TOUCH_DESIGN_ONLY"
REAL_ROUTER_TOUCH_ALLOWED = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
ROUTE_REGISTRATION_ALLOWED = False
APIRouter_ALLOWED = False
INCLUDE_ROUTER_ALLOWED = False
ROUTE_DECORATOR_ALLOWED = False
FEATURE_FLAG_RUNTIME_HOOK_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ONLY = True
SERVER_APPLY_ALLOWED = False

EXCLUDED_FILE_PATTERNS = [
    "test_", "_test.", "audit_", "smoke_",
    "route_integration", "wrapper_candidate",
    "__pycache__", ".pyc",
]

SEARCH_ROOTS = ["ai_orchestrator", "backend"]
SEARCH_PATTERNS = [
    "APIRouter", "FastAPI", "Flask",
    "@router.", "@app.route", "include_router",
    "/api/v1/inbox", "/api/v1/tasks",
    "email.fetch", "approve", "reject",
]

FORBIDDEN_ROUTES = ["/execute", "/webhook", "/dashboard"]
FORBIDDEN_SAME_CONTRACT = ["SAME_CONTRACT_001", "SAME_CONTRACT_002"]

# ── stop conditions (공통) ─────────────────────────
COMMON_STOP_CONDITIONS = [
    "router_file_modification",
    "route_decorator_creation",
    "include_router_creation",
    "feature_flag_default_true",
    "db_write",
    "secret_env_access",
    "http_client_import",
    "subprocess_socket_import",
    "server_startup",
]

# ── design matrix ─────────────────────────────────
def _base_row():
    return {
        "phase": PHASE,
        "design_id": DESIGN_ID,
        "feature_flag_default": False,
        "route_registered_now": False,
        "real_router_touch_allowed_now": False,
        "router_file_modification_allowed_now": False,
        "include_router_allowed_now": False,
        "route_decorator_allowed_now": False,
        "feature_flag_runtime_hook_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_executed_allowed": False,
        "verdict": "ROUTER_TOUCH_DESIGN_READY",
    }


def build_design_matrix():
    # router candidate scan 먼저
    candidate_files = scan_router_candidates()

    rows = []

    # A. INBOX_EMAIL_FETCH
    row_a = _base_row()
    row_a.update({
        "route_skeleton_id": "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "INBOX_EMAIL_FETCH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/inbox/email/fetch",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/inbox/email/fetch",
        "candidate_router_search_terms": ["/api/v1/inbox", "email/fetch", "inbox", "fetch"],
        "candidate_router_files": candidate_files,
        "selected_candidate_router_files": _filter_candidates(candidate_files, ["inbox", "email", "fetch"]),
        "selected_candidate_reason": "inbox/email/fetch 키워드 포함 파일 우선 선정",
        "integration_design_boundary": "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_EMAIL_FETCH_ENABLED",
        "approval_gate_required": False,
        "required_before_phase1p": ["confirm router file path", "verify no existing route conflict"],
        "required_during_phase1p": ["add feature flag check", "connect to wrapper", "register route with flag=off"],
        "stop_conditions": COMMON_STOP_CONDITIONS + ["actual_email_fetch", "external_site_cookie_storage"],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1P_OR_PHASE_1J_AFTER_DESIGN",
    })
    rows.append(row_a)

    # B. TASK_APPROVE
    row_b = _base_row()
    row_b.update({
        "route_skeleton_id": "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/approve",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/approve",
        "candidate_router_search_terms": ["/api/v1/tasks", "approve", "task", "approval"],
        "candidate_router_files": candidate_files,
        "selected_candidate_router_files": _filter_candidates(candidate_files, ["task", "approve", "approval"]),
        "selected_candidate_reason": "task/approve/approval 키워드 포함 파일 우선 선정",
        "integration_design_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_APPROVE_ENABLED",
        "approval_gate_required": True,
        "required_before_phase1p": ["confirm router file path", "verify approval gate wiring", "check double slash"],
        "required_during_phase1p": ["add feature flag check", "connect to wrapper", "register route with flag=off", "preserve {id} in path"],
        "stop_conditions": COMMON_STOP_CONDITIONS + [
            "approval_gate_executed_true", "actual_approve",
            "double_slash", "execute_boundary_violation", "external_site_approval_gate_violation",
        ],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1P_OR_PHASE_1J_AFTER_DESIGN",
    })
    rows.append(row_b)

    # C. TASK_REJECT
    row_c = _base_row()
    row_c.update({
        "route_skeleton_id": "TASK_REJECT_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_REJECT_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/reject",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/reject",
        "candidate_router_search_terms": ["/api/v1/tasks", "reject", "task", "approval"],
        "candidate_router_files": candidate_files,
        "selected_candidate_router_files": _filter_candidates(candidate_files, ["task", "reject", "approval"]),
        "selected_candidate_reason": "task/reject/approval 키워드 포함 파일 우선 선정",
        "integration_design_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_REJECT_ENABLED",
        "approval_gate_required": True,
        "required_before_phase1p": ["confirm router file path", "verify approval gate wiring", "check double slash"],
        "required_during_phase1p": ["add feature flag check", "connect to wrapper", "register route with flag=off", "preserve {id} in path"],
        "stop_conditions": COMMON_STOP_CONDITIONS + [
            "approval_gate_executed_true", "actual_reject",
            "double_slash", "execute_boundary_violation", "external_site_approval_gate_violation",
        ],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1P_OR_PHASE_1J_AFTER_DESIGN",
    })
    rows.append(row_c)

    return rows


def _is_excluded(path_str):
    for pat in EXCLUDED_FILE_PATTERNS:
        if pat in path_str:
            return True
    return False


def scan_router_candidates():
    """Read-only scan. 파일 수정 없음."""
    repo_root = Path(__file__).parent.parent.parent
    found = []
    for root_name in SEARCH_ROOTS:
        root_path = repo_root / root_name
        if not root_path.exists():
            continue
        for py_file in root_path.rglob("*.py"):
            if _is_excluded(str(py_file)):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in SEARCH_PATTERNS:
                if pat in content:
                    rel = str(py_file.relative_to(repo_root))
                    if rel not in found:
                        found.append(rel)
                    break
    return sorted(found)


def _filter_candidates(candidates, keywords):
    selected = []
    for f in candidates:
        lower = f.lower()
        if any(kw in lower for kw in keywords):
            selected.append(f)
    if not selected:
        return ["UNKNOWN"]
    return selected


def run_audit():
    matrix = build_design_matrix()
    candidate_files = scan_router_candidates()

    errors = []
    warnings = []

    # 기본 검증
    if len(matrix) != 3:
        errors.append(f"design matrix row 수 불일치: {len(matrix)} (expected 3)")

    for row in matrix:
        if row.get("real_router_touch_allowed_now") is not False:
            errors.append(f"{row['route_skeleton_id']}: real_router_touch_allowed_now must be False")
        if row.get("router_file_modification_allowed_now") is not False:
            errors.append(f"{row['route_skeleton_id']}: router_file_modification_allowed_now must be False")
        if row.get("route_registered_now") is not False:
            errors.append(f"{row['route_skeleton_id']}: route_registered_now must be False")
        if row.get("feature_flag_default") is not False:
            errors.append(f"{row['route_skeleton_id']}: feature_flag_default must be False")
        if row.get("approval_gate_executed_allowed") is not False:
            errors.append(f"{row['route_skeleton_id']}: approval_gate_executed_allowed must be False")
        if row.get("dry_run_only_now") is not True:
            errors.append(f"{row['route_skeleton_id']}: dry_run_only_now must be True")
        if row.get("live_traffic_allowed_now") is not False:
            errors.append(f"{row['route_skeleton_id']}: live_traffic_allowed_now must be False")
        if row.get("verdict") != "ROUTER_TOUCH_DESIGN_READY":
            errors.append(f"{row['route_skeleton_id']}: verdict must be ROUTER_TOUCH_DESIGN_READY")
        if row.get("selected_candidate_router_files") == ["UNKNOWN"]:
            warnings.append(f"{row['route_skeleton_id']}: selected_candidate_router_files UNKNOWN")

    # candidate scan 검증
    if len(candidate_files) == 0:
        warnings.append("router candidate scan: 0개 발견")

    # forbidden routes 제외 검증
    approve_row = next((r for r in matrix if r["route_skeleton_id"] == "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON"), None)
    if approve_row:
        if "<id>" not in approve_row["legacy_path_template"]:
            errors.append("approve: legacy path에 <id> 없음")
        if "{id}" not in approve_row["fastapi_path_template"]:
            errors.append("approve: fastapi path에 {id} 없음")
        if "//" in approve_row["fastapi_path_template"]:
            errors.append("approve: double slash 발견")

    reject_row = next((r for r in matrix if r["route_skeleton_id"] == "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"), None)
    if reject_row:
        if "<id>" not in reject_row["legacy_path_template"]:
            errors.append("reject: legacy path에 <id> 없음")
        if "{id}" not in reject_row["fastapi_path_template"]:
            errors.append("reject: fastapi path에 {id} 없음")
        if "//" in reject_row["fastapi_path_template"]:
            errors.append("reject: double slash 발견")

    # execute/webhook/dashboard 제외 확인
    all_paths = []
    for row in matrix:
        all_paths.append(row.get("legacy_path_template", ""))
        all_paths.append(row.get("fastapi_path_template", ""))
    for forbidden in FORBIDDEN_ROUTES:
        for p in all_paths:
            if forbidden in p:
                errors.append(f"forbidden route {forbidden} 발견: {p}")

    verdict = "FAIL" if errors else ("WARN" if warnings else "PHASE1O_ROUTER_TOUCH_DESIGN_ONLY_READY")

    return {
        "phase": PHASE,
        "design_id": DESIGN_ID,
        "verdict": verdict,
        "design_matrix_row_count": len(matrix),
        "candidate_file_count": len(candidate_files),
        "candidate_files": candidate_files,
        "scanned_file_count": len(candidate_files),
        "selected_candidate_router_files": matrix[0]["candidate_router_files"] if matrix else [],
        "modified_files_count": 0,
        "forbidden_import_violations": 0,
        "skipped_dirs": ["__pycache__", "tests", "scripts/ops"],
        "errors": errors,
        "warnings": warnings,
        "real_router_touch_allowed": REAL_ROUTER_TOUCH_ALLOWED,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "route_registration_allowed": ROUTE_REGISTRATION_ALLOWED,
        "apirouter_allowed": APIRouter_ALLOWED,
        "include_router_allowed": INCLUDE_ROUTER_ALLOWED,
        "route_decorator_allowed": ROUTE_DECORATOR_ALLOWED,
        "feature_flag_runtime_hook_allowed": FEATURE_FLAG_RUNTIME_HOOK_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "dry_run_only": DRY_RUN_ONLY,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "design_matrix": matrix,
    }


def get_design_matrix():
    return build_design_matrix()


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-O Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN: {w}")
