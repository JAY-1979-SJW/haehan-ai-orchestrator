"""
POST /api/v1/tasks Dry-Run Flag Implementation Audit
ASSISTANT_BACKEND_POST_TASKS_DRY_RUN_FLAG_IMPLEMENTATION

POST_TASKS_DRY_RUN_ENABLED=True 플래그 및 submit_task 분기 구현 검증.
실제 approval token 발행 / approve 호출 / execute_task 호출 /
DB write / 서버 반영 전면 금지.
"""

import ast
from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

AUDIT_ID = "POST_TASKS_DRY_RUN_FLAG_IMPLEMENTATION"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
APPROVAL_TOKEN_ISSUE_ALLOWED = False
EXECUTE_TASK_CALL_ALLOWED = False
DB_WRITE_ALLOWED = False
SERVER_DEPLOY_ALLOWED = False
IMPLEMENTATION_SCOPE = "DRY_RUN_FLAG_AND_SUBMIT_BRANCH_ONLY"

# ── 구현 확정 사항 ────────────────────────────────────────────────────────────
IMPLEMENTATION_RECORD = {
    "flag_name": "POST_TASKS_DRY_RUN_ENABLED",
    "flag_default": True,
    "flag_location": "ai_orchestrator/routers/registry.py (Phase 1-R feature flag 섹션 하단)",
    "branch_location": "submit_task() — issue_token 호출 전",
    "branch_condition": "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval and ep.allowed",
    "branch_behavior": (
        "조건 충족 시: log_event(DRY_RUN_GATE_BLOCKED) 기록 후 "
        "'DRY_RUN: would issue token — gate active' 상태 반환. "
        "issue_token() 미호출 — 토큰 발행 없음."
    ),
    "low_path_unaffected": ("requires_approval=False인 low 경로는 dry-run 분기를 통과하지 않음 → 기존 동작 그대로."),
    "blocked_path_unaffected": ("ep.allowed=False인 차단 경로도 dry-run 분기 미적용 → BLOCKED 반환 그대로."),
    "approve_route_impact": (
        "approve_task는 dry-run 상태에서 토큰이 발행되지 않으므로 토큰 조회 시 not_found 반환 — 자연 격리."
    ),
    "router_modification_approved": True,
    "approved_by": "대표 명시 승인 2026-05-18",
    "approved_verbatim": "POST_TASKS_DRY_RUN_ENABLED 플래그 추가 및 submit_task 분기 승인",
}

# ── 영향받는 경로 분석 ────────────────────────────────────────────────────────
PATH_IMPACT_ANALYSIS = {
    "medium_requires_approval_True_allowed_True": {
        "before": "issue_token() 호출 → PENDING_APPROVAL 반환",
        "after": "DRY_RUN 분기 → 'DRY_RUN: would issue token' 반환, 토큰 없음",
        "token_issued": False,
        "file_writes": ["audit_logs.jsonl (DRY_RUN_GATE_BLOCKED 이벤트 1회)"],
    },
    "low_requires_approval_False": {
        "before": "execute() 직접 호출",
        "after": "변경 없음 — dry-run 분기 미적용",
        "token_issued": False,
        "file_writes": ["기존과 동일"],
    },
    "blocked_allowed_False": {
        "before": "BLOCKED: 반환",
        "after": "변경 없음 — dry-run 분기 미적용",
        "token_issued": False,
        "file_writes": ["기존과 동일"],
    },
    "high_critical": {
        "before": "allowed=False or requires_approval=True, BLOCKED/PENDING",
        "after": "변경 없음 — policy/planner 단계에서 처리",
        "token_issued": False,
        "file_writes": ["기존과 동일"],
    },
}

# ── 다음 Phase 진입 조건 ──────────────────────────────────────────────────────
NEXT_PHASE_CONDITIONS = {
    "phase": "POST_TASKS_MEDIUM_ISOLATION_SMOKE",
    "all_conditions_must_be_met": [
        "POST_TASKS_DRY_RUN_ENABLED=True 플래그 router.py 반영 확인",
        "submit_task dry-run 분기 unit test 통과",
        "medium 경로 issue_token 미호출 확인",
        "low 경로 영향 없음 확인",
        "approve 경로 not_found 자연 격리 확인",
        "대표 승인: isolation smoke 진행",
    ],
    "current_status": "PREFLIGHT_COMPLETE_PENDING_SMOKE",
}


def _check_router_implementation() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "dry_run_flag_present": "POST_TASKS_DRY_RUN_ENABLED = True" in content,
        "dry_run_flag_default_true": "POST_TASKS_DRY_RUN_ENABLED = True" in content,
        "dry_run_branch_present": "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval" in content,
        "dry_run_log_event_present": "DRY_RUN_GATE_BLOCKED" in content,
        "dry_run_status_string": "DRY_RUN: would issue token" in content,
        "dry_run_field_in_response": '"dry_run": True' in content or "'dry_run': True" in content,
        "issue_token_still_present": "issue_token(req, risk" in content,
        "execute_task_not_imported": "execute_task"
        not in content.split("from ..tasks.executor import")[1].split("\n")[0]
        if "from ..tasks.executor import" in content
        else True,
        "phase_1r_guards_intact": (
            "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in content
            and "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in content
        ),
        "touch_phase_1r": (
            'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in content
            or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content
        ),
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
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for bad in ["requests", "httpx", "aiohttp", "urllib3"]:
        if bad in imported:
            return False, f"HTTP client imported: {bad}"
    return True, "OK"


def _audit_safety_flags(errors):
    if APPROVAL_TOKEN_ISSUE_ALLOWED:
        errors.append("APPROVAL_TOKEN_ISSUE_ALLOWED must be False")
    if EXECUTE_TASK_CALL_ALLOWED:
        errors.append("EXECUTE_TASK_CALL_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if SERVER_DEPLOY_ALLOWED:
        errors.append("SERVER_DEPLOY_ALLOWED must be False")


def _audit_router_impl(errors):
    ri = _check_router_implementation()
    if not ri["dry_run_flag_present"]:
        errors.append("POST_TASKS_DRY_RUN_ENABLED = True 플래그 없음")
    if not ri["dry_run_flag_default_true"]:
        errors.append("POST_TASKS_DRY_RUN_ENABLED 기본값이 True가 아님")
    if not ri["dry_run_branch_present"]:
        errors.append("dry-run 분기 코드 없음 (POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval)")
    if not ri["dry_run_log_event_present"]:
        errors.append("DRY_RUN_GATE_BLOCKED log_event 없음")
    if not ri["dry_run_status_string"]:
        errors.append("'DRY_RUN: would issue token' 상태 문자열 없음")
    if not ri["dry_run_field_in_response"]:
        errors.append("응답에 dry_run=True 필드 없음")
    if not ri["issue_token_still_present"]:
        errors.append("issue_token 호출 코드 삭제됨 — dry-run flag OFF 경로 보존 필요")
    if not ri["phase_1r_guards_intact"]:
        errors.append("Phase 1-R guard 소실")
    if not ri["touch_phase_1r"]:
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    return ri


def _audit_path_impact(errors):
    for path_key in (
        "medium_requires_approval_True_allowed_True",
        "low_requires_approval_False",
        "blocked_allowed_False",
        "high_critical",
    ):
        if path_key not in PATH_IMPACT_ANALYSIS:
            errors.append(f"경로 분석 누락: {path_key}")

    medium_impact = PATH_IMPACT_ANALYSIS["medium_requires_approval_True_allowed_True"]
    if medium_impact["token_issued"]:
        errors.append("medium 경로에서 토큰 발행됨 — dry-run 분기 오류")


def run_audit() -> dict:
    errors: list[Any] = []
    warnings: list[Any] = []

    # 1. 운영 안전 플래그
    _audit_safety_flags(errors)

    # 2. 구현 검증
    ri = _audit_router_impl(errors)

    # 3. 구현 기록 완전성
    rec = IMPLEMENTATION_RECORD
    if not rec["router_modification_approved"]:
        errors.append("router 수정 승인 기록 없음")
    if not rec["flag_default"]:
        errors.append("flag_default must be True")

    # 4. 경로 영향 분석 완전성
    _audit_path_impact(errors)

    # 5. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    if errors:
        verdict = "POST_TASKS_DRY_RUN_IMPLEMENTATION_FAIL"
    elif warnings:
        verdict = "POST_TASKS_DRY_RUN_IMPLEMENTATION_READY_WITH_WARN"
    else:
        verdict = "POST_TASKS_DRY_RUN_IMPLEMENTATION_READY"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "router_impl": ri,
        "dry_run_flag": "POST_TASKS_DRY_RUN_ENABLED = True",
        "dry_run_branch_active": ri["dry_run_branch_present"],
        "phase_1r_guards_intact": ri["phase_1r_guards_intact"],
        "next_phase": NEXT_PHASE_CONDITIONS["phase"],
        "next_phase_status": NEXT_PHASE_CONDITIONS["current_status"],
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json

    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Dry-Run Flag Implementation: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
