"""
Phase 1-J7: GET /api/v1/inbox Disable Plan Approval Gate
폐쇄 허가서 — disable plan 작성 + 대표 승인 조건 고정.
실제 disable 금지. 대표 명시 승인 전까지 plan/gate 단계만.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J7"
GATE_ID = "PHASE1J7_GET_INBOX_DISABLE_PLAN_APPROVAL_GATE"
TARGET_ROUTE = "GET /api/v1/inbox"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ACTUAL_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
APPROVAL_GATE_ONLY = True
REPRESENTATIVE_APPROVAL_RECEIVED = False  # 대표 명시 승인 전까지 False

# ── 1. disable plan ───────────────────────────────────────────────────────────
GET_INBOX_DISABLE_PLAN = {
    "route": "/api/v1/inbox",
    "method": "GET",
    "phase": PHASE,
    "disable_strategy": "FEATURE_FLAG_GUARD_OFF",
    "disable_mechanism": (
        "router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False 전환. "
        "Phase 1-R 패턴 재사용: _legacy_5050_should_use_route_wiring() guard 경유."
    ),
    "disable_scope": "GET /api/v1/inbox only. POST /api/v1/tasks 불변.",
    "schema_freeze_status": "FROZEN",
    "side_effect_classification": "READ_ONLY_EXPECTED",
    "effective_real_caller_count": 0,
    "disable_candidate": True,
    "actual_disable_allowed_now": False,
    "plan_approved": False,
    "pre_disable_steps": [
        "1. 대표 명시 승인 수신 (REPRESENTATIVE_APPROVAL_RECEIVED = True)",
        "2. git status clean + HEAD == origin/master 확인",
        "3. Phase 1-J6 readiness matrix 재확인",
        "4. router.py guard 동작 재확인 (Phase 1-S smoke)",
        "5. disable flag 전환 commit 준비",
    ],
    "disable_steps": [
        "1. router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False",
        "2. GET /inbox smoke: 5050 route → disabled guard 반환 확인",
        "3. 8400 FastAPI GET /api/v1/inbox 정상 응답 확인",
        "4. quality gate + layer audit 실행",
        "5. commit + push",
        "6. 서버 배포 — SERVER_APPLY_ALLOWED 별도 승인 후",
    ],
    "post_disable_steps": [
        "1. GET /inbox route smoke (8400 경로 동작)",
        "2. caller smoke (caller 0이므로 무영향 예상)",
        "3. route list audit",
        "4. quality gate + layer audit 재실행",
        "5. 서버 health check (배포 후)",
    ],
    "rollback_steps": [
        "1. git revert <disable_commit_sha>",
        "2. GET /inbox smoke 재실행 — 5050 route 복구 확인",
        "3. quality gate + layer audit",
        "4. push + 서버 반영 (배포 전이면 commit만)",
    ],
    "risk_level": "LOW",
    "rollback_risk": "VERY_LOW",
    "next_phase_if_approved": "PHASE_1K_GET_INBOX_ACTUAL_DISABLE",
    "verdict": "DISABLE_PLAN_READY_PENDING_APPROVAL",
}

# ── 2. 대표 승인 조건 ─────────────────────────────────────────────────────────
APPROVAL_CONDITIONS = {
    "required_from_representative": [
        "GET /api/v1/inbox legacy route disable 명시 승인",
        "실제 router.py 수정 허가",
        "서버 배포 시점 확인 (또는 local-only 단계 승인)",
    ],
    "pre_approval_checklist": [
        "Phase 1-J6 readiness matrix 확인 완료",
        "caller count 0 최종 확인",
        "schema freeze 확인",
        "rollback plan 확인",
        "smoke plan 확인",
    ],
    "approval_not_received_action": "HOLD — 이 파일만 존재, router.py/caller 수정 없음",
    "approval_received_next_step": "Phase 1-K: GET /inbox actual disable implementation",
    "representative_approval_received": REPRESENTATIVE_APPROVAL_RECEIVED,
    "verdict": (
        "APPROVAL_GATE_HOLDING"
        if not REPRESENTATIVE_APPROVAL_RECEIVED
        else "APPROVAL_RECEIVED_PROCEED"
    ),
}

# ── 3. pre-deploy smoke 조건 ──────────────────────────────────────────────────
PRE_DEPLOY_SMOKE_CONDITIONS = {
    "before_router_change": [
        "Phase 1-S guard smoke 재실행",
        "GET /inbox 현재 동작 snapshot",
        "router.py guard 함수 확인",
    ],
    "after_router_change_before_deploy": [
        "GET /inbox disabled guard 반환 확인",
        "router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False 확인",
        "quality gate errors = 0",
        "layer audit PASS",
    ],
    "after_deploy": [
        "서버 health check",
        "GET /inbox 8400 경로 smoke",
        "롤백 경로 smoke",
    ],
    "verdict": "PRE_DEPLOY_SMOKE_CONDITIONS_DEFINED",
}

# ── 4. POST /tasks 제외 ───────────────────────────────────────────────────────
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

# ── 5. rollback plan (J6 MINOR_NOTE 반영 — git revert 주 기준) ────────────────
ROLLBACK_PLAN = {
    "primary_rollback": "git revert <disable_commit_sha>",
    "secondary_rollback": (
        "router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = True 복원 "
        "(disable flag가 구현된 이후 단계에서만 유효)"
    ),
    "current_phase_rollback": "git revert — disable commit 미존재이므로 이 스크립트/테스트 파일만 삭제",
    "rollback_smoke_required": True,
    "evidence_required": True,
    "user_approval_required": True,
    "verdict": "ROLLBACK_PLAN_GIT_REVERT_PRIMARY",
}


def _verify_no_router_modification() -> tuple[bool, str]:
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J7" in content:
        return False, "router.py에 PHASE_1J7 감지 — 수정 발생"
    if content.count("LEGACY_5050_ROUTER_TOUCH_PHASE") != 1:
        return False, f"LEGACY_5050_ROUTER_TOUCH_PHASE count 이상"
    # FETCH_EMAIL_INBOX_ENABLED는 여전히 True여야 함 (아직 disable 전)
    if "LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False" in content:
        return False, "router.py FETCH_EMAIL_INBOX_ENABLED가 이미 False — 미승인 수정"
    return True, "router.py 수정 없음 + FETCH_EMAIL_INBOX_ENABLED 아직 True"


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

    # 1. disable plan 검증
    dp = GET_INBOX_DISABLE_PLAN
    if dp["schema_freeze_status"] != "FROZEN":
        errors.append("schema_freeze_status must be FROZEN")
    if dp["side_effect_classification"] != "READ_ONLY_EXPECTED":
        errors.append("side_effect_classification must be READ_ONLY_EXPECTED")
    if dp["effective_real_caller_count"] != 0:
        errors.append(f"effective_real_caller_count != 0")
    if not dp["disable_candidate"]:
        errors.append("disable_candidate must be True")
    if dp["actual_disable_allowed_now"]:
        errors.append("actual_disable_allowed_now must be False")
    if dp["plan_approved"]:
        errors.append("plan_approved must be False (대표 승인 전)")
    for field in ["pre_disable_steps", "disable_steps", "post_disable_steps", "rollback_steps"]:
        if not dp.get(field):
            errors.append(f"{field} 없음")

    # 2. 승인 조건
    ac = APPROVAL_CONDITIONS
    if ac["representative_approval_received"]:
        errors.append("REPRESENTATIVE_APPROVAL_RECEIVED must be False at this phase")
    if ac["verdict"] != "APPROVAL_GATE_HOLDING":
        errors.append(f"approval verdict 이상: {ac['verdict']}")
    if not ac["pre_approval_checklist"]:
        errors.append("pre_approval_checklist 없음")

    # 3. POST /tasks 제외
    pt = POST_TASKS_EXCLUSION
    if pt["mode"] != "BLOCKED_DESIGN_ONLY":
        errors.append("POST /tasks mode must be BLOCKED_DESIGN_ONLY")
    if pt["actual_disable_allowed_now"]:
        errors.append("POST /tasks actual_disable_allowed_now must be False")
    if len(pt.get("blockers", [])) < 5:
        errors.append(f"POST /tasks blockers < 5")

    # 4. rollback plan
    rp = ROLLBACK_PLAN
    if not rp.get("primary_rollback"):
        errors.append("primary_rollback 없음")
    if not rp.get("rollback_smoke_required"):
        errors.append("rollback_smoke_required must be True")
    if not rp.get("user_approval_required"):
        errors.append("user_approval_required must be True")

    # 5. router.py 수정 없음 + FETCH_EMAIL_INBOX_ENABLED 아직 True
    ok, msg = _verify_no_router_modification()
    if not ok:
        errors.append(msg)

    # 6. frontend 수정 없음
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists() and "PHASE_1J7" in tsx.read_text(encoding="utf-8", errors="ignore"):
        errors.append("admin-web page.tsx에 PHASE_1J7 감지")

    # 7. backend 수정 없음
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists() and "PHASE_1J7" in p.read_text(encoding="utf-8", errors="ignore"):
            errors.append(f"{f}에 PHASE_1J7 감지")

    # 8. legacy_5050 존재
    if not (REPO_ROOT / "backend/compat/legacy_5050").exists():
        errors.append("backend/compat/legacy_5050 삭제 감지")

    # 9. 이전 Phase 파일 존재
    prev_phases = [
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
    if ACTUAL_DISABLE_ALLOWED_NOW:
        errors.append("ACTUAL_DISABLE_ALLOWED_NOW must be False")
    if not APPROVAL_GATE_ONLY:
        errors.append("APPROVAL_GATE_ONLY must be True")
    if REPRESENTATIVE_APPROVAL_RECEIVED:
        errors.append("REPRESENTATIVE_APPROVAL_RECEIVED must be False")

    # 11. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # verdict
    if errors:
        verdict = "PHASE1J7_GET_INBOX_DISABLE_PLAN_FAIL"
    elif warnings:
        verdict = "PHASE1J7_GET_INBOX_DISABLE_PLAN_GATE_HOLDING_WITH_WARN"
    else:
        verdict = "PHASE1J7_GET_INBOX_DISABLE_PLAN_GATE_HOLDING"

    return {
        "phase": PHASE,
        "gate_id": GATE_ID,
        "target_route": TARGET_ROUTE,
        "verdict": verdict,
        "disable_plan_status": dp["verdict"],
        "approval_gate_status": APPROVAL_CONDITIONS["verdict"],
        "representative_approval_received": REPRESENTATIVE_APPROVAL_RECEIVED,
        "pre_deploy_smoke_defined": True,
        "get_inbox_effective_real_caller_count": dp["effective_real_caller_count"],
        "get_inbox_schema_freeze": dp["schema_freeze_status"],
        "get_inbox_actual_disable_allowed_now": dp["actual_disable_allowed_now"],
        "post_tasks_status": POST_TASKS_EXCLUSION["mode"],
        "post_tasks_blocker_count": len(POST_TASKS_EXCLUSION.get("blockers", [])),
        "actual_disable_allowed_now": ACTUAL_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "approval_gate_only": APPROVAL_GATE_ONLY,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J7는 approval gate 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 / 테스트 파일만 삭제.",
            "Phase 1-K(실제 disable) rollback: git revert <disable_commit_sha>",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
        "next_phases": [
            "Phase 1-K: GET /inbox actual disable (대표 명시 승인 후)",
            "Phase 1-T: disabled guard expanded smoke",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J7 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
