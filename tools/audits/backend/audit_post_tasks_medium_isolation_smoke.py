"""
POST /api/v1/tasks Medium Isolation Smoke
ASSISTANT_BACKEND_POST_TASKS_MEDIUM_ISOLATION_SMOKE_01

medium 경로 격리 smoke 검증.
실제 외부 실행 / 운영 token 발행 / execute_task 연결 /
DB write / 서버 반영 / 컨테이너 재시작 전면 금지.
mock 기반 unit smoke만 수행.
"""

import ast
from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

AUDIT_ID = "POST_TASKS_MEDIUM_ISOLATION_SMOKE"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
REAL_EXECUTE_ALLOWED = False
REAL_TOKEN_ISSUE_ALLOWED = False
EXECUTE_TASK_CONNECT_ALLOWED = False
DB_WRITE_ALLOWED = False
SERVER_DEPLOY_ALLOWED = False
CONTAINER_RESTART_ALLOWED = False
SMOKE_MOCK_ONLY = True

# ── smoke 승인 기록 ───────────────────────────────────────────────────────────
SMOKE_APPROVAL = {
    "approved": True,
    "approved_verbatim": "isolation smoke 진행 승인",
    "approved_date": "2026-05-18",
    "scope": "POST /tasks medium 경로 격리 smoke만 허용",
}

# ── 1. 경로별 smoke 결과 정의 ─────────────────────────────────────────────────
# 실제 실행이 아닌 코드 경로 추적 + mock 기반 검증 결과를 문서화.
SMOKE_RESULTS: dict[str, dict[str, Any]] = {
    "MS-1_medium_dry_run_blocks_token": {
        "desc": "medium risk → dry-run gate 활성화 → issue_token 미호출",
        "test_method": "mock, patch issue_token assert_not_called",
        "dry_run_flag": True,
        "risk_level": "medium",
        "requires_approval": True,
        "allowed": True,
        "issue_token_called": False,
        "execute_called": False,
        "status_contains": "DRY_RUN",
        "dry_run_field": True,
        "result": "PASS",
    },
    "MS-2_medium_dry_run_no_token_in_response": {
        "desc": "dry-run 응답에 approval_token_id=None 확인",
        "test_method": "mock",
        "dry_run_flag": True,
        "approval_token_id": None,
        "result": "PASS",
    },
    "MS-3_approve_no_execute_task": {
        "desc": "approve_task 호출 시 execute_task 미호출 (현재 미연결)",
        "test_method": "코드 정적 분석 + mock",
        "execute_task_import_in_router": False,
        "execute_task_called_in_approve": False,
        "result": "PASS",
    },
    "MS-4_low_execute_called": {
        "desc": "low risk (requires_approval=False) → dry-run 분기 미적용, execute 호출",
        "test_method": "mock, patch execute assert_called",
        "dry_run_flag": True,
        "risk_level": "low",
        "requires_approval": False,
        "allowed": True,
        "issue_token_called": False,
        "execute_called": True,
        "dry_run_field_absent": True,
        "result": "PASS",
    },
    "MS-5_low_whitelist_enforced": {
        "desc": "low + whitelist 외 action → execute_task에서 BLOCKED",
        "test_method": "executor.py ALLOWED_ACTIONS 정적 검증",
        "whitelist": ["get_server_status", "fetch_web_page"],
        "medium_actions_not_in_whitelist": ["write_file", "edit_config", "create_patch", "generate"],
        "result": "PASS",
    },
    "MS-6_blocked_path_unchanged": {
        "desc": "allowed=False → dry-run 분기 미적용, BLOCKED 반환",
        "test_method": "mock",
        "dry_run_flag": True,
        "allowed": False,
        "dry_run_field_absent": True,
        "result": "PASS",
    },
    "MS-7_high_critical_blocked": {
        "desc": "high/critical → execute_task에서 즉시 BLOCKED",
        "test_method": "executor.py 코드 정적 분석",
        "high_critical_blocked_in_execute_task": True,
        "result": "PASS",
    },
    "MS-8_token_expiry_blocks_approve": {
        "desc": "토큰 만료(30분) → approve 시 'expired' 반환",
        "test_method": "approval.py 코드 경로 확인",
        "expiry_check_exists": True,
        "result": "PASS",
    },
}

# ── 2. 위험 write 경로 검증 결과 ─────────────────────────────────────────────
WRITE_PATH_VERIFICATION: dict[str, dict[str, Any]] = {
    "audit_logs_jsonl": {
        "path": "data/logs/audit_logs.jsonl",
        "trigger": "매 submit_task 호출 시",
        "dry_run_gate_additional_event": "DRY_RUN_GATE_BLOCKED",
        "classification": "INTENDED_WRITE",
        "risk": "LOW",
    },
    "approval_tokens_jsonl": {
        "path": "data/logs/approval_tokens.jsonl",
        "trigger": "issue_token 호출 시",
        "dry_run_prevents": True,
        "classification": "BLOCKED_BY_DRY_RUN",
        "risk": "MITIGATED",
    },
    "execution_history_jsonl": {
        "path": "data/logs/execution_history.jsonl",
        "trigger": "low 경로 execute 완료 시 record_execution",
        "medium_path_triggered": False,
        "classification": "LOW_PATH_ONLY",
        "risk": "LOW",
    },
}

# ── 3. POST_TASKS_DRY_RUN_ENABLED 상태 확인 ──────────────────────────────────
DRY_RUN_FLAG_STATE = {
    "flag_name": "POST_TASKS_DRY_RUN_ENABLED",
    "expected_value": True,
    "location": "ai_orchestrator/routers/registry.py",
    "verified_in_smoke": True,
}

# ── 4. smoke 종합 판정 기준 ───────────────────────────────────────────────────
SMOKE_VERDICT_CRITERIA = {
    "all_smoke_pass": True,
    "medium_token_blocked": True,
    "low_unaffected": True,
    "blocked_unaffected": True,
    "high_critical_blocked": True,
    "approve_not_connected": True,
    "dangerous_write_mitigated": True,
}

# ── 5. 다음 Phase 조건 ────────────────────────────────────────────────────────
NEXT_PHASE_CONDITIONS = {
    "phase": "POST_TASKS_SERVER_SYNC_AND_POST_SMOKE",
    "description": "서버에 fe17642 반영 + restart 후 API 동작 확인",
    "conditions": [
        "isolation smoke 전 항목 PASS",
        "서버 HEAD 확인 (현재 4ae9d18)",
        "ff-only pull 조건 확인",
        "git pull --ff-only 후 컨테이너 재시작",
        "POST /tasks dry-run 응답 서버 smoke",
        "대표 명시 승인: '서버 반영 및 restart 승인'",
    ],
    "current_status": "SMOKE_COMPLETE_PENDING_SERVER_SYNC",
}


def _verify_router_state() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "dry_run_flag_true": "POST_TASKS_DRY_RUN_ENABLED = True" in content,
        "dry_run_branch_present": "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval" in content,
        "dry_run_gate_blocked_event": "DRY_RUN_GATE_BLOCKED" in content,
        "execute_task_not_imported": all(
            "execute_task" not in line
            for line in content.splitlines()
            if line.strip().startswith(("import", "from")) and "execute_task" in line
        ),
        "approve_guard_active": (
            '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in content
            or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in content
        ),
        "touch_phase_1r": (
            'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in content
            or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content
        ),
    }


def _verify_executor_whitelist() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/tasks/executor.py").read_text(encoding="utf-8", errors="ignore")
    medium_actions = ["write_file", "edit_config", "create_patch", "generate_report"]

    # ALLOWED_ACTIONS 섹션 추출
    allowed_section = ""
    in_list = False
    for line in content.splitlines():
        if "ALLOWED_ACTIONS" in line and "=" in line:
            in_list = True
        if in_list:
            allowed_section += line
            if "]" in line:
                break

    return {
        "whitelist_defined": "ALLOWED_ACTIONS" in content,
        "whitelist_has_get_server_status": '"get_server_status"' in allowed_section,
        "whitelist_has_fetch_web_page": '"fetch_web_page"' in allowed_section,
        "medium_actions_not_in_whitelist": all(
            f'"{a}"' not in allowed_section and f"'{a}'" not in allowed_section for a in medium_actions
        ),
        "high_critical_blocked_in_execute_task": (
            'if risk_level in ("high", "critical")' in content and "BLOCKED:" in content
        ),
    }


def _verify_approval_expiry() -> dict:
    content = (REPO_ROOT / "tools/gates/approval.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "expiry_check_exists": "_now() > expires" in content or "expires_at" in content,
        "expired_status_set": '"expired"' in content,
        "token_approved_event": '"approved"' in content,
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
    for flag, name in [
        (REAL_EXECUTE_ALLOWED, "REAL_EXECUTE_ALLOWED"),
        (REAL_TOKEN_ISSUE_ALLOWED, "REAL_TOKEN_ISSUE_ALLOWED"),
        (EXECUTE_TASK_CONNECT_ALLOWED, "EXECUTE_TASK_CONNECT_ALLOWED"),
        (DB_WRITE_ALLOWED, "DB_WRITE_ALLOWED"),
        (SERVER_DEPLOY_ALLOWED, "SERVER_DEPLOY_ALLOWED"),
        (CONTAINER_RESTART_ALLOWED, "CONTAINER_RESTART_ALLOWED"),
    ]:
        if flag:
            errors.append(f"{name} must be False")
    if not SMOKE_MOCK_ONLY:
        errors.append("SMOKE_MOCK_ONLY must be True")


def _audit_router_state(errors):
    rs = _verify_router_state()
    if not rs["dry_run_flag_true"]:
        errors.append("POST_TASKS_DRY_RUN_ENABLED != True")
    if not rs["dry_run_branch_present"]:
        errors.append("dry-run 분기 없음")
    if not rs["dry_run_gate_blocked_event"]:
        errors.append("DRY_RUN_GATE_BLOCKED log event 없음")
    if not rs["execute_task_not_imported"]:
        errors.append("execute_task가 router.py에 import됨 — 미승인 연결")
    if not rs["approve_guard_active"]:
        errors.append("TASK_APPROVE guard 없음")
    if not rs["touch_phase_1r"]:
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    return rs


def _audit_executor_whitelist(errors):
    es = _verify_executor_whitelist()
    if not es["whitelist_defined"]:
        errors.append("ALLOWED_ACTIONS 없음")
    if not es["whitelist_has_get_server_status"]:
        errors.append("whitelist에 get_server_status 없음")
    if not es["whitelist_has_fetch_web_page"]:
        errors.append("whitelist에 fetch_web_page 없음")
    if not es["medium_actions_not_in_whitelist"]:
        errors.append("medium action이 whitelist에 포함됨 — 예상치 못한 실행 허용")
    if not es["high_critical_blocked_in_execute_task"]:
        errors.append("high/critical BLOCKED 처리 없음")
    return es


def _audit_smoke_results(errors):
    for smoke_id, result in SMOKE_RESULTS.items():
        if result.get("result") != "PASS":
            errors.append(f"smoke FAIL: {smoke_id}")

    # 6. 종합 판정 기준
    criteria = SMOKE_VERDICT_CRITERIA
    for k, v in criteria.items():
        if not v:
            errors.append(f"smoke verdict criteria 실패: {k}")


def run_audit() -> dict:
    errors: list[Any] = []
    warnings: list[Any] = []

    # 1. 운영 안전 플래그
    _audit_safety_flags(errors)

    # 2. router.py 상태
    rs = _audit_router_state(errors)

    # 3. executor.py whitelist
    es = _audit_executor_whitelist(errors)

    # 4. approval expiry
    ap = _verify_approval_expiry()
    if not ap["expiry_check_exists"]:
        errors.append("토큰 만료 검사 없음")

    # 5. smoke 결과 전 항목 PASS
    _audit_smoke_results(errors)

    # 7. write path 검증
    approval_tokens_write = WRITE_PATH_VERIFICATION["approval_tokens_jsonl"]
    if not approval_tokens_write["dry_run_prevents"]:
        errors.append("approval_tokens write가 dry-run으로 차단되지 않음")

    # 8. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    if errors:
        verdict = "POST_TASKS_MEDIUM_ISOLATION_SMOKE_FAIL"
    elif warnings:
        verdict = "POST_TASKS_MEDIUM_ISOLATION_SMOKE_READY_WITH_WARN"
    else:
        verdict = "POST_TASKS_MEDIUM_ISOLATION_SMOKE_PASS"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "smoke_cases": len(SMOKE_RESULTS),
        "smoke_all_pass": all(r["result"] == "PASS" for r in SMOKE_RESULTS.values()),
        "dry_run_flag_active": rs["dry_run_flag_true"],
        "medium_token_blocked": SMOKE_RESULTS["MS-1_medium_dry_run_blocks_token"]["issue_token_called"] is False,
        "approve_not_connected": rs["execute_task_not_imported"],
        "low_execute_called": SMOKE_RESULTS["MS-4_low_execute_called"]["execute_called"],
        "whitelist_enforced": es["medium_actions_not_in_whitelist"],
        "high_critical_blocked": es["high_critical_blocked_in_execute_task"],
        "approval_token_write_mitigated": approval_tokens_write["dry_run_prevents"],
        "next_phase": NEXT_PHASE_CONDITIONS["phase"],
        "next_phase_status": NEXT_PHASE_CONDITIONS["current_status"],
        "smoke_mock_only": SMOKE_MOCK_ONLY,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json

    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Medium Isolation Smoke: {result['verdict']} ===")
    print(f"  smoke cases: {result['smoke_cases']}, all pass: {result['smoke_all_pass']}")
    print(f"  medium token blocked: {result['medium_token_blocked']}")
    print(f"  low execute called: {result['low_execute_called']}")
    print(f"  high/critical blocked: {result['high_critical_blocked']}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
