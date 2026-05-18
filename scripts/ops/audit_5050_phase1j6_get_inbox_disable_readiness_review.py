"""
Phase 1-J6: GET /api/v1/inbox Disable Readiness Review
GET /inbox 문을 실제로 닫기 전 폐쇄 준비 조건을 machine-readable하게 고정한다.
실제 disable 금지. readiness matrix와 rollback 조건만 확정.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J6"
REVIEW_ID = "PHASE1J6_GET_INBOX_DISABLE_READINESS_REVIEW"
TARGET_ROUTE = "GET /api/v1/inbox"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ACTUAL_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
READINESS_REVIEW_ONLY = True

# ── 1. GET /inbox disable readiness matrix ────────────────────────────────────
GET_INBOX_DISABLE_READINESS = {
    "route": "/api/v1/inbox",
    "method": "GET",
    "schema_freeze_status": "FROZEN",
    "side_effect_classification": "READ_ONLY_EXPECTED",
    "effective_real_caller_count": 0,
    "migration_strategy": "NO_CALLER_MIGRATION_NEEDED",
    "disable_candidate": True,
    "actual_disable_allowed_now": False,
    "readiness_status": "READY_FOR_DISABLE_PLAN",
    "required_before_disable": [
        "representative_approval_required",
        "git_clean_and_head_eq_origin",
        "schema_freeze_verified",
        "caller_count_verified_as_zero",
        "rollback_plan_verified",
        "disable_flag_design_selected",
        "server_deployment_plan_prepared",
        "smoke_plan_prepared",
    ],
    "required_during_disable": [
        "change_GET_inbox_only",
        "no_POST_tasks_changes",
        "feature_flag_or_disable_guard_default_safe",
        "no_db_write",
        "no_external_call",
        "preserve_rollback_path",
    ],
    "required_after_disable": [
        "GET_inbox_smoke",
        "route_list_audit",
        "caller_smoke",
        "rollback_smoke",
        "quality_gate",
        "layer_audit",
        "server_health_if_deployed",
    ],
    "required_rollback": [
        "revert_disable_commit",
        "restore_route",
        "rerun_GET_inbox_smoke",
        "rerun_route_list_audit",
    ],
    "risk_level": "LOW",
    "blockers": [],
    "next_phase": "PHASE_1J7_GET_INBOX_DISABLE_PLAN_APPROVAL_GATE",
    "verdict": "GET_INBOX_DISABLE_READINESS_READY",
}

# ── 2. caller zero confirmation ───────────────────────────────────────────────
CALLER_ZERO_CONFIRMATION = {
    "frontend_real_caller_count": 0,
    "backend_real_caller_count": 0,
    "metadata_only_reference_count": 1,
    "plan_only_reference_count": 1,
    "backend_compat_reference_count": 1,
    "unknown_caller_count": 0,
    "evidence": {
        "admin_web_external_tasks": "정적 UI 컴포넌트, HTTP 호출 없음 (Phase 1-J4 확정)",
        "external_work_registry": "NOT_A_CALLER_METADATA_ONLY, HTTP import 없음 (Phase 1-J5 확정)",
        "gabia_autowork_subdomain_plan": "계획 문서 성격, HTTP 호출 없음 (Phase 1-J4 확정)",
        "backend_compat_legacy_5050": "COMPAT_CONTRACT_REFERENCE, runtime HTTP 호출 없음 (Phase 1-J4 확정)",
        "inbox_router_py": "Flask Blueprint, dashboard.py 전용, NOT_MOUNTED (Phase 1-J3 확정)",
        "tasks_router_py": "Flask Blueprint, dashboard.py 전용, NOT_MOUNTED (Phase 1-J3 확정)",
        "mcp_server": "주석/에러메시지 문자열만, NOT_MOUNTED (Phase 1-J3 확정)",
    },
    "verdict": "CALLER_ZERO_CONFIRMED",
}

# ── 3. schema freeze confirmation ─────────────────────────────────────────────
SCHEMA_FREEZE_CONFIRMATION = {
    "request_schema_frozen": True,
    "response_schema_frozen": True,
    "status_code_contract_frozen": True,
    "auth_contract_frozen": True,
    "error_schema_contract_frozen": True,
    "inbox_item_required_keys": 12,
    "inbox_item_optional_keys": 1,
    "freeze_basis": "Phase 1-J2 확정 (audit_5050_phase1j2_same_contract_response_schema_freeze.py)",
    "verdict": "SCHEMA_FREEZE_CONFIRMED",
}

# ── 4. rollback plan ──────────────────────────────────────────────────────────
ROLLBACK_PLAN = {
    "disable_strategy_candidate": "FEATURE_FLAG_GUARD_OFF (router.py 패턴 재사용)",
    "rollback_strategy": "git revert disable commit 또는 feature flag 재활성화",
    "rollback_command_or_patch_plan": (
        "git revert <disable_commit_sha> 또는 "
        "router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = True 복원"
    ),
    "rollback_smoke_required": True,
    "evidence_required": True,
    "user_approval_required": True,
    "rollback_basis": (
        "Phase 1-R 패턴 (847f0ee) 재사용. "
        "현재 guard: _legacy_5050_should_use_route_wiring() + LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = True. "
        "disable = False로 전환 후 smoke. rollback = True 복원 후 smoke."
    ),
    "verdict": "ROLLBACK_PLAN_READY",
}

# ── 5. POST /tasks exclusion ──────────────────────────────────────────────────
POST_TASKS_EXCLUSION = {
    "route": "/api/v1/tasks",
    "method": "POST",
    "mode": "BLOCKED_DESIGN_ONLY",
    "blockers": [
        "WRITE_POSSIBLE",
        "execute_side_effect",
        "approval_token_side_effect",
        "db_write_impact",
        "approval_gate_not_designed",
    ],
    "actual_disable_allowed_now": False,
    "migration_allowed_now": False,
    "verdict": "POST_TASKS_EXCLUDED_BLOCKED_DESIGN_ONLY",
}


def _verify_no_router_modification() -> tuple[bool, str]:
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J6" in content:
        return False, "router.py에 PHASE_1J6 감지 — 수정 발생"
    touch_count = content.count("LEGACY_5050_ROUTER_TOUCH_PHASE")
    if touch_count != 1:
        return False, f"LEGACY_5050_ROUTER_TOUCH_PHASE count={touch_count} (expected 1)"
    return True, "router.py 수정 없음"


def _verify_no_frontend_modification() -> tuple[bool, str]:
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists() and "PHASE_1J6" in tsx.read_text(encoding="utf-8", errors="ignore"):
        return False, "admin-web page.tsx에 PHASE_1J6 감지 — 수정 발생"
    return True, "admin-web 수정 없음"


def _verify_no_backend_modification() -> tuple[bool, str]:
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists() and "PHASE_1J6" in p.read_text(encoding="utf-8", errors="ignore"):
            return False, f"{f}에 PHASE_1J6 감지"
    return True, "backend caller 수정 없음"


def _verify_legacy_5050_exists() -> tuple[bool, str]:
    legacy_dir = REPO_ROOT / "backend/compat/legacy_5050"
    if not legacy_dir.exists():
        return False, "backend/compat/legacy_5050 삭제 감지"
    return True, "legacy_5050 디렉터리 존재"


def _verify_no_http_import_in_this_script() -> tuple[bool, str]:
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
            return False, f"HTTP client imported in audit script: {bad}"
    return True, "HTTP client import 없음"


def run_audit() -> dict:
    errors = []
    warnings = []

    # 1. GET /inbox readiness matrix 검증
    dr = GET_INBOX_DISABLE_READINESS
    if dr["schema_freeze_status"] != "FROZEN":
        errors.append("schema_freeze_status must be FROZEN")
    if dr["side_effect_classification"] != "READ_ONLY_EXPECTED":
        errors.append("side_effect_classification must be READ_ONLY_EXPECTED")
    if dr["effective_real_caller_count"] != 0:
        errors.append(f"effective_real_caller_count != 0: {dr['effective_real_caller_count']}")
    if dr["migration_strategy"] != "NO_CALLER_MIGRATION_NEEDED":
        errors.append(f"migration_strategy 이상: {dr['migration_strategy']}")
    if not dr["disable_candidate"]:
        errors.append("disable_candidate must be True")
    if dr["actual_disable_allowed_now"]:
        errors.append("actual_disable_allowed_now must be False")
    if not dr["readiness_status"]:
        errors.append("readiness_status 없음")
    for field in ["required_before_disable", "required_during_disable",
                   "required_after_disable", "required_rollback"]:
        if not dr.get(field):
            errors.append(f"{field} 없음")

    # 2. caller zero confirmation
    cz = CALLER_ZERO_CONFIRMATION
    if cz["frontend_real_caller_count"] != 0:
        errors.append(f"frontend_real_caller_count != 0: {cz['frontend_real_caller_count']}")
    if cz["backend_real_caller_count"] != 0:
        errors.append(f"backend_real_caller_count != 0: {cz['backend_real_caller_count']}")
    if cz["unknown_caller_count"] != 0:
        errors.append(f"unknown_caller_count != 0: {cz['unknown_caller_count']}")

    # 3. schema freeze
    sf = SCHEMA_FREEZE_CONFIRMATION
    for key in ["request_schema_frozen", "response_schema_frozen",
                 "status_code_contract_frozen", "auth_contract_frozen",
                 "error_schema_contract_frozen"]:
        if not sf.get(key):
            errors.append(f"schema freeze {key} must be True")

    # 4. rollback plan
    rp = ROLLBACK_PLAN
    if not rp.get("rollback_smoke_required"):
        errors.append("rollback_smoke_required must be True")
    if not rp.get("evidence_required"):
        errors.append("evidence_required must be True")
    if not rp.get("user_approval_required"):
        errors.append("user_approval_required must be True")
    if not rp.get("rollback_command_or_patch_plan"):
        errors.append("rollback_command_or_patch_plan 없음")

    # 5. POST /tasks exclusion
    pt = POST_TASKS_EXCLUSION
    if pt["mode"] != "BLOCKED_DESIGN_ONLY":
        errors.append("POST /tasks mode must be BLOCKED_DESIGN_ONLY")
    if pt["actual_disable_allowed_now"]:
        errors.append("POST /tasks actual_disable_allowed_now must be False")
    if pt["migration_allowed_now"]:
        errors.append("POST /tasks migration_allowed_now must be False")
    if len(pt.get("blockers", [])) < 5:
        errors.append(f"POST /tasks blockers < 5: {pt.get('blockers')}")

    # 6. router.py 수정 없음
    ok, msg = _verify_no_router_modification()
    if not ok:
        errors.append(msg)

    # 7. frontend 수정 없음
    ok, msg = _verify_no_frontend_modification()
    if not ok:
        errors.append(msg)

    # 8. backend 수정 없음
    ok, msg = _verify_no_backend_modification()
    if not ok:
        errors.append(msg)

    # 9. legacy_5050 존재
    ok, msg = _verify_legacy_5050_exists()
    if not ok:
        errors.append(msg)

    # 10. 이전 Phase 파일 존재
    prev_phases = [
        "scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py",
        "scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py",
        "scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py",
        "scripts/ops/audit_5050_phase1j3_caller_migration_plan.py",
        "scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py",
        "scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py",
        "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py",
        "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py",
        "scripts/ops/audit_5050_phase1_8400_contract_freeze.py",
        "scripts/ops/audit_5050_legacy_characterization.py",
        "scripts/ops/audit_external_site_canonical_registry.py",
    ]
    for p in prev_phases:
        if not (REPO_ROOT / p).exists():
            errors.append(f"이전 Phase 파일 없음: {p}")

    # 11. HTTP import 없음
    ok, msg = _verify_no_http_import_in_this_script()
    if not ok:
        errors.append(msg)

    # 12. global flags
    if ACTUAL_DISABLE_ALLOWED_NOW:
        errors.append("ACTUAL_DISABLE_ALLOWED_NOW must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if LIVE_TRAFFIC_ALLOWED:
        errors.append("LIVE_TRAFFIC_ALLOWED must be False")
    if not READINESS_REVIEW_ONLY:
        errors.append("READINESS_REVIEW_ONLY must be True")

    # verdict
    if errors:
        verdict = "PHASE1J6_GET_INBOX_DISABLE_READINESS_FAIL"
    elif warnings:
        verdict = "PHASE1J6_GET_INBOX_DISABLE_READINESS_READY_WITH_WARN"
    else:
        verdict = "PHASE1J6_GET_INBOX_DISABLE_READINESS_READY"

    return {
        "phase": PHASE,
        "review_id": REVIEW_ID,
        "target_route": TARGET_ROUTE,
        "verdict": verdict,
        "get_inbox_readiness_status": dr["readiness_status"],
        "get_inbox_disable_candidate": dr["disable_candidate"],
        "get_inbox_actual_disable_allowed_now": dr["actual_disable_allowed_now"],
        "get_inbox_effective_real_caller_count": cz["frontend_real_caller_count"] + cz["backend_real_caller_count"],
        "get_inbox_schema_freeze": sf["response_schema_frozen"],
        "get_inbox_migration_strategy": dr["migration_strategy"],
        "get_inbox_risk_level": dr["risk_level"],
        "post_tasks_status": pt["mode"],
        "post_tasks_blocker_count": len(pt.get("blockers", [])),
        "actual_disable_allowed_now": ACTUAL_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "readiness_review_only": READINESS_REVIEW_ONLY,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J6는 readiness review 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 / 테스트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
        "next_phases": [
            "Phase 1-J7: GET /inbox disable plan approval gate (대표 승인 후)",
            "Phase 1-T: disabled guard expanded smoke",
            "백엔드 운영 안정화 최종 점검",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J6 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
