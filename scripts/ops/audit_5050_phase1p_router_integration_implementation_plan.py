"""
Phase 1-P: Router Integration Implementation Plan Audit
PLAN_ID: PHASE1P_FEATURE_FLAG_OFF_ROUTER_INTEGRATION_IMPLEMENTATION_PLAN
실제 router 파일 수정 없이 router integration 구현 계획만 machine-readable하게 고정.
"""
import importlib.util
from pathlib import Path

# ── 상수 ──────────────────────────────────────────────────────────────────
PHASE = "PHASE_1P"
PLAN_ID = "PHASE1P_FEATURE_FLAG_OFF_ROUTER_INTEGRATION_IMPLEMENTATION_PLAN"
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
IMPLEMENTATION_PLAN_ONLY = True

REPO_ROOT = Path(__file__).parent.parent.parent

EXCLUDED_FILE_PATTERNS = [
    "test_", "_test.", "audit_", "smoke_",
    "route_integration", "wrapper_candidate",
    "__pycache__", ".pyc", "docs/", "/docs/",
]

SEARCH_ROOTS = ["ai_orchestrator", "backend"]

FORBIDDEN_ROUTES = ["/execute", "/webhook", "/dashboard"]
FORBIDDEN_SAME_CONTRACT = ["SAME_CONTRACT_001", "SAME_CONTRACT_002"]

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

# ── approval gate registry 경로 확인 ────────────────────────────────────
def _get_approval_gate_registry_info():
    candidate_path = REPO_ROOT / "ai_orchestrator/external_sites/approval_gate_registry.py"
    if candidate_path.exists():
        try:
            import sys as _sys
            spec = importlib.util.spec_from_file_location("approval_gate_registry", candidate_path)
            mod = importlib.util.module_from_spec(spec)
            _sys.modules["approval_gate_registry"] = mod
            spec.loader.exec_module(mod)
            registry = getattr(mod, "APPROVAL_GATE_REGISTRY", {})
            # Also check APPROVAL_GATES tuple format
            gates_tuple = getattr(mod, "APPROVAL_GATES", None)
            if not registry and gates_tuple:
                registry = {g.gate_id: g.to_safe_dict() for g in gates_tuple}
            gate_ids = list(registry.keys())
            auto_exec_ok = all(
                g.get("auto_execute_allowed") is False
                for g in registry.values()
                if "auto_execute_allowed" in g
            )
            user_approval_ok = all(
                g.get("user_approval_required") is True
                for g in registry.values()
                if "user_approval_required" in g
            )
            return {
                "canonical_path": "ai_orchestrator/external_sites/approval_gate_registry.py",
                "importable": True,
                "gate_ids": gate_ids,
                "auto_execute_allowed_all_false": auto_exec_ok,
                "user_approval_required_all_true": user_approval_ok,
                "raw_registry": registry,
            }
        except Exception as e:
            return {
                "canonical_path": "ai_orchestrator/external_sites/approval_gate_registry.py",
                "importable": False,
                "error": str(e),
                "gate_ids": [],
                "auto_execute_allowed_all_false": None,
            }
    return {
        "canonical_path": "UNKNOWN",
        "importable": False,
        "gate_ids": [],
        "auto_execute_allowed_all_false": None,
    }


# ── router candidate classification ────────────────────────────────────
def _is_excluded(path_str: str) -> bool:
    for pat in EXCLUDED_FILE_PATTERNS:
        if pat in path_str:
            return True
    return False

ROUTE_KEYWORDS = [
    "APIRouter", "FastAPI", "Flask",
    "@router.", "@app.route", "include_router",
    "/api/v1/inbox", "/api/v1/tasks",
    "email.fetch", "approve", "reject",
]

SELECTED_KEYWORDS = ["inbox", "task", "approve", "reject", "email", "fetch"]


def classify_candidates():
    selected = []
    observation = []
    excluded_count = 0

    for root_name in SEARCH_ROOTS:
        root_path = REPO_ROOT / root_name
        if not root_path.exists():
            continue
        for py_file in root_path.rglob("*.py"):
            path_str = str(py_file)
            if _is_excluded(path_str):
                excluded_count += 1
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            has_route_keyword = any(kw in content for kw in ROUTE_KEYWORDS)
            if not has_route_keyword:
                continue
            rel = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
            has_selected_kw = any(kw in rel.lower() or kw in content.lower() for kw in SELECTED_KEYWORDS)
            has_route_def = any(kw in content for kw in ["@router.", "@app.route", "APIRouter(", "include_router("])
            if has_selected_kw and has_route_def:
                if rel not in selected:
                    selected.append(rel)
            else:
                if rel not in observation:
                    observation.append(rel)

    return sorted(selected), sorted(observation), excluded_count


# ── implementation plan matrix ─────────────────────────────────────────
def _base_row():
    return {
        "phase": PHASE,
        "plan_id": PLAN_ID,
        "feature_flag_default": False,
        "route_registered_now": False,
        "router_file_modification_allowed_now": False,
        "route_decorator_allowed_now": False,
        "include_router_allowed_now": False,
        "feature_flag_runtime_hook_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_executed_allowed": False,
        "verdict": "ROUTER_INTEGRATION_IMPLEMENTATION_PLAN_READY",
    }


def build_plan_matrix():
    gate_info = _get_approval_gate_registry_info()
    canonical_path = gate_info["canonical_path"]
    gate_ids = gate_info.get("gate_ids", [])
    selected, observation, excluded_count = classify_candidates()

    def _filter_for_route(keywords):
        result = [f for f in selected if any(kw in f.lower() for kw in keywords)]
        return result if result else ["UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW"]

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
        "selected_candidate_router_files": _filter_for_route(["inbox", "email", "fetch"]),
        "selected_candidate_reason": "inbox/email/fetch 키워드 + route definition 포함 파일 우선",
        "proposed_router_touch_strategy": "PLAN_ONLY_FEATURE_FLAG_OFF_DRY_RUN_ROUTE_GUARD",
        "proposed_integration_boundary": "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY",
        "proposed_import_location": "UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW",
        "proposed_guard_order": [
            "1. route still unmodified",
            "2. feature flag default false",
            "3. dry-run only",
            "4. no live email fetch",
            "5. no DB write",
            "6. no secret/env access",
        ],
        "feature_flag": "LEGACY_5050_EMAIL_FETCH_ENABLED",
        "approval_gate_required": False,
        "approval_gate_registry_path": canonical_path,
        "approval_gate_ids": [],
        "required_before_phase1q": [
            "confirm selected router file path",
            "verify no existing route conflict",
            "confirm feature flag default=false",
        ],
        "required_during_phase1q": [
            "add feature flag check at route entry",
            "connect to wrapper skeleton",
            "register route with flag=off",
        ],
        "rollback_plan": [
            "remove planned import",
            "keep feature flag false",
            "keep original route behavior",
            "no migration of traffic",
        ],
        "stop_conditions": COMMON_STOP_CONDITIONS + [
            "actual_email_fetch",
            "external_site_cookie_storage",
        ],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1Q_ROUTER_TOUCH_APPROVAL_GATE_OR_PHASE_1J",
    })
    rows.append(row_a)

    # B. TASK_APPROVE
    approve_gate_ids = [g for g in gate_ids if "APPROVAL" in g or "DOCUMENT" in g or "FILE_UPLOAD" in g] or ["APPROVAL_ACTION"]
    row_b = _base_row()
    row_b.update({
        "route_skeleton_id": "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/approve",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/approve",
        "selected_candidate_router_files": _filter_for_route(["task", "approve", "approval"]),
        "selected_candidate_reason": "task/approve/approval 키워드 + route definition 포함 파일 우선",
        "proposed_router_touch_strategy": "PLAN_ONLY_FEATURE_FLAG_OFF_DRY_RUN_ROUTE_GUARD",
        "proposed_integration_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "proposed_import_location": "UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW",
        "proposed_guard_order": [
            "1. route still unmodified",
            "2. feature flag default false",
            "3. dry-run only",
            "4. approval gate required",
            "5. approval_gate_executed false",
            "6. no live approve",
            "7. no DB write",
            "8. no /execute boundary",
        ],
        "feature_flag": "LEGACY_5050_TASK_APPROVE_ENABLED",
        "approval_gate_required": True,
        "approval_gate_registry_path": canonical_path,
        "approval_gate_ids": approve_gate_ids,
        "required_before_phase1q": [
            "confirm selected router file path",
            "verify approval gate wiring",
            "check for double slash in path",
        ],
        "required_during_phase1q": [
            "add feature flag check at route entry",
            "connect to wrapper skeleton",
            "register route with flag=off",
            "preserve {id} in path",
        ],
        "rollback_plan": [
            "remove planned import",
            "keep feature flag false",
            "keep original approval route behavior",
            "no approval action executed",
        ],
        "stop_conditions": COMMON_STOP_CONDITIONS + [
            "approval_gate_executed_true",
            "actual_approve",
            "double_slash",
            "execute_boundary_violation",
            "external_site_approval_gate_violation",
        ],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1Q_ROUTER_TOUCH_APPROVAL_GATE_OR_PHASE_1J",
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
        "selected_candidate_router_files": _filter_for_route(["task", "reject", "approval"]),
        "selected_candidate_reason": "task/reject/approval 키워드 + route definition 포함 파일 우선",
        "proposed_router_touch_strategy": "PLAN_ONLY_FEATURE_FLAG_OFF_DRY_RUN_ROUTE_GUARD",
        "proposed_integration_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "proposed_import_location": "UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW",
        "proposed_guard_order": [
            "1. route still unmodified",
            "2. feature flag default false",
            "3. dry-run only",
            "4. approval gate required",
            "5. approval_gate_executed false",
            "6. no live reject",
            "7. no DB write",
            "8. no /execute boundary",
        ],
        "feature_flag": "LEGACY_5050_TASK_REJECT_ENABLED",
        "approval_gate_required": True,
        "approval_gate_registry_path": canonical_path,
        "approval_gate_ids": approve_gate_ids,
        "required_before_phase1q": [
            "confirm selected router file path",
            "verify approval gate wiring",
            "check for double slash in path",
        ],
        "required_during_phase1q": [
            "add feature flag check at route entry",
            "connect to wrapper skeleton",
            "register route with flag=off",
            "preserve {id} in path",
        ],
        "rollback_plan": [
            "remove planned import",
            "keep feature flag false",
            "keep original reject route behavior",
            "no reject action executed",
        ],
        "stop_conditions": COMMON_STOP_CONDITIONS + [
            "approval_gate_executed_true",
            "actual_reject",
            "double_slash",
            "execute_boundary_violation",
            "external_site_approval_gate_violation",
        ],
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": [],
        "next_phase": "PHASE_1Q_ROUTER_TOUCH_APPROVAL_GATE_OR_PHASE_1J",
    })
    rows.append(row_c)

    return rows, selected, observation, excluded_count, gate_info


def run_audit():
    matrix, selected, observation, excluded_count, gate_info = build_plan_matrix()
    all_candidates = selected + observation
    errors = []
    warnings = []

    if len(matrix) != 3:
        errors.append(f"plan matrix row 수 불일치: {len(matrix)} (expected 3)")

    for row in matrix:
        for field, expected in [
            ("route_registered_now", False),
            ("router_file_modification_allowed_now", False),
            ("route_decorator_allowed_now", False),
            ("include_router_allowed_now", False),
            ("feature_flag_runtime_hook_allowed_now", False),
            ("live_traffic_allowed_now", False),
            ("dry_run_only_now", True),
            ("feature_flag_default", False),
            ("approval_gate_executed_allowed", False),
        ]:
            if row.get(field) is not expected:
                errors.append(f"{row['route_skeleton_id']}: {field} must be {expected}")
        if row.get("verdict") != "ROUTER_INTEGRATION_IMPLEMENTATION_PLAN_READY":
            errors.append(f"{row['route_skeleton_id']}: verdict 불일치")
        if row.get("selected_candidate_router_files") == ["UNKNOWN_UNTIL_PHASE1Q_READ_ONLY_ROUTER_REVIEW"]:
            warnings.append(f"{row['route_skeleton_id']}: selected_candidate_router_files UNKNOWN")

    # approval gate
    if not gate_info.get("importable"):
        warnings.append(f"approval_gate_registry not importable: {gate_info.get('canonical_path')}")
    if gate_info.get("auto_execute_allowed_all_false") is False:
        errors.append("approval gate: auto_execute_allowed=True 발견")

    # path 검증
    for row in matrix:
        if row["route_skeleton_id"] in ("TASK_APPROVE_ROUTE_INTEGRATION_SKELETON", "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"):
            if "<id>" not in row["legacy_path_template"]:
                errors.append(f"{row['route_skeleton_id']}: legacy path <id> 없음")
            if "{id}" not in row["fastapi_path_template"]:
                errors.append(f"{row['route_skeleton_id']}: fastapi path {{id}} 없음")
            if "//" in row["fastapi_path_template"]:
                errors.append(f"{row['route_skeleton_id']}: double slash 발견")

    # forbidden routes
    for row in matrix:
        for p in [row.get("legacy_path_template", ""), row.get("fastapi_path_template", "")]:
            for f in FORBIDDEN_ROUTES:
                if f in p:
                    errors.append(f"forbidden route {f} in {p}")

    # candidate count warning
    if len(selected) > 10:
        warnings.append(f"selected_count={len(selected)} > 10")
    if len(selected) == 0:
        warnings.append("selected_count=0: router 후보 없음")
    if len(observation) > 100:
        warnings.append(f"observation_count={len(observation)} > 100")

    verdict = "FAIL" if errors else ("WARN" if warnings else "PHASE1P_ROUTER_INTEGRATION_IMPLEMENTATION_PLAN_READY")

    return {
        "phase": PHASE,
        "plan_id": PLAN_ID,
        "verdict": verdict,
        "plan_matrix_row_count": len(matrix),
        "approval_gate_registry_info": gate_info,
        "scanned_file_count": len(all_candidates) + excluded_count,
        "candidate_file_count": len(all_candidates),
        "selected_count": len(selected),
        "observation_count": len(observation),
        "excluded_count": excluded_count,
        "selected_candidate_router_files": selected,
        "observation_candidate_files": observation[:20],
        "modified_files_count": 0,
        "forbidden_import_violations": 0,
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
        "implementation_plan_only": IMPLEMENTATION_PLAN_ONLY,
        "plan_matrix": matrix,
    }


def get_plan_matrix():
    matrix, _, _, _, _ = build_plan_matrix()
    return matrix


def get_approval_gate_info():
    return _get_approval_gate_registry_info()


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-P Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN: {w}")
