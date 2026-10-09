"""
POST /api/v1/tasks Side-Effect Gate Design Audit
ASSISTANT_BACKEND_POST_TASKS_SIDE_EFFECT_GATE_DESIGN_01

설계·분석·기준선 작성 전용.
실제 POST /tasks 실행 / execute 호출 / approval_token 발행 / DB write /
router.py 수정 / 서버 반영 전면 금지.
"""

import ast
from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

AUDIT_ID = "POST_TASKS_SIDE_EFFECT_GATE_DESIGN"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ROUTE_EXECUTION_ALLOWED = False  # 실제 POST /tasks 호출 금지
EXECUTE_CALL_ALLOWED = False  # execute() 실제 호출 금지
APPROVAL_TOKEN_ISSUE_ALLOWED = False  # issue_token() 실제 발행 금지
DB_WRITE_ALLOWED = False  # 파일·DB write 금지
ROUTER_MODIFICATION_ALLOWED = False  # router.py 수정 금지
SERVER_DEPLOY_ALLOWED = False  # 서버 반영 금지
DESIGN_ONLY = True  # 설계 전용

# ── 1. POST /tasks 코드 경로 분석 결과 ──────────────────────────────────────
CALL_CHAIN = [
    {
        "step": 1,
        "call": "router.submit_task(body, user)",
        "file": "ai_orchestrator/routers/registry.py",
        "line_approx": 140,
        "side_effects": ["log_event(TASK_RECEIVED) → audit_logs.jsonl write"],
        "blocking": False,
    },
    {
        "step": 2,
        "call": "plan(req)",
        "file": "ai_orchestrator/llm/planner.py",
        "line_approx": 9,
        "side_effects": ["classify_risk()", "evaluate_request() — 모두 pure 계산, write 없음"],
        "blocking": False,
    },
    {
        "step": 3,
        "call": "log_event(PLAN_CREATED)",
        "file": "ai_orchestrator/routers/registry.py",
        "line_approx": 157,
        "side_effects": ["audit_logs.jsonl write"],
        "blocking": False,
    },
    {
        "step": 4,
        "call": "issue_token(req, risk) — ep.requires_approval and ep.allowed 조건 시",
        "file": "tools/gates/approval.py",
        "line_approx": 149,
        "side_effects": [
            "approval_tokens.jsonl 신규 항목 append (파일 write)",
            "인메모리 _store dict 변경",
            "log_event(APPROVAL_ISSUED) → audit_logs.jsonl write",
        ],
        "blocking": True,  # 파일 write 발생
        "condition": "ep.requires_approval is True and ep.allowed is True",
    },
    {
        "step": 5,
        "call": "execute(ep, req, risk_level)",
        "file": "ai_orchestrator/tasks/executor.py",
        "line_approx": 70,
        "side_effects": [
            "low 경로: check_rate_limits() 인메모리 변경",
            "low 경로: record_execution() → execution_history.jsonl write",
            "low + whitelist action: _dispatch_allowed_action() → 실제 외부 실행",
            "requires_approval: 'PENDING_APPROVAL' 반환 (write 없음)",
            "blocked: 'BLOCKED:...' 반환 (write 없음)",
        ],
        "blocking": True,  # low 경로에서 파일 write + 외부 실행 가능
    },
    {
        "step": 6,
        "call": "log_event(DRY_RUN_RETURNED / EXECUTION_RATE_LIMITED / EXECUTION_TIMEOUT)",
        "file": "ai_orchestrator/routers/registry.py",
        "line_approx": 175,
        "side_effects": ["audit_logs.jsonl write"],
        "blocking": False,
    },
]

# ── 2. side-effect 분류 ───────────────────────────────────────────────────────
SIDE_EFFECT_CATALOG = {
    "FILE_WRITE_AUDIT_LOG": {
        "type": "FILE_WRITE",
        "path": "data/logs/audit_logs.jsonl",
        "trigger": "매 submit_task 호출 시 항상 발생 (TASK_RECEIVED, PLAN_CREATED, 결과 이벤트)",
        "risk": "LOW",
        "reversible": True,
        "note": "감사 로그 — 설계상 의도된 write. 실행 rollback 영향 없음.",
    },
    "FILE_WRITE_APPROVAL_TOKENS": {
        "type": "FILE_WRITE",
        "path": "data/logs/approval_tokens.jsonl",
        "trigger": "ep.requires_approval=True and ep.allowed=True 조건 만족 시",
        "risk": "MEDIUM",
        "reversible": False,
        "note": (
            "토큰 생성 후 만료(30분)까지 승인 가능 상태가 됨. "
            "실제 approve_token 호출 없이는 실행으로 이어지지 않으나, "
            "토큰 ID 노출 시 외부 승인 경로가 열릴 수 있음."
        ),
    },
    "FILE_WRITE_EXECUTION_HISTORY": {
        "type": "FILE_WRITE",
        "path": "data/logs/execution_history.jsonl",
        "trigger": "low 경로 실행 시 record_execution() 호출",
        "risk": "LOW",
        "reversible": True,
        "note": "실행 이력 기록. rate limit 판단에 사용되어 후속 호출에 영향.",
    },
    "EXTERNAL_EXECUTION_WHITELIST": {
        "type": "EXTERNAL_CALL",
        "whitelist": ["get_server_status", "fetch_web_page"],
        "trigger": "low 경로 + action_type이 whitelist에 포함될 때",
        "risk": "LOW",
        "reversible": True,
        "note": "read-only 외부 실행. 현재 whitelist 2개만 허용.",
    },
    "MEMORY_RATE_STORE": {
        "type": "IN_MEMORY_WRITE",
        "trigger": "check_rate_limits() 호출 시 인메모리 _rate_store 변경",
        "risk": "LOW",
        "reversible": True,
        "note": "재시작 시 초기화. 60초 윈도우 rate limit 상태만 영향.",
    },
    "MEMORY_APPROVAL_STORE": {
        "type": "IN_MEMORY_WRITE",
        "trigger": "issue_token() 호출 시 _store dict 변경",
        "risk": "MEDIUM",
        "reversible": False,
        "note": "재시작 시 초기화되나, 파일 write와 함께 발생하므로 MEDIUM.",
    },
}

# ── 3. risk level별 실행 경로 분석 ──────────────────────────────────────────
RISK_LEVEL_PATHS = {
    "low": {
        "planner_result": "allowed=True, requires_approval=False",
        "execute_path": "rate limit 체크 → whitelist 실행 또는 DRY_RUN_ONLY",
        "token_issued": False,
        "file_writes": ["audit_logs.jsonl (3회)", "execution_history.jsonl (1회)"],
        "external_execution_possible": True,
        "gate_gap": "whitelist에 없는 action은 BLOCKED. whitelist action은 실제 실행됨.",
    },
    "medium": {
        "planner_result": "allowed=True, requires_approval=True",
        "execute_path": "'PENDING_APPROVAL' 반환 — execute_task 미호출",
        "token_issued": True,
        "file_writes": [
            "audit_logs.jsonl (4회)",
            "approval_tokens.jsonl (1회, 토큰 생성)",
        ],
        "external_execution_possible": False,
        "gate_gap": (
            "토큰 발행 후 30분 이내에 POST /tasks/{id}/approve 가 호출되면 "
            "execute_task 경로로 실제 실행 가능. approve 경로의 gate 설계 필요."
        ),
    },
    "high": {
        "planner_result": "allowed=False 또는 requires_approval=True (정책에 따라)",
        "execute_path": "'BLOCKED:...' 또는 'PENDING_APPROVAL'",
        "token_issued": False,
        "file_writes": ["audit_logs.jsonl (2~3회)"],
        "external_execution_possible": False,
        "gate_gap": "현재 high는 execute_task에서 BLOCKED 처리됨. 안전.",
    },
    "critical": {
        "planner_result": "allowed=False",
        "execute_path": "'BLOCKED:...'",
        "token_issued": False,
        "file_writes": ["audit_logs.jsonl (2~3회)"],
        "external_execution_possible": False,
        "gate_gap": "execute_task에서 즉시 BLOCKED. 안전.",
    },
}

# ── 4. 승인 게이트 설계 (medium 경로 핵심) ───────────────────────────────────
APPROVAL_GATE_DESIGN = {
    "gate_id": "POST_TASKS_MEDIUM_APPROVE_GATE_V1",
    "status": "DESIGN_ONLY",
    "target_route": "POST /api/v1/tasks/{task_id}/approve",
    "current_state": "Phase 1-R guard 있음 (_legacy_5050_should_use_route_wiring('TASK_APPROVE') → False)",
    "required_before_enable": [
        "execute_task 실제 실행 경로 whitelist 재검토 (medium 전용 별도 whitelist 필요)",
        "approve_token → execute_task 연결 경로 감사",
        "approve 호출 가능 role 재확인 (현재 admin, owner)",
        "토큰 만료(30분) 검증 강화 여부 결정",
        "야간 차단 / cooldown 정책 medium 경로 적용 확인",
        "대표 명시 승인",
    ],
    "blockers": [
        "WRITE_POSSIBLE",  # execute_task → 실제 외부 실행 가능
        "execute_side_effect",  # execute() 외부 시스템 호출
        "approval_token_side_effect",  # issue_token → 파일 write + 승인 상태 생성
        "db_write_impact",  # execution_history.jsonl / audit_logs.jsonl
        "approval_gate_not_designed",  # medium approve 이후 execute_task 경로 미검증
    ],
    "disable_allowed_now": False,
    "note": "현재 Phase 1-R guard가 TASK_APPROVE 경로를 no-op으로 유지 중. 이 공정에서 변경 금지.",
}

# ── 5. dry-run 정책 설계 ─────────────────────────────────────────────────────
DRY_RUN_POLICY = {
    "policy_id": "POST_TASKS_DRY_RUN_POLICY_V1",
    "status": "DESIGN_ONLY",
    "principle": ("POST /tasks를 실제 실행으로 전환하기 전에 dry-run 모드를 별도 flag로 명시적으로 활성화해야 한다."),
    "dry_run_flag_location": "router.py 또는 별도 policy 모듈",
    "dry_run_flag_name": "POST_TASKS_DRY_RUN_ENABLED",
    "dry_run_default": True,
    "steps_before_real_run": [
        "1. dry-run flag ON 상태에서 모든 경로 smoke (medium 포함)",
        "2. audit_logs.jsonl / approval_tokens.jsonl / execution_history.jsonl 기록 검증",
        "3. medium approve 경로 isolation test (token 발행 → approve → execute_task 검증)",
        "4. whitelist action 별도 dry-run 정책 확인 (read-only 보장)",
        "5. 대표 명시 승인 후 dry-run flag OFF → 실제 실행 전환",
    ],
    "note": "이 설계는 이번 공정에서 확정만 하고 구현은 다음 Phase에서 수행.",
}

# ── 6. rollback 기준 ─────────────────────────────────────────────────────────
ROLLBACK_CRITERIA = {
    "trigger_conditions": [
        "execute() 호출 후 외부 시스템 비정상 응답",
        "approval_tokens.jsonl 파일 손상",
        "중복 토큰 발행 감지",
        "rate limit 우회 감지",
    ],
    "rollback_command": "git revert <enable_commit_sha> (미래 enable 커밋 대상)",
    "rollback_approval": "대표 명시 승인 필수",
    "force_push": False,
    "note": "이번 공정은 설계만 — 실제 route 변경 없으므로 현재 rollback 불필요.",
}

# ── 7. 다음 Phase 진입 조건 ──────────────────────────────────────────────────
NEXT_PHASE_CONDITIONS = {
    "phase": "POST_TASKS_MEDIUM_APPROVE_GATE_IMPLEMENTATION",
    "all_conditions_must_be_met": [
        "approve 경로 execute_task whitelist 확정",
        "dry-run flag 구현 완료",
        "medium 경로 isolation smoke pass",
        "approval gate 설계 대표 승인",
        "router.py 수정 대표 명시 승인",
    ],
    "current_status": "BLOCKED_DESIGN_ONLY",
    "estimated_phases_remaining": 3,
}


def _check_router_stability() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "post_tasks_handler_exists": '@router.post("/tasks")' in content or "@router.post('/tasks')" in content,
        "task_approve_guard_active": (
            '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in content
            or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in content
        ),
        "task_reject_guard_active": (
            '_legacy_5050_should_use_route_wiring("TASK_REJECT")' in content
            or "_legacy_5050_should_use_route_wiring('TASK_REJECT')" in content
        ),
        "task_approve_flag_false": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in content,
        "task_reject_flag_false": "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in content,
        "no_post_tasks_dry_run_flag": "POST_TASKS_DRY_RUN_ENABLED" not in content,
        "touch_phase": "PHASE_1R"
        if 'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content
        else "UNKNOWN",
    }


def _check_key_files() -> tuple[list, list]:
    required = [
        "ai_orchestrator/routers/registry.py",
        "ai_orchestrator/tasks/executor.py",
        "tools/gates/approval.py",
        "ai_orchestrator/llm/planner.py",
        "ai_orchestrator/core/execution_limits.py",
        # backend/compat/legacy_5050: faf799bd(2026-09-23 타앱 연결 2차 삭제)에서 이동 없이 삭제됨 -> 필수 목록에서 제외
    ]
    present, missing = [], []
    for f in required:
        if (REPO_ROOT / f).exists():
            present.append(f)
        else:
            missing.append(f)
    return present, missing


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
    return True, "HTTP client import 없음"


def _audit_router_stability(errors, warnings):
    rs = _check_router_stability()
    if not rs["post_tasks_handler_exists"]:
        errors.append("POST /tasks handler 없음")
    if not rs["task_approve_guard_active"]:
        errors.append("TASK_APPROVE guard 없음 — Phase 1-R 안전장치 소실")
    if not rs["task_reject_guard_active"]:
        errors.append("TASK_REJECT guard 없음 — Phase 1-R 안전장치 소실")
    if not rs["task_approve_flag_false"]:
        errors.append("TASK_APPROVE flag가 False가 아님 — guard 우회 위험")
    if not rs["task_reject_flag_false"]:
        errors.append("TASK_REJECT flag가 False가 아님 — guard 우회 위험")
    if rs["touch_phase"] != "PHASE_1R":
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    if not rs["no_post_tasks_dry_run_flag"]:
        warnings.append("POST_TASKS_DRY_RUN_ENABLED flag 이미 존재 — 설계 범위 초과 여부 확인 필요")
    return rs


def _audit_safety_flags(errors):
    if ROUTE_EXECUTION_ALLOWED:
        errors.append("ROUTE_EXECUTION_ALLOWED must be False")
    if EXECUTE_CALL_ALLOWED:
        errors.append("EXECUTE_CALL_ALLOWED must be False")
    if APPROVAL_TOKEN_ISSUE_ALLOWED:
        errors.append("APPROVAL_TOKEN_ISSUE_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if ROUTER_MODIFICATION_ALLOWED:
        errors.append("ROUTER_MODIFICATION_ALLOWED must be False")
    if SERVER_DEPLOY_ALLOWED:
        errors.append("SERVER_DEPLOY_ALLOWED must be False")
    if not DESIGN_ONLY:
        errors.append("DESIGN_ONLY must be True")


def _audit_catalog_and_gate(errors):
    required_effects = [
        "FILE_WRITE_AUDIT_LOG",
        "FILE_WRITE_APPROVAL_TOKENS",
        "FILE_WRITE_EXECUTION_HISTORY",
        "EXTERNAL_EXECUTION_WHITELIST",
        "MEMORY_RATE_STORE",
        "MEMORY_APPROVAL_STORE",
    ]
    for e in required_effects:
        if e not in SIDE_EFFECT_CATALOG:
            errors.append(f"side-effect 누락: {e}")

    # 5. approval gate 설계 완전성
    gate = APPROVAL_GATE_DESIGN
    if gate["disable_allowed_now"]:
        errors.append("APPROVAL_GATE disable_allowed_now must be False")
    if len(gate["blockers"]) < 5:
        errors.append("approval gate blockers < 5")
    if gate["status"] != "DESIGN_ONLY":
        errors.append("APPROVAL_GATE status must be DESIGN_ONLY")


def run_audit() -> dict:
    errors = []
    warnings: list[Any] = []

    # 1. 핵심 파일 존재
    present, missing = _check_key_files()  # noqa: RUF059 — present 는 표시용, 실제 사용은 missing
    for f in missing:
        errors.append(f"필수 파일 없음: {f}")

    # 2. router.py 안정성
    rs = _audit_router_stability(errors, warnings)

    # 3. 운영 안전 플래그
    _audit_safety_flags(errors)

    # 4. side-effect catalog 완전성
    _audit_catalog_and_gate(errors)

    # 6. call chain 완전성
    if len(CALL_CHAIN) < 5:
        errors.append("CALL_CHAIN steps < 5")

    # 7. risk level paths 완전성
    for level in ("low", "medium", "high", "critical"):
        if level not in RISK_LEVEL_PATHS:
            errors.append(f"RISK_LEVEL_PATHS에 {level} 누락")

    # 8. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # verdict
    if errors:
        verdict = "POST_TASKS_SIDE_EFFECT_GATE_DESIGN_FAIL"
    elif warnings:
        verdict = "POST_TASKS_SIDE_EFFECT_GATE_DESIGN_READY_WITH_WARN"
    else:
        verdict = "POST_TASKS_SIDE_EFFECT_GATE_DESIGN_READY"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "router_stability": rs,
        "side_effect_count": len(SIDE_EFFECT_CATALOG),
        "call_chain_steps": len(CALL_CHAIN),
        "risk_levels_analyzed": list(RISK_LEVEL_PATHS.keys()),
        "approval_gate_status": APPROVAL_GATE_DESIGN["status"],
        "blockers_count": len(APPROVAL_GATE_DESIGN["blockers"]),
        "dry_run_policy_status": DRY_RUN_POLICY["status"],
        "next_phase": NEXT_PHASE_CONDITIONS["phase"],
        "next_phase_status": NEXT_PHASE_CONDITIONS["current_status"],
        "design_only": DESIGN_ONLY,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json

    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== POST /tasks Side-Effect Gate Design: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
