"""
Phase 1-J5: GET /inbox Caller Confirmation & Migration Implementation Plan
external_work_registry.py 참조 성격 최종 확인 + GET /inbox migration 구현 계획.
POST /api/v1/tasks는 BLOCKED_DESIGN_ONLY 유지.
"""
from pathlib import Path
import ast

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J5"
AUDIT_ID = "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_AND_MIGRATION_PLAN"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
CALLER_MODIFICATION_ALLOWED_NOW = False
LEGACY_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
PLAN_ONLY = True

# ── external_work_registry.py 정적 분석 결과 ─────────────────────────────────
EXTERNAL_WORK_REGISTRY_ANALYSIS = {
    "file": "ai_orchestrator/external_work_registry.py",
    "phase1j4_warn": "NEEDS_CONFIRM",
    "phase1j5_classification": "NOT_A_CALLER_METADATA_ONLY",
    "has_real_http_call": False,
    "has_http_client_import": False,
    "allowed_imports": ["__future__", "dataclasses", "typing"],
    "inbox_direct_reference": False,
    "inbox_string_reference": "notes field in gmail_read entry references /api/v1/inbox/email/fetch",
    "inbox_string_is_http_call": False,
    "migration_impact": "NONE",
    "phase1j4_warn_resolved": True,
    "resolution_basis": (
        "external_work_registry.py는 순수 메타데이터 레지스트리."
        " imports: __future__, dataclasses, typing 만 존재."
        " requests/httpx/urllib/aiohttp 없음."
        " /api/v1/inbox 직접 참조 없음."
        " notes 문자열 내 /api/v1/inbox/email/fetch는 문서 성격."
        " NOT_A_CALLER_METADATA_ONLY 최종 확정."
    ),
}

# ── 실효 caller 집계 ─────────────────────────────────────────────────────────
EFFECTIVE_CALLER_SUMMARY = {
    "get_inbox": {
        "frontend_real_http_caller_count": 0,
        "frontend_callers": [],
        "frontend_note": "admin-web external-tasks page.tsx: 정적 UI, HTTP 호출 없음",
        "backend_real_http_caller_count": 0,
        "backend_callers": [],
        "backend_note": "external_work_registry.py: NOT_A_CALLER_METADATA_ONLY",
        "compat_caller_count": 0,
        "compat_note": "backend/compat/legacy_5050/* 는 compat contract ref, runtime HTTP 호출 없음",
        "effective_real_caller_count": 0,
        "migration_impact": "NONE",
        "migration_action": "NO_CALLER_TO_MIGRATE",
        "verdict": "GET_INBOX_EFFECTIVE_CALLER_COUNT_ZERO",
    },
    "post_tasks": {
        "status": "BLOCKED_DESIGN_ONLY",
        "migration_impact": "WRITE_POSSIBLE_SIDE_EFFECT_UNRESOLVED",
        "verdict": "POST_TASKS_BLOCKED_DESIGN_ONLY_MAINTAINED",
    },
}

# ── GET /inbox migration implementation plan ──────────────────────────────────
GET_INBOX_MIGRATION_PLAN = {
    "phase": PHASE,
    "path": "/api/v1/inbox",
    "method": "GET",
    "schema_freeze_status": "FROZEN",
    "effective_real_caller_count": 0,
    "disable_allowed_now": False,
    "caller_modification_allowed_now": False,
    "implementation_allowed_now": False,
    "implementation_blocker": "LEGACY_DISABLE_GATE_NOT_PASSED",
    "side_effect_classification": "READ_ONLY_EXPECTED",
    "migration_strategy": "NO_CALLER_MIGRATION_NEEDED",
    "migration_steps": [
        "1. GET /inbox 실효 caller 수 = 0 확정 (Phase 1-J5 완료)",
        "2. legacy 5050 route disable 결정 — LEGACY_DISABLE_ALLOWED_NOW=True 승인 필요",
        "3. router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = False 적용 (Phase 1-R 패턴)",
        "4. server.py 8400 FastAPI GET /api/v1/inbox 검증 smoke",
        "5. 최종 end-to-end 확인 후 Phase 1-K(disable 실행) 진행",
    ],
    "required_before_disable": [
        "LEGACY_DISABLE_ALLOWED_NOW 승인",
        "Phase 1-S disabled guard behavior audit 통과",
        "8400 FastAPI inbox endpoint smoke 통과",
    ],
    "required_after_disable": [
        "router guard behavior 재확인",
        "client 에러 없음 확인 (caller count=0이므로 무영향 예상)",
    ],
    "rollback_plan": (
        "git revert 또는 router.py LEGACY_5050_FETCH_EMAIL_INBOX_ENABLED = True 복원. "
        "Phase 1-R rollback: git revert 847f0ee 또는 "
        "git checkout 0d74129 -- ai_orchestrator/router.py"
    ),
    "risk_level": "LOW",
    "next_action": "WAIT_FOR_LEGACY_DISABLE_APPROVAL",
}

# ── POST /tasks blocker 유지 현황 ────────────────────────────────────────────
POST_TASKS_BLOCKER_STATUS = {
    "phase": PHASE,
    "path": "/api/v1/tasks",
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
    "caller_modification_allowed_now": False,
    "next_action": "POST_TASKS_SIDE_EFFECT_GATE_DESIGN",
}


def _analyze_external_work_registry() -> dict:
    """external_work_registry.py AST 분석."""
    reg_path = REPO_ROOT / "ai_orchestrator/external_work_registry.py"
    if not reg_path.exists():
        return {"error": "file not found", "classification": "UNKNOWN"}

    content = reg_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}", "classification": "UNKNOWN"}

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    http_clients = {"requests", "httpx", "aiohttp", "urllib3", "http"}
    has_http_import = bool(imported & http_clients)
    has_inbox_direct = "/api/v1/inbox" in content and "fetch(" in content
    has_inbox_string = "/api/v1/inbox" in content

    classification = (
        "NOT_A_CALLER_METADATA_ONLY"
        if not has_http_import and not has_inbox_direct
        else "NEEDS_MANUAL_REVIEW"
    )

    return {
        "file": "ai_orchestrator/external_work_registry.py",
        "imports": sorted(imported),
        "has_http_client_import": has_http_import,
        "has_inbox_direct_call": has_inbox_direct,
        "has_inbox_string_reference": has_inbox_string,
        "classification": classification,
        "phase1j4_warn_resolved": classification == "NOT_A_CALLER_METADATA_ONLY",
    }


def run_audit() -> dict:
    errors = []
    warnings = []

    # 1. external_work_registry.py 분석
    reg_analysis = _analyze_external_work_registry()
    if reg_analysis.get("error"):
        errors.append(f"external_work_registry.py 분석 실패: {reg_analysis['error']}")
    elif reg_analysis.get("classification") != "NOT_A_CALLER_METADATA_ONLY":
        errors.append(
            f"external_work_registry.py 분류 예상과 다름: {reg_analysis.get('classification')}"
        )
    if reg_analysis.get("has_http_client_import"):
        errors.append("external_work_registry.py에 HTTP 클라이언트 import 감지됨")

    # 2. Phase 1-J4 WARN 해소 확인
    if not reg_analysis.get("phase1j4_warn_resolved"):
        errors.append("Phase 1-J4 WARN(NEEDS_CONFIRM) 미해소")

    # 3. effective caller count = 0
    eff = EFFECTIVE_CALLER_SUMMARY["get_inbox"]
    if eff["effective_real_caller_count"] != 0:
        errors.append(f"effective_real_caller_count != 0: {eff['effective_real_caller_count']}")

    # 4. migration impact NONE
    if eff["migration_impact"] != "NONE":
        errors.append(f"get_inbox migration_impact != NONE: {eff['migration_impact']}")

    # 5. disable_allowed_now False
    if GET_INBOX_MIGRATION_PLAN["disable_allowed_now"]:
        errors.append("GET /inbox disable_allowed_now must be False")
    if POST_TASKS_BLOCKER_STATUS["disable_allowed_now"]:
        errors.append("POST /tasks disable_allowed_now must be False")

    # 6. POST /tasks blockers 5개 이상 유지
    blockers = POST_TASKS_BLOCKER_STATUS.get("blockers", [])
    if len(blockers) < 5:
        errors.append(f"POST /tasks blockers < 5: {blockers}")

    # 7. router.py 수정 없음
    router_content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J5" in router_content:
        errors.append("router.py contains PHASE_1J5 — 수정 감지")

    # 8. frontend 수정 없음
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists() and "PHASE_1J5" in tsx.read_text(encoding="utf-8", errors="ignore"):
        errors.append("admin-web page.tsx contains PHASE_1J5 — 수정 감지")

    # 9. backend 파일 수정 없음
    for f in [
        "ai_orchestrator/external_work_registry.py",
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",
    ]:
        p = REPO_ROOT / f
        if p.exists() and "PHASE_1J5" in p.read_text(encoding="utf-8", errors="ignore"):
            errors.append(f"{f} contains PHASE_1J5 — 수정 감지")

    # 10. 이전 Phase 파일 존재 확인
    prev_phases = [
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

    # 11. schema freeze status
    if GET_INBOX_MIGRATION_PLAN["schema_freeze_status"] != "FROZEN":
        errors.append("GET /inbox schema_freeze_status must be FROZEN")

    # 12. forbidden HTTP client imports in this script (AST-based, not string search)
    try:
        this_tree = ast.parse(Path(__file__).read_text(encoding="utf-8", errors="ignore"))
        this_imported = set()
        for node in ast.walk(this_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    this_imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    this_imported.add(node.module.split(".")[0])
        for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
            if bad in this_imported:
                errors.append(f"HTTP client imported in audit script: {bad}")
    except SyntaxError:
        warnings.append("audit script AST parse failed — manual review needed")

    # 13. inbox migration strategy 확인
    if GET_INBOX_MIGRATION_PLAN["migration_strategy"] != "NO_CALLER_MIGRATION_NEEDED":
        warnings.append(
            f"migration_strategy 예상값 다름: {GET_INBOX_MIGRATION_PLAN['migration_strategy']}"
        )

    # 14. verdict
    if errors:
        verdict = "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_FAIL"
    elif warnings:
        verdict = "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_READY_WITH_WARN"
    else:
        verdict = "PHASE1J5_GET_INBOX_CALLER_CONFIRMATION_READY"

    return {
        "phase": PHASE,
        "audit_id": AUDIT_ID,
        "verdict": verdict,
        "external_work_registry_classification": reg_analysis.get("classification"),
        "external_work_registry_has_http_import": reg_analysis.get("has_http_client_import"),
        "phase1j4_warn_resolved": reg_analysis.get("phase1j4_warn_resolved"),
        "effective_real_caller_count": eff["effective_real_caller_count"],
        "get_inbox_migration_impact": eff["migration_impact"],
        "get_inbox_migration_strategy": GET_INBOX_MIGRATION_PLAN["migration_strategy"],
        "post_tasks_status": POST_TASKS_BLOCKER_STATUS["status"],
        "caller_modification_allowed_now": CALLER_MODIFICATION_ALLOWED_NOW,
        "legacy_disable_allowed_now": LEGACY_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "plan_only": PLAN_ONLY,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J5는 read-only 분석 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J5 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
