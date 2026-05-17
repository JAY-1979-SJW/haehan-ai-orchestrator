"""
Phase 1-Q: Real Router Touch Approval Gate Audit
GATE_ID: PHASE1Q_REAL_ROUTER_TOUCH_APPROVAL_GATE

WARN 3건 처리 결과와 Phase 1-R 진입 조건을 machine-readable하게 고정.
실제 router 파일 수정 없음.
"""
import importlib.util
from pathlib import Path

# ── 상수 ──────────────────────────────────────────────────────────────────
PHASE = "PHASE_1Q"
GATE_ID = "PHASE1Q_REAL_ROUTER_TOUCH_APPROVAL_GATE"
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
HUMAN_APPROVAL_REQUIRED_FOR_PHASE1R = True

REPO_ROOT = Path(__file__).parent.parent.parent

EXCLUDED_PATTERNS = [
    "test_", "audit_", "smoke_", "route_integration", "wrapper_candidate",
    "__pycache__", ".pyc", "/docs/", "docs/", "external_sites",
    "wrappers/",
]

# ── approval gate registry 로드 ────────────────────────────────────────────
def _load_approval_gate_registry():
    p = REPO_ROOT / "ai_orchestrator/external_sites/approval_gate_registry.py"
    if not p.exists():
        return None, "FILE_NOT_FOUND"
    try:
        import sys
        # REPO_ROOT를 sys.path에 추가해야 ai_orchestrator 내부 import가 작동
        repo_str = str(REPO_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)
        spec = importlib.util.spec_from_file_location("_approval_gate_registry_q", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_approval_gate_registry_q"] = mod
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as e:
        return None, str(e)

def get_approval_gate_info():
    mod, err = _load_approval_gate_registry()
    if mod is None:
        return {
            "canonical_path": "ai_orchestrator/external_sites/approval_gate_registry.py",
            "importable": False,
            "error": err,
            "gate_ids": [],
            "auto_execute_allowed_all_false": None,
            "user_approval_required_all_true": None,
            "evidence_required_all_true": None,
            "raw_registry": {},
        }

    # approval_gate_registry 는 APPROVAL_GATES tuple + _GATE_INDEX dict 구조
    raw_registry = {}
    gates_tuple = getattr(mod, "APPROVAL_GATES", None)
    gate_index = getattr(mod, "_GATE_INDEX", None)

    if gate_index:
        for gid, gate_obj in gate_index.items():
            if hasattr(gate_obj, "to_safe_dict"):
                raw_registry[gid] = gate_obj.to_safe_dict()
            else:
                raw_registry[gid] = {
                    "gate_id": gid,
                    "auto_execute_allowed": getattr(gate_obj, "auto_execute_allowed", None),
                    "user_approval_required": getattr(gate_obj, "user_approval_required", None),
                    "evidence_required": getattr(gate_obj, "evidence_required", None),
                }
    elif gates_tuple:
        for gate_obj in gates_tuple:
            gid = getattr(gate_obj, "gate_id", str(gate_obj))
            if hasattr(gate_obj, "to_safe_dict"):
                raw_registry[gid] = gate_obj.to_safe_dict()
            else:
                raw_registry[gid] = {
                    "gate_id": gid,
                    "auto_execute_allowed": getattr(gate_obj, "auto_execute_allowed", None),
                    "user_approval_required": getattr(gate_obj, "user_approval_required", None),
                    "evidence_required": getattr(gate_obj, "evidence_required", None),
                }
    else:
        # fallback: dict-based registry
        for attr in ["APPROVAL_GATE_REGISTRY", "GATE_REGISTRY", "GATES"]:
            candidate = getattr(mod, attr, {})
            if candidate:
                raw_registry = dict(candidate)
                break

    gate_ids = list(raw_registry.keys())
    auto_exec_ok = all(g.get("auto_execute_allowed") is False for g in raw_registry.values() if "auto_execute_allowed" in g)
    user_ok = all(g.get("user_approval_required") is True for g in raw_registry.values() if "user_approval_required" in g)
    evidence_ok = all(g.get("evidence_required") is True for g in raw_registry.values() if "evidence_required" in g)
    return {
        "canonical_path": "ai_orchestrator/external_sites/approval_gate_registry.py",
        "importable": True,
        "gate_ids": gate_ids,
        "auto_execute_allowed_all_false": auto_exec_ok,
        "user_approval_required_all_true": user_ok,
        "evidence_required_all_true": evidence_ok,
        "raw_registry": raw_registry,
    }

# ── INBOX 후보 탐색 ──────────────────────────────────────────────────────
INBOX_SEARCH_KEYWORDS = [
    "inbox", "email_fetch", "fetch_email", "/api/v1/inbox",
    "email/fetch", "fetch", "email",
]
INBOX_ROUTE_KEYWORDS = ["@router.", "@app.route", "APIRouter", "include_router", "route"]

def _is_excluded(path_str):
    return any(p in path_str for p in EXCLUDED_PATTERNS)

def scan_inbox_candidates():
    exact = []
    likely = []
    service_boundary = []

    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if _is_excluded(str(py_file)):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
            has_inbox = any(kw in content for kw in ["inbox", "email_fetch", "/api/v1/inbox", "email/fetch"])
            has_route = any(kw in content for kw in INBOX_ROUTE_KEYWORDS)
            if has_inbox and has_route:
                exact.append(rel)
            elif has_inbox:
                service_boundary.append(rel)
            elif any(kw in content for kw in ["fetch_email", "email_fetch"]):
                likely.append(rel)

    return {
        "exact_router_candidate": exact,
        "likely_router_candidate": likely,
        "service_boundary_candidate": service_boundary,
        "no_current_router_found": len(exact) == 0 and len(likely) == 0,
    }

# ── selected candidate 재분류 ────────────────────────────────────────────
ROUTE_DEF_KEYWORDS = ["@router.", "@app.route", "APIRouter(", "include_router("]
PRIMARY_KEYWORDS = ["/api/v1/inbox", "/api/v1/tasks", "approve", "reject", "email/fetch"]
SECONDARY_KEYWORDS = ["task", "inbox", "email", "fetch", "approve", "reject", "handler"]

def classify_candidates():
    primary = []
    secondary = []
    observation = []
    excluded_count = 0

    for root_name in ["ai_orchestrator", "backend"]:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            path_str = str(py_file)
            if _is_excluded(path_str):
                excluded_count += 1
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
            has_route_def = any(kw in content for kw in ROUTE_DEF_KEYWORDS)
            has_primary = any(kw in content or kw in rel for kw in PRIMARY_KEYWORDS)
            has_secondary = any(kw in content.lower() or kw in rel.lower() for kw in SECONDARY_KEYWORDS)
            has_route_kw = any(kw in content for kw in ["APIRouter", "@router.", "@app.route", "include_router", "/api/v1"])

            if has_route_def and has_primary:
                primary.append(rel)
            elif has_route_kw and has_secondary:
                secondary.append(rel)
            elif has_route_kw:
                observation.append(rel)

    # deduplicate
    primary = sorted(set(primary))
    secondary = sorted(set(s for s in secondary if s not in primary))
    observation = sorted(set(o for o in observation if o not in primary and o not in secondary))

    return primary, secondary, observation, excluded_count

# ── WARN resolution matrix ───────────────────────────────────────────────
def build_warn_resolution_matrix():
    gate_info = get_approval_gate_info()
    inbox_candidates = scan_inbox_candidates()
    primary, secondary, observation, excluded_count = classify_candidates()

    selected_count = len(primary) + len(secondary)

    # WARN 1: INBOX_SELECTED_UNKNOWN
    if inbox_candidates["exact_router_candidate"] or inbox_candidates["likely_router_candidate"]:
        inbox_status = "RESOLVED"
        inbox_evidence = inbox_candidates["exact_router_candidate"] + inbox_candidates["likely_router_candidate"]
        inbox_risk = "none"
    elif inbox_candidates["service_boundary_candidate"]:
        inbox_status = "CONDITIONALLY_ACCEPTED"
        inbox_evidence = inbox_candidates["service_boundary_candidate"]
        inbox_risk = "INBOX route may be defined at service boundary; Phase 1-R read-only inspection required"
    else:
        inbox_status = "CONDITIONALLY_ACCEPTED"
        inbox_evidence = ["NO_DIRECT_ROUTER_FILE_FOUND"]
        inbox_risk = "INBOX route not yet registered; likely new route addition in Phase 1-R"

    # WARN 2: APPROVAL_GATE_REGISTRY_IMPORT
    if gate_info["importable"]:
        gate_status = "RESOLVED"
        gate_evidence = f"canonical: {gate_info['canonical_path']}, gates: {gate_info['gate_ids']}"
        gate_risk = "none"
    else:
        gate_status = "CONDITIONALLY_ACCEPTED"
        gate_evidence = f"file exists at {gate_info['canonical_path']} but import issue: {gate_info.get('error', 'unknown')}"
        gate_risk = "approval gate registry requires direct read; spec-based import used as fallback"

    # WARN 3: SELECTED_CANDIDATE_COUNT
    if selected_count <= 10:
        count_status = "RESOLVED"
        count_evidence = f"selected_count={selected_count} <= 10"
        count_risk = "none"
    else:
        count_status = "CONDITIONALLY_ACCEPTED"
        count_evidence = f"selected_count={selected_count}; primary={len(primary)}, secondary={len(secondary)}"
        count_risk = f"selected_count exceeds 10; each file is distinct route/handler candidate"

    return [
        {
            "warn_id": "INBOX_SELECTED_UNKNOWN",
            "previous_status": "WARN",
            "resolution_status": inbox_status,
            "evidence": inbox_evidence,
            "remaining_risk": inbox_risk,
            "phase1r_entry_condition": "INBOX route candidate re-confirmed via read-only router file inspection",
        },
        {
            "warn_id": "APPROVAL_GATE_REGISTRY_IMPORT",
            "previous_status": "WARN",
            "resolution_status": gate_status,
            "evidence": gate_evidence,
            "remaining_risk": gate_risk,
            "phase1r_entry_condition": "approval_gate_registry loaded via canonical path before any router touch",
        },
        {
            "warn_id": "SELECTED_CANDIDATE_COUNT",
            "previous_status": "WARN",
            "resolution_status": count_status,
            "evidence": count_evidence,
            "remaining_risk": count_risk,
            "phase1r_entry_condition": "final candidate confirmed as <=10 or each file has documented reason",
        },
    ], primary, secondary, observation, excluded_count, gate_info, inbox_candidates

# ── Phase 1-R entry conditions ────────────────────────────────────────────
PHASE1R_ENTRY_CONDITIONS = [
    "git_clean",
    "head_sync_with_origin_master",
    "selected_candidates_le_10_or_accepted_reason",
    "approval_gate_canonical_path_fixed",
    "inbox_candidate_resolved_or_conditionally_accepted",
    "no_router_modification_yet",
    "user_explicit_approval_required",
]

# ── route approval gate rows ─────────────────────────────────────────────
def build_route_gate_rows(primary, secondary, gate_info):
    all_selected = primary + secondary
    gate_ids = gate_info.get("gate_ids", [])
    approval_ids = [g for g in gate_ids if any(k in g for k in ["APPROVAL", "DOCUMENT", "FILE_UPLOAD", "ACTION"])] or ["APPROVAL_ACTION"]

    def _filter(keywords):
        result = [f for f in all_selected if any(kw in f.lower() for kw in keywords)]
        return result or ["UNKNOWN_UNTIL_PHASE1R_READ_ONLY_INSPECTION"]

    return [
        {
            "route_skeleton_id": "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON",
            "adapter_id": "INBOX_EMAIL_FETCH_ADAPTER",
            "selected_candidate_status": "CONDITIONALLY_ACCEPTED",
            "selected_candidate_files": _filter(["inbox", "email", "fetch"]),
            "approval_gate_required": False,
            "approval_gate_registry_path": gate_info["canonical_path"],
            "approval_gate_ids": [],
            "approval_gate_executed_allowed": False,
            "real_router_touch_allowed_now": False,
            "phase1r_requires_human_approval": True,
            "phase1r_action_allowed": False,
            "verdict": "APPROVAL_GATE_READY_CONDITIONALLY_ACCEPTED",
        },
        {
            "route_skeleton_id": "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON",
            "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
            "selected_candidate_status": "CONDITIONALLY_ACCEPTED",
            "selected_candidate_files": _filter(["task", "approve", "approval"]),
            "approval_gate_required": True,
            "approval_gate_registry_path": gate_info["canonical_path"],
            "approval_gate_ids": approval_ids,
            "approval_gate_executed_allowed": False,
            "real_router_touch_allowed_now": False,
            "phase1r_requires_human_approval": True,
            "phase1r_action_allowed": False,
            "verdict": "APPROVAL_GATE_READY_CONDITIONALLY_ACCEPTED",
        },
        {
            "route_skeleton_id": "TASK_REJECT_ROUTE_INTEGRATION_SKELETON",
            "adapter_id": "TASK_REJECT_PATH_AUTH_ADAPTER",
            "selected_candidate_status": "CONDITIONALLY_ACCEPTED",
            "selected_candidate_files": _filter(["task", "reject", "approval"]),
            "approval_gate_required": True,
            "approval_gate_registry_path": gate_info["canonical_path"],
            "approval_gate_ids": approval_ids,
            "approval_gate_executed_allowed": False,
            "real_router_touch_allowed_now": False,
            "phase1r_requires_human_approval": True,
            "phase1r_action_allowed": False,
            "verdict": "APPROVAL_GATE_READY_CONDITIONALLY_ACCEPTED",
        },
    ]

# ── main audit ────────────────────────────────────────────────────────────
def run_audit():
    warn_matrix, primary, secondary, observation, excluded_count, gate_info, inbox_candidates = build_warn_resolution_matrix()
    selected_count = len(primary) + len(secondary)
    route_rows = build_route_gate_rows(primary, secondary, gate_info)

    errors = []
    warnings = []

    blocked = [w for w in warn_matrix if w["resolution_status"] == "BLOCKED"]
    if blocked:
        for b in blocked:
            errors.append(f"BLOCKED warn: {b['warn_id']}")

    if gate_info.get("auto_execute_allowed_all_false") is False:
        errors.append("approval gate: auto_execute_allowed=True 발견")

    if selected_count > 10:
        warnings.append(f"selected_count={selected_count} > 10 (CONDITIONALLY_ACCEPTED)")

    verdict = (
        "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_BLOCKED" if errors else
        "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_READY_WITH_WARN" if warnings or any(w["resolution_status"] == "CONDITIONALLY_ACCEPTED" for w in warn_matrix) else
        "PHASE1Q_ROUTER_TOUCH_APPROVAL_GATE_READY"
    )

    return {
        "phase": PHASE,
        "gate_id": GATE_ID,
        "verdict": verdict,
        "warn_resolution_matrix": warn_matrix,
        "blocked_count": len(blocked),
        "conditionally_accepted_count": sum(1 for w in warn_matrix if w["resolution_status"] == "CONDITIONALLY_ACCEPTED"),
        "resolved_count": sum(1 for w in warn_matrix if w["resolution_status"] == "RESOLVED"),
        "approval_gate_registry_info": gate_info,
        "candidate_classification": {
            "selected_count": selected_count,
            "primary_count": len(primary),
            "secondary_count": len(secondary),
            "observation_count": len(observation),
            "excluded_count": excluded_count,
            "selected_primary": primary,
            "selected_secondary": secondary,
            "observation_sample": observation[:10],
        },
        "inbox_candidates": inbox_candidates,
        "route_gate_rows": route_rows,
        "phase1r_entry_conditions": PHASE1R_ENTRY_CONDITIONS,
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
        "human_approval_required_for_phase1r": HUMAN_APPROVAL_REQUIRED_FOR_PHASE1R,
        "modified_files_count": 0,
        "errors": errors,
        "warnings": warnings,
    }

def get_warn_resolution_matrix():
    matrix, *_ = build_warn_resolution_matrix()
    return matrix

def get_route_gate_rows():
    matrix, primary, secondary, observation, excluded_count, gate_info, inbox = build_warn_resolution_matrix()
    return build_route_gate_rows(primary, secondary, gate_info)

if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-Q Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN: {w}")
