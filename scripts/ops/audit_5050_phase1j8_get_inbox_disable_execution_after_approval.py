"""
Phase 1-J8: GET /api/v1/inbox Disable Execution (After Representative Approval)
대표 명시 승인 수신 후 실제 disable 상태 확인 공정.

핵심 발견:
- GET /api/v1/inbox는 router.py에 8400 FastAPI handler로 직접 구현됨 (line 258)
- 5050 legacy inbox_router.py Flask Blueprint은 8400에 NOT_MOUNTED (Phase 1-J3 확정)
- compat/legacy_5050/에는 /inbox/email/fetch(POST) 어댑터만 있고 GET /inbox 어댑터 없음
- 결론: GET /api/v1/inbox 5050 legacy route는 이미 effectively disabled (NOT_MOUNTED)
- 추가 router.py 수정 불필요

이 공정:
- 대표 승인 반영 확인
- 현재 상태(already effectively disabled) 공식 문서화
- router.py 수정 없음 (8400 FastAPI handler 정상 유지)
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J8"
EXECUTION_ID = "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_AFTER_APPROVAL"
TARGET_ROUTE = "GET /api/v1/inbox"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
REPRESENTATIVE_APPROVAL_RECEIVED = True   # 2026-05-18 대표 명시 승인 수신
ACTUAL_DISABLE_PERFORMED = False          # router.py 수정 없음 — 이미 disabled
ROUTER_FILE_MODIFICATION_PERFORMED = False
SERVER_APPLY_PERFORMED = False
LIVE_TRAFFIC_CALL = False
DB_WRITE = False

# ── disable 실행 결과 ─────────────────────────────────────────────────────────
DISABLE_EXECUTION_RESULT = {
    "route": "/api/v1/inbox",
    "method": "GET",
    "phase": PHASE,
    "representative_approval_date": "2026-05-18",
    "disable_strategy_applied": "ALREADY_EFFECTIVELY_DISABLED_VIA_NOT_MOUNTED",
    "router_modification_required": False,
    "router_modification_performed": False,
    "disable_status": "EFFECTIVELY_DISABLED",
    "disable_basis": (
        "5050 legacy Flask inbox_router.py는 dashboard.py 전용 Flask Blueprint. "
        "8400 FastAPI server.py에 include_router 또는 마운트 없음 (Phase 1-J3 확정). "
        "router.py line 258: @router.get('/inbox') → 8400 FastAPI handler 직접 구현. "
        "compat/legacy_5050/에 GET /inbox 어댑터 없음. "
        "추가 disable 조치 불필요."
    ),
    "8400_fastapi_handler_status": "ACTIVE_NORMAL",
    "8400_fastapi_handler_location": "ai_orchestrator/router.py:258",
    "legacy_5050_mount_status": "NOT_MOUNTED",
    "legacy_5050_basis": "Phase 1-J3 audit 확정",
    "schema_freeze_status": "FROZEN",
    "side_effect_classification": "READ_ONLY_EXPECTED",
    "effective_real_caller_count": 0,
    "verdict": "GET_INBOX_LEGACY_EFFECTIVELY_DISABLED",
}

# ── Phase 1-J7 대비 변경사항 ──────────────────────────────────────────────────
PHASE_DELTA_FROM_J7 = {
    "representative_approval": "False → True (2026-05-18)",
    "router_modification": "없음 — 이미 effectively disabled",
    "disable_status": "pending → EFFECTIVELY_DISABLED",
    "next_action": "Phase 1-T: disabled guard expanded smoke 또는 운영 안정화",
}

# ── POST /tasks 제외 유지 ─────────────────────────────────────────────────────
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
    "modification_allowed_now": False,
    "verdict": "POST_TASKS_EXCLUDED_BLOCKED_DESIGN_ONLY",
}

# ── rollback plan ─────────────────────────────────────────────────────────────
ROLLBACK_PLAN = {
    "need_rollback": False,
    "reason": "router.py 수정 없음 — rollback 대상 commit 없음",
    "if_needed": "git revert <this_audit_commit_sha> — 스크립트/테스트 파일만 삭제",
    "8400_handler_rollback": "불필요 — 8400 handler 수정 없음",
    "verdict": "NO_ROLLBACK_NEEDED",
}


def _check_router_state() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    has_get_inbox_handler = "@router.get(\"/inbox\")" in content or "@router.get('/inbox')" in content
    has_phase1j8_tag = "PHASE_1J8" in content
    touch_count = content.count("LEGACY_5050_ROUTER_TOUCH_PHASE")
    # inbox email fetch route wiring enabled 상태
    has_inbox_fetch_enabled = "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" in content
    return {
        "has_8400_get_inbox_handler": has_get_inbox_handler,
        "has_phase1j8_modification": has_phase1j8_tag,
        "touch_phase_count": touch_count,
        "inbox_fetch_wiring_enabled": has_inbox_fetch_enabled,
    }


def _check_legacy_mount() -> dict:
    """5050 legacy inbox route 8400 마운트 여부 확인."""
    server_path = REPO_ROOT / "ai_orchestrator/server.py"
    if not server_path.exists():
        return {"server_exists": False, "inbox_blueprint_mounted": False}
    content = server_path.read_text(encoding="utf-8", errors="ignore")
    inbox_bp_mounted = "inbox_bp" in content and "register_blueprint" in content
    return {
        "server_exists": True,
        "inbox_blueprint_mounted": inbox_bp_mounted,
        "verdict": "MOUNTED" if inbox_bp_mounted else "NOT_MOUNTED",
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

    # 1. 대표 승인 확인
    if not REPRESENTATIVE_APPROVAL_RECEIVED:
        errors.append("REPRESENTATIVE_APPROVAL_RECEIVED must be True")

    # 2. disable execution result 검증
    dr = DISABLE_EXECUTION_RESULT
    if dr["router_modification_performed"]:
        errors.append("router_modification_performed must be False")
    if dr["disable_status"] != "EFFECTIVELY_DISABLED":
        errors.append(f"disable_status 이상: {dr['disable_status']}")
    if dr["effective_real_caller_count"] != 0:
        errors.append(f"effective_real_caller_count != 0")
    if dr["schema_freeze_status"] != "FROZEN":
        errors.append("schema_freeze_status must be FROZEN")
    if dr["legacy_5050_mount_status"] != "NOT_MOUNTED":
        errors.append(f"legacy_5050_mount_status must be NOT_MOUNTED")
    if dr["8400_fastapi_handler_status"] != "ACTIVE_NORMAL":
        errors.append("8400 handler must remain ACTIVE_NORMAL")

    # 3. router.py 상태 확인
    router_state = _check_router_state()
    if not router_state["has_8400_get_inbox_handler"]:
        errors.append("8400 GET /inbox handler 없음 — router.py 확인 필요")
    if router_state["has_phase1j8_modification"]:
        errors.append("router.py에 PHASE_1J8 태그 — 미승인 수정 감지")
    if router_state["touch_phase_count"] != 1:
        errors.append(f"LEGACY_5050_ROUTER_TOUCH_PHASE count 이상: {router_state['touch_phase_count']}")
    if router_state["inbox_fetch_wiring_enabled"]:
        errors.append("LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED이 True — Phase 1-R 상태 이상")

    # 4. 5050 legacy 마운트 상태
    mount = _check_legacy_mount()
    if mount.get("inbox_blueprint_mounted"):
        errors.append("inbox_bp가 server.py에 마운트됨 — NOT_MOUNTED 전제 깨짐")

    # 5. frontend 수정 없음
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists() and "PHASE_1J8" in tsx.read_text(encoding="utf-8", errors="ignore"):
        errors.append("admin-web page.tsx에 PHASE_1J8 감지")

    # 6. backend caller 수정 없음
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists() and "PHASE_1J8" in p.read_text(encoding="utf-8", errors="ignore"):
            errors.append(f"{f}에 PHASE_1J8 감지")

    # 7. legacy_5050 존재
    if not (REPO_ROOT / "backend/compat/legacy_5050").exists():
        errors.append("backend/compat/legacy_5050 삭제 감지")

    # 8. compat에 GET /inbox 어댑터 없음 확인 (정상 상태)
    compat_inbox_adapters = list(
        (REPO_ROOT / "backend/compat/legacy_5050").glob("**/inbox*.py")
    )
    # inbox/email/fetch 어댑터만 있어야 함 — GET /inbox 전용 어댑터 없음이 정상
    get_inbox_adapters = [
        f for f in compat_inbox_adapters
        if "email_fetch" not in f.name
    ]
    if get_inbox_adapters:
        warnings.append(
            f"compat에 예상 외 inbox 어댑터 파일 존재: {[f.name for f in get_inbox_adapters]}"
        )

    # 9. 이전 Phase 파일 존재
    prev_phases = [
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
    for p in prev_phases:
        if not (REPO_ROOT / p).exists():
            errors.append(f"이전 Phase 파일 없음: {p}")

    # 10. global flags
    if ROUTER_FILE_MODIFICATION_PERFORMED:
        errors.append("ROUTER_FILE_MODIFICATION_PERFORMED must be False")
    if LIVE_TRAFFIC_CALL:
        errors.append("LIVE_TRAFFIC_CALL must be False")
    if DB_WRITE:
        errors.append("DB_WRITE must be False")

    # 11. POST /tasks 제외
    pt = POST_TASKS_EXCLUSION
    if pt["mode"] != "BLOCKED_DESIGN_ONLY":
        errors.append("POST /tasks mode must be BLOCKED_DESIGN_ONLY")
    if pt["actual_disable_allowed_now"]:
        errors.append("POST /tasks actual_disable_allowed_now must be False")
    if len(pt.get("blockers", [])) < 5:
        errors.append("POST /tasks blockers < 5")

    # 12. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # verdict
    if errors:
        verdict = "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_FAIL"
    elif warnings:
        verdict = "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_CONFIRMED_WITH_WARN"
    else:
        verdict = "PHASE1J8_GET_INBOX_DISABLE_EXECUTION_CONFIRMED"

    return {
        "phase": PHASE,
        "execution_id": EXECUTION_ID,
        "target_route": TARGET_ROUTE,
        "verdict": verdict,
        "representative_approval_received": REPRESENTATIVE_APPROVAL_RECEIVED,
        "disable_status": DISABLE_EXECUTION_RESULT["disable_status"],
        "disable_strategy": DISABLE_EXECUTION_RESULT["disable_strategy_applied"],
        "router_modification_performed": ROUTER_FILE_MODIFICATION_PERFORMED,
        "8400_handler_status": DISABLE_EXECUTION_RESULT["8400_fastapi_handler_status"],
        "legacy_5050_mount_status": DISABLE_EXECUTION_RESULT["legacy_5050_mount_status"],
        "get_inbox_effective_real_caller_count": DISABLE_EXECUTION_RESULT["effective_real_caller_count"],
        "get_inbox_schema_freeze": DISABLE_EXECUTION_RESULT["schema_freeze_status"],
        "post_tasks_status": POST_TASKS_EXCLUSION["mode"],
        "post_tasks_blocker_count": len(POST_TASKS_EXCLUSION.get("blockers", [])),
        "router_state": _check_router_state(),
        "legacy_mount_state": _check_legacy_mount(),
        "rollback_needed": ROLLBACK_PLAN["need_rollback"],
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J8는 read-only 확인 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 / 테스트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
        "next_phases": [
            "Phase 1-T: disabled guard expanded smoke",
            "백엔드 운영 안정화 최종 점검",
            "GET /inbox는 이미 effectively disabled — 별도 추가 disable 조치 불필요",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J8 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
