"""
POST /api/v1/tasks Medium Approve Gate Preflight
ASSISTANT_BACKEND_POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_01

approve → execute_task 연결 경로 preflight.
실제 approval token 발행 / approve 호출 / execute_task 호출 /
DB write / router.py 수정 / 서버 반영 전면 금지.
이번 공정은 medium approve gate 진입 조건 확정까지만.
"""

import ast
from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

AUDIT_ID = "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
APPROVAL_TOKEN_ISSUE_ALLOWED = False
APPROVE_CALL_ALLOWED = False
EXECUTE_TASK_CALL_ALLOWED = False
DB_WRITE_ALLOWED = False
ROUTER_MODIFICATION_ALLOWED = False
SERVER_DEPLOY_ALLOWED = False
PREFLIGHT_ONLY = True

# ── 1. 핵심 발견: approve → execute_task 연결 현황 ───────────────────────────
APPROVE_EXECUTE_CONNECTION_ANALYSIS = {
    "finding_id": "APPROVE_EXECUTE_NOT_CONNECTED",
    "severity": "CRITICAL_GAP_FOUND",
    "description": (
        "POST /tasks/{id}/approve (router.py:191) 는 approve_token() 호출 후 "
        "토큰 status를 'approved'로 변경만 하고 execute_task()를 호출하지 않는다. "
        "execute_task는 router.py에서 import조차 되지 않음."
    ),
    "implication": (
        "현재 medium 경로에서 토큰이 approved 상태가 돼도 "
        "실제 execute_task 실행으로 이어지는 경로가 없다. "
        "submit_task가 'PENDING_APPROVAL'을 반환하면 그걸로 끝 — 실행 없음."
    ),
    "current_safety": "SAFE_BY_INCOMPLETENESS",
    "risk_if_connected": (
        "approve 이후 execute_task 연결이 추가되면 "
        "whitelist 검증 + policy 검증이 작동하지만, "
        "해당 연결 자체가 신규 attack surface가 됨."
    ),
    "router_import_check": "from ..tasks.executor import execute  (execute만 import, execute_task 없음)",
}

# ── 2. medium 경로 전체 흐름 (현재 상태) ─────────────────────────────────────
MEDIUM_PATH_CURRENT_STATE: dict[str, Any] = {
    "step_1": {
        "route": "POST /api/v1/tasks",
        "handler": "submit_task()",
        "plan_result": "allowed=True, requires_approval=True (medium)",
        "issue_token": "O — approval_tokens.jsonl에 write",
        "execute_result": "'PENDING_APPROVAL' 반환",
        "execute_task_called": False,
        "side_effects": ["audit_logs.jsonl 3회", "approval_tokens.jsonl 1회"],
    },
    "step_2": {
        "route": "POST /api/v1/tasks/{task_id}/approve",
        "handler": "approve_task()",
        "guard": "_legacy_5050_should_use_route_wiring('TASK_APPROVE') → False → guard pass",
        "approve_token_called": True,
        "execute_task_called": False,
        "result": "status='approved' 토큰 상태 변경만",
        "side_effects": [
            "approval_tokens.jsonl 업데이트",
            "audit_logs.jsonl 1회 (APPROVAL_GRANTED)",
        ],
    },
    "gap": ("approve 이후 execute_task 미호출 → 실제 작업 실행 없음. 'PENDING_APPROVAL' 상태의 task는 영구 미실행."),
}

# ── 3. Phase 1-R guard 현황 (approve 경로) ───────────────────────────────────
PHASE_1R_GUARD_STATUS = {
    "TASK_APPROVE_guard": {
        "flag": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED",
        "current_value": False,
        "guard_function": "_legacy_5050_should_use_route_wiring('TASK_APPROVE')",
        "guard_behavior": (
            "False → guard 통과 (approve_token 정상 호출). "
            "True 시 RuntimeError('PHASE_1R route wiring is disabled by default') 발생."
        ),
        "semantic_note": (
            "이 guard는 5050 legacy wiring 전환 여부를 제어하는 것이지, "
            "approve_token 자체를 막는 게 아니다. "
            "flag=False여도 approve_task는 정상 동작하며 토큰 상태를 변경한다."
        ),
        "safe": True,
    },
    "TASK_REJECT_guard": {
        "flag": "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED",
        "current_value": False,
        "guard_function": "_legacy_5050_should_use_route_wiring('TASK_REJECT')",
        "guard_behavior": "False → guard 통과 (reject_token 정상 호출).",
        "safe": True,
    },
    "conclusion": (
        "Phase 1-R guard는 5050 wiring 차단 목적. "
        "approve 자체 실행은 flag=False에서도 허용됨. "
        "추가 approve gate 설계 필요."
    ),
}

# ── 4. execute_task whitelist 검토 ───────────────────────────────────────────
EXECUTE_TASK_WHITELIST_ANALYSIS = {
    "current_whitelist": ["get_server_status", "fetch_web_page"],
    "whitelist_location": "ai_orchestrator/tasks/executor.py:ALLOWED_ACTIONS",
    "medium_path_applicable": (
        "approve → execute_task 연결이 추가될 때 동일 whitelist 적용됨. "
        "medium 요청의 action_type이 whitelist에 없으면 BLOCKED:not_allowed_action."
    ),
    "whitelist_gap": (
        "medium 경로 action_type('write', 'edit', 'create_patch', 'generate' 계열)은 "
        "현재 whitelist에 없음 → approve 후에도 BLOCKED 처리됨. "
        "medium 전용 whitelist 별도 설계 필요."
    ),
    "recommended_action": (
        "medium approve 경로 전용 whitelist를 executor.py에 별도 정의. 현재 ALLOWED_ACTIONS와 혼용 금지."
    ),
    "design_status": "PENDING",
}

# ── 5. dry-run flag 구현 범위 확정 ───────────────────────────────────────────
DRY_RUN_FLAG_SCOPE = {
    "flag_name": "POST_TASKS_DRY_RUN_ENABLED",
    "default_value": True,
    "location": "ai_orchestrator/routers/registry.py (feature flag 섹션)",
    "scope": "submit_task + approve_task 양쪽에 적용",
    "behavior_when_true": (
        "submit_task: issue_token 호출 전 dry-run 분기 — 토큰 발행 없이 "
        "'DRY_RUN: would issue token for medium risk' 반환. "
        "approve_task: 토큰 없으면 not_found 반환 (dry-run에서 발행 안 됐으므로 자연 차단)."
    ),
    "behavior_when_false": "현재 동작 그대로 — issue_token 발행 + approve 상태 변경.",
    "implementation_phase": "NEXT_PHASE (이번 공정에서 구현 금지)",
    "current_status": "DESIGN_CONFIRMED",
    "router_modification_required": True,
    "modification_approval_required": True,
}

# ── 6. medium isolation smoke 설계 ───────────────────────────────────────────
MEDIUM_ISOLATION_SMOKE_DESIGN = {
    "smoke_id": "MEDIUM_APPROVE_ISOLATION_SMOKE_V1",
    "status": "DESIGN_ONLY",
    "test_cases": [
        {
            "id": "MS-1",
            "desc": "medium risk action_type('write_file') submit → 'PENDING_APPROVAL' 반환 확인",
            "method": "unit test, mock issue_token",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-2",
            "desc": "dry-run flag ON 시 issue_token 미호출 확인",
            "method": "unit test, mock issue_token + assert not called",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-3",
            "desc": "approve_task 호출 시 execute_task 미호출 확인 (현재 상태 그대로)",
            "method": "unit test, mock execute_task + assert not called",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-4",
            "desc": "medium action_type이 execute_task whitelist에 없을 때 BLOCKED 확인",
            "method": "unit test, mock execute_task 직접 호출",
            "execute_task_called": True,
            "real_token_issued": False,
            "note": "executor.py ALLOWED_ACTIONS 기반 — 실제 외부 실행 없음",
        },
        {
            "id": "MS-5",
            "desc": "high/critical은 execute_task에서 즉시 BLOCKED 확인",
            "method": "unit test",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-6",
            "desc": "토큰 만료(30분) 이후 approve 시 'expired' 반환 확인",
            "method": "unit test, time mock",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-7",
            "desc": "rate limit 초과 시 approve 차단 확인",
            "method": "unit test",
            "execute_task_called": False,
            "real_token_issued": False,
        },
        {
            "id": "MS-8",
            "desc": "role=operator로 approve 시 'forbidden' 반환 확인",
            "method": "unit test",
            "execute_task_called": False,
            "real_token_issued": False,
        },
    ],
    "implementation_phase": "NEXT_PHASE (이번 공정에서 실제 smoke 실행 금지)",
}

# ── 7. approval token 격리 조건 설계 ─────────────────────────────────────────
TOKEN_ISOLATION_DESIGN = {
    "isolation_id": "APPROVAL_TOKEN_ISOLATION_V1",
    "status": "DESIGN_ONLY",
    "conditions": [
        {
            "condition": "dry-run flag ON",
            "token_issued": False,
            "note": "토큰 발행 자체를 막음 — 가장 강한 격리",
        },
        {
            "condition": "dry-run flag OFF + approve 호출",
            "token_issued": True,
            "execute_task_connected": False,
            "note": "현재 상태 — approve가 토큰 상태 변경 후 execute_task 미호출",
        },
        {
            "condition": "approve 이후 execute_task 연결 추가 시",
            "token_issued": True,
            "execute_task_connected": True,
            "additional_gate_required": True,
            "gate_design": "medium 전용 whitelist + cooldown + role 재검증",
            "note": "이 연결을 추가하는 시점이 별도 Phase (현재 금지)",
        },
    ],
    "current_isolation_level": "LEVEL_2 (approve = 토큰 상태 변경만, execute_task 미연결)",
    "target_isolation_level_before_connect": "LEVEL_3 (dry-run flag + medium whitelist + approval gate 설계 완료)",
}

# ── 8. router.py 수정 필요 여부 판단 ─────────────────────────────────────────
ROUTER_MODIFICATION_ASSESSMENT = {
    "modifications_needed_now": [],
    "modifications_needed_for_dry_run": [
        {
            "change": "POST_TASKS_DRY_RUN_ENABLED = True 플래그 추가",
            "location": "feature flag 섹션 (line 31~35 근처)",
            "risk": "LOW (상수 추가만)",
            "requires_approval": True,
        },
        {
            "change": "submit_task에 dry-run 분기 추가",
            "location": "line 140~188",
            "risk": "MEDIUM (기존 흐름 변경)",
            "requires_approval": True,
        },
    ],
    "modifications_needed_for_execute_connect": [
        {
            "change": "approve_task에서 approve 후 execute_task 호출 추가",
            "location": "line 191~211",
            "risk": "HIGH (신규 실행 경로)",
            "requires_approval": True,
            "current_status": "BLOCKED_DESIGN_ONLY",
        },
    ],
    "current_phase_modification": False,
    "note": "이번 공정에서 router.py 수정 없음. 다음 Phase에서 대표 명시 승인 후 수행.",
}

# ── 9. 대표 승인 조건 고정 ────────────────────────────────────────────────────
REPRESENTATIVE_APPROVAL_CONDITIONS = {
    "for_dry_run_flag_implementation": [
        "medium isolation smoke 설계 검토 완료",
        "dry-run flag ON 동작 unit test 통과",
        "router.py 수정 diff 사전 제출 및 검토",
        "대표 명시 승인: 'POST_TASKS_DRY_RUN_ENABLED 플래그 추가 및 submit_task 분기 승인'",
    ],
    "for_execute_task_connection": [
        "dry-run flag 구현 및 smoke 통과",
        "medium 전용 whitelist 확정",
        "approve → execute_task 연결 diff 사전 제출",
        "isolation test 전 항목 PASS",
        "대표 명시 승인: 'approve 후 execute_task 연결 승인'",
    ],
    "current_approval_status": "BLOCKED_DESIGN_ONLY",
    "approval_received": False,
}

# ── 10. preflight 진입 조건 달성 현황 ────────────────────────────────────────
PREFLIGHT_GATE_STATUS: dict[str, Any] = {
    "condition_1_approve_execute_connection_analyzed": {
        "status": "COMPLETE",
        "finding": "현재 미연결 (SAFE_BY_INCOMPLETENESS)",
    },
    "condition_2_execute_task_whitelist_reviewed": {
        "status": "COMPLETE",
        "finding": "medium action_type 미포함 → approve 후에도 BLOCKED",
    },
    "condition_3_dry_run_flag_scope_confirmed": {
        "status": "COMPLETE",
        "finding": "POST_TASKS_DRY_RUN_ENABLED, default=True, 양쪽 적용",
    },
    "condition_4_medium_isolation_smoke_designed": {
        "status": "COMPLETE",
        "finding": "MS-1~MS-8 설계 완료 (실행은 다음 Phase)",
    },
    "condition_5_token_isolation_conditions_designed": {
        "status": "COMPLETE",
        "finding": "LEVEL_2 현재 → LEVEL_3 목표 설계 완료",
    },
    "condition_6_router_modification_scope_confirmed": {
        "status": "COMPLETE",
        "finding": "이번 공정 수정 없음, 다음 Phase에서 승인 후 수행",
    },
    "condition_7_representative_approval_conditions_fixed": {
        "status": "COMPLETE",
        "finding": "dry-run flag / execute_task 연결 각각 별도 승인 조건 고정",
    },
    "all_conditions_met": True,
    "next_phase": "POST_TASKS_DRY_RUN_FLAG_IMPLEMENTATION",
}


def _check_router_state() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "execute_task_imported": "execute_task" in content and "import" in content,
        "execute_imported": "from ..tasks.executor import execute" in content,
        "task_approve_guard_active": (
            '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in content
            or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in content
        ),
        "task_approve_flag_false": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in content,
        "dry_run_flag_not_present": "POST_TASKS_DRY_RUN_ENABLED" not in content,
        "touch_phase_1r": (
            'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in content
            or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content
        ),
    }


def _check_executor_state() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/tasks/executor.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "execute_task_defined": "def execute_task(" in content,
        "allowed_actions_defined": "ALLOWED_ACTIONS" in content,
        "get_server_status_in_whitelist": '"get_server_status"' in content or "'get_server_status'" in content,
        "fetch_web_page_in_whitelist": '"fetch_web_page"' in content or "'fetch_web_page'" in content,
        "medium_whitelist_not_separate": "ALLOWED_ACTIONS_MEDIUM" not in content,
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


def _check_safety_flags() -> list[str]:
    """1. 운영 안전 플래그."""
    errors = []
    if APPROVAL_TOKEN_ISSUE_ALLOWED:
        errors.append("APPROVAL_TOKEN_ISSUE_ALLOWED must be False")
    if APPROVE_CALL_ALLOWED:
        errors.append("APPROVE_CALL_ALLOWED must be False")
    if EXECUTE_TASK_CALL_ALLOWED:
        errors.append("EXECUTE_TASK_CALL_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")
    if ROUTER_MODIFICATION_ALLOWED:
        errors.append("ROUTER_MODIFICATION_ALLOWED must be False")
    if not PREFLIGHT_ONLY:
        errors.append("PREFLIGHT_ONLY must be True")
    return errors


def _check_router_state_findings(rs: dict) -> tuple[list[str], list[str]]:
    """2. router.py 상태."""
    errors: list[str] = []
    warnings: list[str] = []
    if rs["execute_task_imported"]:
        errors.append("execute_task가 router.py에 import됨 — 연결 경로 열림 위험")
    if not rs["execute_imported"]:
        errors.append("execute가 router.py에 import되지 않음")
    if not rs["task_approve_guard_active"]:
        errors.append("TASK_APPROVE guard 없음 — Phase 1-R 안전장치 소실")
    if not rs["task_approve_flag_false"]:
        errors.append("TASK_APPROVE flag != False")
    if not rs["dry_run_flag_not_present"]:
        warnings.append("POST_TASKS_DRY_RUN_ENABLED 이미 존재 — 이번 공정 범위 초과 여부 확인")
    if not rs["touch_phase_1r"]:
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    return errors, warnings


def _check_executor_state_findings(es: dict) -> tuple[list[str], list[str]]:
    """3. executor.py 상태."""
    errors: list[str] = []
    warnings: list[str] = []
    if not es["execute_task_defined"]:
        errors.append("execute_task 함수 없음")
    if not es["allowed_actions_defined"]:
        errors.append("ALLOWED_ACTIONS 없음")
    if not es["get_server_status_in_whitelist"]:
        errors.append("get_server_status whitelist 누락")
    if not es["fetch_web_page_in_whitelist"]:
        errors.append("fetch_web_page whitelist 누락")
    if not es["medium_whitelist_not_separate"]:
        warnings.append("ALLOWED_ACTIONS_MEDIUM 이미 존재 — 설계 충돌 여부 확인")
    return errors, warnings


def _check_design_docs_consistency() -> list[str]:
    """4·5·6·8·9: 이 모듈의 설계 딕셔너리 자기 일관성 검사."""
    errors = []
    finding = APPROVE_EXECUTE_CONNECTION_ANALYSIS
    if finding["current_safety"] != "SAFE_BY_INCOMPLETENESS":
        errors.append("approve→execute 연결 안전 상태 분류 오류")

    medium = MEDIUM_PATH_CURRENT_STATE
    if medium["step_1"]["execute_task_called"]:
        errors.append("step_1에서 execute_task 호출됨 — 설계 오류")
    if medium["step_2"]["execute_task_called"]:
        errors.append("step_2에서 execute_task 호출됨 — 현재 미연결 전제 위반")

    smoke = MEDIUM_ISOLATION_SMOKE_DESIGN
    if smoke["status"] != "DESIGN_ONLY":
        errors.append("isolation smoke status must be DESIGN_ONLY")
    if len(smoke["test_cases"]) < 6:
        errors.append("isolation smoke test cases < 6")

    approval = REPRESENTATIVE_APPROVAL_CONDITIONS
    if approval["approval_received"]:
        errors.append("approval_received must be False (이번 공정에서 승인 없음)")
    if approval["current_approval_status"] != "BLOCKED_DESIGN_ONLY":
        errors.append("approval status must be BLOCKED_DESIGN_ONLY")

    if ROUTER_MODIFICATION_ASSESSMENT["current_phase_modification"]:
        errors.append("이번 공정에서 router.py 수정됨 — preflight 범위 초과")
    return errors


def _check_preflight_gate_conditions() -> list[str]:
    """7. preflight gate 조건."""
    errors = []
    gate = PREFLIGHT_GATE_STATUS
    if not gate["all_conditions_met"]:
        errors.append("preflight gate conditions not all met")
    conditions = [
        "condition_1_approve_execute_connection_analyzed",
        "condition_2_execute_task_whitelist_reviewed",
        "condition_3_dry_run_flag_scope_confirmed",
        "condition_4_medium_isolation_smoke_designed",
        "condition_5_token_isolation_conditions_designed",
        "condition_6_router_modification_scope_confirmed",
        "condition_7_representative_approval_conditions_fixed",
    ]
    for c in conditions:
        if gate.get(c, {}).get("status") != "COMPLETE":
            errors.append(f"preflight condition 미완료: {c}")
    return errors


def run_audit() -> dict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 이 함수 하나(C901=32)에 있던 10개 번호 섹션(원본
    # 주석 1.~10.)을 위 _check_*() 함수로 분리했다. 각 섹션이 errors/warnings 에만 추가하는
    # 독립 검사라 순서·조건·문자열을 그대로 유지한 채 나누는 것이 안전했다.
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_safety_flags())

    rs = _check_router_state()
    e, w = _check_router_state_findings(rs)
    errors.extend(e)
    warnings.extend(w)

    es = _check_executor_state()
    e, w = _check_executor_state_findings(es)
    errors.extend(e)
    warnings.extend(w)

    errors.extend(_check_design_docs_consistency())
    errors.extend(_check_preflight_gate_conditions())

    # 10. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    if errors:
        verdict = "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_FAIL"
    elif warnings:
        verdict = "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_READY_WITH_WARN"
    else:
        verdict = "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT_READY"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "key_finding": APPROVE_EXECUTE_CONNECTION_ANALYSIS["finding_id"],
        "current_safety": APPROVE_EXECUTE_CONNECTION_ANALYSIS["current_safety"],
        "execute_task_in_router": rs["execute_task_imported"],
        "approve_guard_active": rs["task_approve_guard_active"],
        "dry_run_flag_present": not rs["dry_run_flag_not_present"],
        "medium_whitelist_separate": not es["medium_whitelist_not_separate"],
        "isolation_smoke_cases": len(MEDIUM_ISOLATION_SMOKE_DESIGN["test_cases"]),
        "preflight_conditions_met": PREFLIGHT_GATE_STATUS["all_conditions_met"],
        "next_phase": PREFLIGHT_GATE_STATUS["next_phase"],
        "router_modified_this_phase": ROUTER_MODIFICATION_ASSESSMENT["current_phase_modification"],
        "preflight_only": PREFLIGHT_ONLY,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json

    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Medium Approve Gate Preflight: {result['verdict']} ===")
    print(f"  핵심 발견: {result['key_finding']}")
    print(f"  현재 안전 상태: {result['current_safety']}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
