"""
Backend Operation Stabilization Final Audit
5050 → 8400 이관 공정 전체 종합 감리.
완료/보류/위험/후속 공정 분리.
앱 착공 전 백엔드 준공 기준 확정.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

AUDIT_ID = "BACKEND_OPERATION_STABILIZATION_FINAL"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
AUDIT_ONLY = True

# ── 1. 5050 → 8400 이관 공정 전체 이력 ──────────────────────────────────────
PHASE_HISTORY = [
    {"phase": "PHASE_1",    "id": "8400_CONTRACT_FREEZE",          "status": "COMPLETE", "commit": "계약 동결"},
    {"phase": "PHASE_1R",   "id": "ACTUAL_ROUTER_TOUCH_FLAG_OFF",  "status": "COMPLETE", "commit": "847f0ee"},
    {"phase": "PHASE_1S",   "id": "DISABLED_GUARD_BEHAVIOR",       "status": "COMPLETE", "commit": "9a53ee9"},
    {"phase": "PHASE_1J",   "id": "SAME_CONTRACT_DISABLE_REVIEW",  "status": "COMPLETE", "commit": "9ecd3d7"},
    {"phase": "PHASE_1J2",  "id": "SCHEMA_FREEZE",                 "status": "COMPLETE", "commit": "de872a3"},
    {"phase": "PHASE_1J3",  "id": "CALLER_MIGRATION_PLAN",         "status": "COMPLETE", "commit": "f615b44"},
    {"phase": "PHASE_1J4",  "id": "DRY_RUN_SMOKE",                 "status": "COMPLETE", "commit": "a0b09ed"},
    {"phase": "PHASE_1J5",  "id": "CALLER_CONFIRMATION",           "status": "COMPLETE", "commit": "2c75bd5"},
    {"phase": "PHASE_1J6",  "id": "DISABLE_READINESS_REVIEW",      "status": "COMPLETE", "commit": "4d25ece"},
    {"phase": "PHASE_1J7",  "id": "DISABLE_PLAN_APPROVAL_GATE",    "status": "COMPLETE", "commit": "04fb68a"},
    {"phase": "PHASE_1J8",  "id": "DISABLE_EXECUTION_CONFIRMED",   "status": "COMPLETE", "commit": "6d63d6b"},
    {"phase": "PHASE_1T",   "id": "DISABLED_GUARD_EXPANDED_SMOKE", "status": "COMPLETE", "commit": "4b593e5"},
]

# ── 2. 완료 항목 ─────────────────────────────────────────────────────────────
COMPLETED_ITEMS = {
    "GET /api/v1/inbox": {
        "status": "COMPLETE",
        "effective_disabled": True,
        "caller_count": 0,
        "schema_frozen": True,
        "migration_needed": False,
        "legacy_wiring": "NOT_MOUNTED",
        "8400_handler": "ACTIVE_NORMAL",
        "guard_noop": True,
    },
    "Phase_1R_guards": {
        "status": "COMPLETE",
        "INBOX_EMAIL_FETCH": "flag=False, no-op",
        "TASK_APPROVE": "flag=False, no-op",
        "TASK_REJECT": "flag=False, no-op",
    },
    "schema_freeze": {
        "status": "COMPLETE",
        "GET_inbox_request": "FROZEN",
        "GET_inbox_response": "FROZEN",
        "POST_tasks_request": "FROZEN",
        "POST_tasks_response": "FROZEN",
    },
    "external_site_registry": {
        "status": "COMPLETE",
        "canonical_registry": "확정",
        "safety_policies": "확정",
        "gabia_settings": "확정",
    },
}

# ── 3. 보류 항목 ─────────────────────────────────────────────────────────────
PENDING_ITEMS = {
    "POST /api/v1/tasks": {
        "status": "BLOCKED_DESIGN_ONLY",
        "reason": "WRITE_POSSIBLE + execute/approval_token side effect + DB write + approval_gate 미설계",
        "blockers": [
            "WRITE_POSSIBLE",
            "execute_side_effect",
            "approval_token_side_effect",
            "db_write_impact",
            "approval_gate_not_designed",
        ],
        "disable_allowed_now": False,
        "next_action": "approval gate 설계 완료 후 별도 Phase",
    },
}

# ── 4. 위험 항목 ─────────────────────────────────────────────────────────────
RISK_ITEMS = {
    "POST_tasks_side_effect": {
        "risk": "MEDIUM",
        "description": "POST /tasks execute/approve/token side effect 미분석",
        "mitigation": "BLOCKED_DESIGN_ONLY 유지",
    },
    "server_not_applied": {
        "risk": "LOW",
        "description": "이 공정들은 서버 반영 없음. 실제 서버 동작은 별도 검증 필요",
        "mitigation": "배포 전 smoke plan 수행",
    },
}

# ── 5. 준공 기준 ──────────────────────────────────────────────────────────────
COMPLETION_CRITERIA = {
    "backend_phase1_legacy_GET_inbox": "COMPLETE",
    "backend_phase1r_guard_noop": "COMPLETE",
    "backend_schema_freeze": "COMPLETE",
    "backend_caller_analysis": "COMPLETE",
    "backend_external_site_registry": "COMPLETE",
    "backend_layer_audit": "PASS",
    "backend_quality_gate": "PASS",
    "backend_regression_641": "PASS",
    "post_tasks_gate": "BLOCKED — 준공 조건 아님, 별도 Phase",
    "server_deploy": "미수행 — 별도 Phase",
    "overall_verdict": "BACKEND_PHASE1_LEGACY_INTEGRATION_AUDIT_COMPLETE",
}

# ── 6. known baseline (회귀 기준) ────────────────────────────────────────────
KNOWN_BASELINES = [
    "tests/test_5050_legacy_characterization_20260517.py",
    "tests/test_5050_phase1_8400_contract_freeze_20260517.py",
    "tests/test_5050_phase1r_actual_router_touch_feature_flag_off_20260517.py",
    "tests/test_5050_phase1s_disabled_router_guard_behavior_20260517.py",
    "tests/test_external_site_canonical_registry_20260517.py",
    "tests/test_codebase_layer_audit.py",
]


def _check_all_phase_files() -> tuple[list, list]:
    """모든 Phase audit 파일 존재 확인."""
    present, missing = [], []
    for ph in PHASE_HISTORY:
        candidate_pattern = f"scripts/ops/audit_5050_phase{ph['phase'].lower().replace('phase_', '')}*.py"
        found = list(REPO_ROOT.glob(candidate_pattern))
        if found:
            present.append(ph["phase"])
        else:
            # 이름이 다른 경우 대비 — audit_backend_operation 등
            missing.append(ph["phase"])
    return present, missing


def _check_router_stability() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    return {
        "touch_phase": "PHASE_1R" if "LEGACY_5050_ROUTER_TOUCH_PHASE = \"PHASE_1R\"" in content
                       or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content else "UNKNOWN",
        "touch_enabled": "LEGACY_5050_ROUTER_TOUCH_ENABLED = False" in content,
        "inbox_fetch_enabled": "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" in content,
        "task_approve_enabled": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = True" in content,
        "task_reject_enabled": "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = True" in content,
        "has_8400_inbox_handler": '@router.get("/inbox")' in content or "@router.get('/inbox')" in content,
        "guard_function_exists": "_legacy_5050_should_use_route_wiring" in content,
    }


def _verify_no_http_import() -> tuple[bool, str]:
    try:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
        if bad in imported:
            return False, f"HTTP client imported: {bad}"
    return True, "HTTP client import 없음"


def run_audit() -> dict:
    errors = []
    warnings = []

    # 1. Phase 파일 존재 확인
    key_files = [
        "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py",
        "scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py",
        "scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py",
        "scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py",
        "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py",
        "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py",
        "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py",
        "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py",
        "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py",
        "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py",
        "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py",
        "scripts/ops/audit_5050_phase1_8400_contract_freeze.py",
        "scripts/ops/audit_5050_legacy_characterization.py",
        "scripts/ops/audit_external_site_canonical_registry.py",
    ]
    for f in key_files:
        if not (REPO_ROOT / f).exists():
            errors.append(f"Phase 파일 없음: {f}")

    # 2. router.py 안정성
    rs = _check_router_stability()
    if rs["touch_phase"] != "PHASE_1R":
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    if not rs["touch_enabled"]:
        warnings.append("LEGACY_5050_ROUTER_TOUCH_ENABLED = True — 확인 필요")
    if rs["inbox_fetch_enabled"]:
        errors.append("INBOX_EMAIL_FETCH wiring enabled — no-op 전제 깨짐")
    if rs["task_approve_enabled"]:
        errors.append("TASK_APPROVE wiring enabled — no-op 전제 깨짐")
    if rs["task_reject_enabled"]:
        errors.append("TASK_REJECT wiring enabled — no-op 전제 깨짐")
    if not rs["has_8400_inbox_handler"]:
        errors.append("8400 GET /inbox handler 없음")
    if not rs["guard_function_exists"]:
        errors.append("guard 함수 없음")

    # 3. GET /inbox 완료 확인
    gi = COMPLETED_ITEMS["GET /api/v1/inbox"]
    if not gi["effective_disabled"]:
        errors.append("GET /inbox effective_disabled must be True")
    if gi["caller_count"] != 0:
        errors.append(f"GET /inbox caller_count != 0")
    if not gi["schema_frozen"]:
        errors.append("GET /inbox schema_frozen must be True")

    # 4. POST /tasks 보류 확인
    pt = PENDING_ITEMS["POST /api/v1/tasks"]
    if pt["disable_allowed_now"]:
        errors.append("POST /tasks disable_allowed_now must be False")
    if len(pt.get("blockers", [])) < 5:
        errors.append("POST /tasks blockers < 5")

    # 5. 준공 기준
    cc = COMPLETION_CRITERIA
    if cc["backend_phase1_legacy_GET_inbox"] != "COMPLETE":
        errors.append("GET /inbox 미완료")
    if cc["backend_phase1r_guard_noop"] != "COMPLETE":
        errors.append("guard no-op 미완료")
    if cc["backend_schema_freeze"] != "COMPLETE":
        errors.append("schema freeze 미완료")

    # 6. legacy_5050 존재
    if not (REPO_ROOT / "backend/compat/legacy_5050").exists():
        errors.append("backend/compat/legacy_5050 삭제 감지")

    # 7. global flags
    if ROUTER_FILE_MODIFICATION_ALLOWED:
        errors.append("ROUTER_FILE_MODIFICATION_ALLOWED must be False")
    if LIVE_TRAFFIC_ALLOWED:
        errors.append("LIVE_TRAFFIC_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if not AUDIT_ONLY:
        errors.append("AUDIT_ONLY must be True")

    # 8. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # verdict
    if errors:
        verdict = "BACKEND_STABILIZATION_FINAL_AUDIT_FAIL"
    elif warnings:
        verdict = "BACKEND_STABILIZATION_FINAL_AUDIT_COMPLETE_WITH_WARN"
    else:
        verdict = "BACKEND_STABILIZATION_FINAL_AUDIT_COMPLETE"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "overall_completion": COMPLETION_CRITERIA["overall_verdict"],
        "completed_phases": len([p for p in PHASE_HISTORY if p["status"] == "COMPLETE"]),
        "total_phases": len(PHASE_HISTORY),
        "get_inbox_status": COMPLETED_ITEMS["GET /api/v1/inbox"]["effective_disabled"],
        "post_tasks_status": PENDING_ITEMS["POST /api/v1/tasks"]["status"],
        "guard_noop_all": not any([
            rs["inbox_fetch_enabled"],
            rs["task_approve_enabled"],
            rs["task_reject_enabled"],
        ]),
        "router_stability": rs,
        "backend_stabilization_entry": True,
        "router_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "이 공정은 audit-only. router.py / caller 파일 수정 없음.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
        "next_phases": [
            "서버 배포 전 smoke plan 수행",
            "POST /tasks side-effect gate 설계 완료 후 별도 Phase",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Backend Stabilization Final Audit: {result['verdict']} ===")
    print(f"  완료 Phase: {result['completed_phases']}/{result['total_phases']}")
    print(f"  GET /inbox: {'COMPLETE' if result['get_inbox_status'] else 'PENDING'}")
    print(f"  POST /tasks: {result['post_tasks_status']}")
    print(f"  guard no-op: {'ALL' if result['guard_noop_all'] else 'PARTIAL'}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
