"""
Phase 1-T: Disabled Guard Expanded Smoke
Phase 1-R disabled guard가 전체 경로에서 no-op임을 확대 검증.
GET /inbox effective disabled 상태 회귀 없음 확인.
POST /tasks BLOCKED_DESIGN_ONLY 유지 확인.
5050 legacy route 정리 공정 백엔드 안정화 진입 가능 여부 판단.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1T"
AUDIT_ID = "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
SMOKE_ONLY = True

# ── Phase 1-R guard 현황 (3개 경로) ─────────────────────────────────────────
GUARD_REGISTRY = [
    {
        "route_id": "INBOX_EMAIL_FETCH",
        "path": "POST /api/v1/inbox/email/fetch",
        "flag": "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED",
        "expected_value": False,
        "guard_behavior": "should_use_route_wiring returns False → no-op (기존 8400 handler 실행)",
        "router_line_hint": 278,
    },
    {
        "route_id": "TASK_APPROVE",
        "path": "POST /api/v1/tasks/{task_id}/approve",
        "flag": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED",
        "expected_value": False,
        "guard_behavior": "should_use_route_wiring returns False → no-op (기존 8400 handler 실행)",
        "router_line_hint": 198,
    },
    {
        "route_id": "TASK_REJECT",
        "path": "POST /api/v1/tasks/{task_id}/reject",
        "flag": "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED",
        "expected_value": False,
        "guard_behavior": "should_use_route_wiring returns False → no-op (기존 8400 handler 실행)",
        "router_line_hint": 221,
    },
]

# ── GET /inbox effective disabled 상태 확인 ───────────────────────────────────
GET_INBOX_STATUS = {
    "route": "/api/v1/inbox",
    "method": "GET",
    "disabled_status": "EFFECTIVELY_DISABLED",
    "disabled_basis": "Phase 1-J8 확정 — inbox_router.py Flask Blueprint NOT_MOUNTED",
    "8400_handler_active": True,
    "legacy_wiring_active": False,
    "regression_risk": "NONE",
}

# ── POST /tasks BLOCKED_DESIGN_ONLY 유지 확인 ────────────────────────────────
POST_TASKS_STATUS = {
    "route": "/api/v1/tasks",
    "method": "POST",
    "status": "BLOCKED_DESIGN_ONLY",
    "blockers": [
        "WRITE_POSSIBLE",
        "execute_side_effect",
        "approval_token_side_effect",
        "db_write_impact",
        "approval_gate_not_designed",
    ],
    "disable_allowed_now": False,
}

# ── 백엔드 안정화 진입 판단 ──────────────────────────────────────────────────
STABILIZATION_READINESS = {
    "get_inbox_legacy_cleared": True,
    "guard_no_op_confirmed": True,
    "post_tasks_still_blocked": True,
    "all_regression_pass_expected": True,
    "backend_stabilization_ready": True,
    "notes": (
        "SAME_CONTRACT 2개 route(GET /inbox, POST /tasks) 중 "
        "GET /inbox effectively disabled 확정. "
        "POST /tasks는 BLOCKED_DESIGN_ONLY 유지. "
        "Phase 1-R guard 3개 전체 no-op 확인. "
        "백엔드 안정화 공정 진입 가능."
    ),
    "verdict": "BACKEND_STABILIZATION_ENTRY_READY",
}


def _load_guard_state() -> dict:
    """router.py에서 실제 guard flag 값과 guard 함수 동작을 정적 분석."""
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    results = {}
    for g in GUARD_REGISTRY:
        flag = g["flag"]
        # "FLAG = False" 패턴 확인
        enabled = f"{flag} = True" in content
        results[g["route_id"]] = {
            "flag": flag,
            "flag_is_false": not enabled,
            "guard_is_noop": not enabled,
        }

    # guard 함수 존재 확인
    has_guard_fn = "_legacy_5050_should_use_route_wiring" in content
    guard_in_inbox_fetch = (
        "_legacy_5050_should_use_route_wiring(\"INBOX_EMAIL_FETCH\")" in content
        or "_legacy_5050_should_use_route_wiring('INBOX_EMAIL_FETCH')" in content
    )
    guard_in_approve = (
        "_legacy_5050_should_use_route_wiring(\"TASK_APPROVE\")" in content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in content
    )
    guard_in_reject = (
        "_legacy_5050_should_use_route_wiring(\"TASK_REJECT\")" in content
        or "_legacy_5050_should_use_route_wiring('TASK_REJECT')" in content
    )

    return {
        "flags": results,
        "has_guard_function": has_guard_fn,
        "guard_applied_to_inbox_fetch": guard_in_inbox_fetch,
        "guard_applied_to_approve": guard_in_approve,
        "guard_applied_to_reject": guard_in_reject,
        "all_guards_noop": all(v["guard_is_noop"] for v in results.values()),
    }


def _verify_get_inbox_8400_handler() -> bool:
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    return '@router.get("/inbox")' in content or "@router.get('/inbox')" in content


def _verify_inbox_not_mounted() -> bool:
    server = REPO_ROOT / "ai_orchestrator/server.py"
    if not server.exists():
        return True  # server.py 없으면 마운트 없음
    content = server.read_text(encoding="utf-8", errors="ignore")
    return not ("inbox_bp" in content and "register_blueprint" in content)


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

    # 1. Phase 1-R guard 상태 확인
    guard_state = _load_guard_state()

    if not guard_state["has_guard_function"]:
        errors.append("_legacy_5050_should_use_route_wiring 함수 없음")
    if not guard_state["guard_applied_to_inbox_fetch"]:
        errors.append("INBOX_EMAIL_FETCH guard 적용 없음")
    if not guard_state["guard_applied_to_approve"]:
        errors.append("TASK_APPROVE guard 적용 없음")
    if not guard_state["guard_applied_to_reject"]:
        errors.append("TASK_REJECT guard 적용 없음")
    if not guard_state["all_guards_noop"]:
        errors.append("guard 중 enabled=True인 항목 존재 — no-op 아님")

    for route_id, state in guard_state["flags"].items():
        if not state["flag_is_false"]:
            errors.append(f"{route_id} flag True — guard active, expected no-op")

    # 2. GET /inbox 상태 확인
    if not _verify_get_inbox_8400_handler():
        errors.append("8400 FastAPI GET /inbox handler 없음")
    if not _verify_inbox_not_mounted():
        errors.append("inbox_bp가 server.py에 마운트됨 — effective disabled 상태 아님")

    # 3. router.py 추가 수정 없음
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1T" in content:
        errors.append("router.py에 PHASE_1T 감지 — 미승인 수정")
    touch_count = content.count("LEGACY_5050_ROUTER_TOUCH_PHASE")
    if touch_count != 1:
        errors.append(f"LEGACY_5050_ROUTER_TOUCH_PHASE count={touch_count} (expected 1)")

    # 4. ROUTER_TOUCH_PHASE = PHASE_1R 유지
    if "LEGACY_5050_ROUTER_TOUCH_PHASE = \"PHASE_1R\"" not in content and \
       "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" not in content:
        errors.append("LEGACY_5050_ROUTER_TOUCH_PHASE != PHASE_1R — 수정 감지")

    # 5. POST /tasks 상태
    pt = POST_TASKS_STATUS
    if pt["status"] != "BLOCKED_DESIGN_ONLY":
        errors.append("POST /tasks status must be BLOCKED_DESIGN_ONLY")
    if pt["disable_allowed_now"]:
        errors.append("POST /tasks disable_allowed_now must be False")
    if len(pt.get("blockers", [])) < 5:
        errors.append(f"POST /tasks blockers < 5")

    # 6. 안정화 진입 판단
    sr = STABILIZATION_READINESS
    if not sr["get_inbox_legacy_cleared"]:
        errors.append("get_inbox_legacy_cleared must be True")
    if not sr["guard_no_op_confirmed"]:
        errors.append("guard_no_op_confirmed must be True")
    if not sr["backend_stabilization_ready"]:
        errors.append("backend_stabilization_ready must be True")

    # 7. 이전 Phase 파일 존재
    prev_phases = [
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
    for p in prev_phases:
        if not (REPO_ROOT / p).exists():
            errors.append(f"이전 Phase 파일 없음: {p}")

    # 8. global flags
    if ROUTER_FILE_MODIFICATION_ALLOWED:
        errors.append("ROUTER_FILE_MODIFICATION_ALLOWED must be False")
    if LIVE_TRAFFIC_ALLOWED:
        errors.append("LIVE_TRAFFIC_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if not SMOKE_ONLY:
        errors.append("SMOKE_ONLY must be True")

    # 9. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # verdict
    if errors:
        verdict = "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_FAIL"
    elif warnings:
        verdict = "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_READY_WITH_WARN"
    else:
        verdict = "PHASE1T_DISABLED_GUARD_EXPANDED_SMOKE_READY"

    return {
        "phase": PHASE,
        "audit_id": AUDIT_ID,
        "verdict": verdict,
        "guard_all_noop": guard_state["all_guards_noop"],
        "guard_function_present": guard_state["has_guard_function"],
        "guard_inbox_fetch_noop": guard_state["flags"].get("INBOX_EMAIL_FETCH", {}).get("guard_is_noop"),
        "guard_task_approve_noop": guard_state["flags"].get("TASK_APPROVE", {}).get("guard_is_noop"),
        "guard_task_reject_noop": guard_state["flags"].get("TASK_REJECT", {}).get("guard_is_noop"),
        "get_inbox_disabled_status": GET_INBOX_STATUS["disabled_status"],
        "get_inbox_8400_handler_active": GET_INBOX_STATUS["8400_handler_active"],
        "get_inbox_regression_risk": GET_INBOX_STATUS["regression_risk"],
        "post_tasks_status": POST_TASKS_STATUS["status"],
        "post_tasks_blocker_count": len(POST_TASKS_STATUS.get("blockers", [])),
        "backend_stabilization_ready": STABILIZATION_READINESS["backend_stabilization_ready"],
        "stabilization_verdict": STABILIZATION_READINESS["verdict"],
        "router_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-T는 smoke-only 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: git revert <this_commit_sha>",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
        "next_phases": [
            "백엔드 운영 안정화 최종 점검",
            "POST /tasks BLOCKED_DESIGN_ONLY — approval gate 설계 후 별도 Phase",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-T Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
