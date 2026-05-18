"""
Backend Pre-Deploy Smoke Plan
Phase 1 백엔드 준공 상태를 서버에 반영하기 전 read-only 체크리스트 확정.
실제 서버 반영 / git pull / 컨테이너 재시작 / DB 변경 / nginx 변경 금지.
자체 scripts/ops 감사·smoke 기준만 사용.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PLAN_ID = "BACKEND_PRE_DEPLOY_SMOKE_PLAN"
PLAN_DATE = "2026-05-18"
TARGET_COMMIT = "0014f24"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
SERVER_APPLY_ALLOWED = False
GIT_PULL_ALLOWED = False
CONTAINER_RESTART_ALLOWED = False
DB_CHANGE_ALLOWED = False
NGINX_CHANGE_ALLOWED = False
EXTERNAL_CALL_ALLOWED = False
PLAN_ONLY = True

# ── 1. 서버 반영 전 로컬 체크리스트 ──────────────────────────────────────────
PRE_DEPLOY_LOCAL_CHECKLIST = [
    {
        "id": "L-1",
        "item": "local HEAD == 0014f24",
        "command": "git rev-parse HEAD",
        "expected": "0014f24",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
    {
        "id": "L-2",
        "item": "local HEAD == origin/master",
        "command": "git rev-parse HEAD && git rev-parse origin/master",
        "expected": "동일",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
    {
        "id": "L-3",
        "item": "git status clean",
        "command": "git status --short",
        "expected": "완전 공백",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
    {
        "id": "L-4",
        "item": "quality gate errors 0",
        "command": "python scripts/quality_gate.py --staged --enforce --allow-existing-code-change",
        "expected": "errors: 0",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
    {
        "id": "L-5",
        "item": "layer audit PASS",
        "command": "pytest -q tests/test_codebase_layer_audit.py",
        "expected": "10 passed",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
    {
        "id": "L-6",
        "item": "전체 회귀 696 PASS",
        "command": "pytest -q (all phase tests)",
        "expected": "696+ passed, 0 failed",
        "status": "VERIFY_BEFORE_DEPLOY",
    },
]

# ── 2. 서버 현재 HEAD 확인 계획 ──────────────────────────────────────────────
SERVER_HEAD_VERIFICATION_PLAN = {
    "target_server": "haehan-app (SSH alias)",
    "api_runtime_path": "/home/ubuntu/apps/haehan-ai-orchestrator",
    "compose_service": "ai-orchestrator-api",
    "check_command": "ssh haehan-app 'cd /home/ubuntu/apps/haehan-ai-orchestrator && git rev-parse HEAD'",
    "expected_before_pull": "이전 commit sha (0014f24 이전)",
    "expected_after_pull": "0014f24",
    "note": "서버 HEAD 확인은 read-only. 실제 pull은 deploy 단계에서만.",
    "divergence_action": (
        "서버 HEAD가 origin/master보다 앞서면 STOP — 강제 진행 금지. "
        "서버 HEAD가 뒤면 ff-only pull 조건 확인 후 진행."
    ),
}

# ── 3. ff-only pull 조건 ──────────────────────────────────────────────────────
FF_ONLY_PULL_CONDITIONS = {
    "command": "git pull --ff-only origin master",
    "allowed_when": [
        "서버 HEAD가 origin/master의 조상(ancestor)인 경우",
        "서버 working tree clean (git status --short 공백)",
        "서버 uncommitted 변경 없음",
    ],
    "blocked_when": [
        "서버 HEAD가 origin/master보다 앞서는 경우",
        "서버에 uncommitted 변경이 있는 경우",
        "merge commit이 필요한 경우 (ff-only로 거부됨)",
    ],
    "on_fail": "STOP — 원인 파악 후 대표 승인 필요. force push / reset --hard 금지.",
    "note": "ff-only pull 실패 시 절대 --force 옵션 사용 금지.",
}

# ── 4. restart 전 smoke 항목 ─────────────────────────────────────────────────
PRE_RESTART_SMOKE = [
    {
        "id": "PR-1",
        "item": "router.py TOUCH_PHASE == PHASE_1R 확인",
        "type": "static_check",
        "command": "grep LEGACY_5050_ROUTER_TOUCH_PHASE ai_orchestrator/router.py",
        "expected": "PHASE_1R",
    },
    {
        "id": "PR-2",
        "item": "guard 3개 모두 False 확인",
        "type": "static_check",
        "command": "grep 'WIRING_ENABLED' ai_orchestrator/router.py",
        "expected": "모두 = False",
    },
    {
        "id": "PR-3",
        "item": "GET /inbox 8400 handler 존재 확인",
        "type": "static_check",
        "command": "grep '@router.get.*inbox' ai_orchestrator/router.py",
        "expected": "@router.get('/inbox') 존재",
    },
    {
        "id": "PR-4",
        "item": "POST /tasks guard 존재 확인",
        "type": "static_check",
        "command": "grep 'TASK_APPROVE\\|TASK_REJECT' ai_orchestrator/router.py",
        "expected": "guard call 존재",
    },
    {
        "id": "PR-5",
        "item": "external site registry 정책 파일 존재",
        "type": "file_check",
        "command": "ls scripts/ops/audit_external_site_canonical_registry.py",
        "expected": "파일 존재",
    },
    {
        "id": "PR-6",
        "item": "Phase 1 audit 파일 전체 존재",
        "type": "file_check",
        "command": "ls scripts/ops/audit_5050_phase1*.py",
        "expected": "12개 이상 파일",
    },
    {
        "id": "PR-7",
        "item": "backend/compat/legacy_5050 존재 확인",
        "type": "file_check",
        "command": "ls backend/compat/legacy_5050/",
        "expected": "디렉터리 존재",
    },
    {
        "id": "PR-8",
        "item": "pytest known baseline PASS",
        "type": "test_run",
        "command": "pytest -q tests/test_codebase_layer_audit.py tests/test_5050_legacy_characterization_20260517.py",
        "expected": "all passed",
    },
]

# ── 5. restart 후 smoke 항목 ─────────────────────────────────────────────────
POST_RESTART_SMOKE = [
    {
        "id": "PS-1",
        "item": "서버 프로세스 정상 기동 확인",
        "type": "server_check",
        "command": "ssh haehan-app 'docker compose ps ai-orchestrator-api'",
        "expected": "Up / running",
        "note": "컨테이너 상태 확인. 재시작은 별도 승인 필요.",
    },
    {
        "id": "PS-2",
        "item": "서버 HEAD == 0014f24 확인",
        "type": "server_check",
        "command": "ssh haehan-app 'cd /home/ubuntu/apps/haehan-ai-orchestrator && git rev-parse HEAD'",
        "expected": "0014f24",
    },
    {
        "id": "PS-3",
        "item": "서버 git status clean 확인",
        "type": "server_check",
        "command": "ssh haehan-app 'cd /home/ubuntu/apps/haehan-ai-orchestrator && git status --short'",
        "expected": "완전 공백",
    },
    {
        "id": "PS-4",
        "item": "API health check",
        "type": "server_check",
        "command": "curl -s http://localhost:8400/health 또는 /api/v1/status",
        "expected": "200 OK",
        "note": "로컬 서버에서 curl. 외부 사이트 호출 아님.",
    },
    {
        "id": "PS-5",
        "item": "GET /inbox endpoint 응답 확인",
        "type": "server_check",
        "command": "curl -s -H 'Authorization: Bearer <token>' http://localhost:8400/api/v1/inbox",
        "expected": "200 OK + list 응답",
        "note": "인증 토큰 필요. 실제 외부 이메일 호출 없음.",
    },
    {
        "id": "PS-6",
        "item": "POST /inbox/email/fetch guard 동작 확인",
        "type": "server_check",
        "command": "curl -s -X POST http://localhost:8400/api/v1/inbox/email/fetch",
        "expected": "guard no-op → 기존 handler 응답 (RuntimeError 없음)",
        "note": "guard가 False이면 기존 handler 실행. 5050 wiring 실행 없음.",
    },
    {
        "id": "PS-7",
        "item": "edge nginx 경로 확인",
        "type": "server_check",
        "command": "curl -s http://localhost/orchestrator/api/v1/inbox",
        "expected": "200 OK (edge nginx → 8400 전달)",
        "note": "edge nginx 변경 없음. 기존 라우팅 그대로.",
    },
]

# ── 6. rollback 기준 ──────────────────────────────────────────────────────────
ROLLBACK_CRITERIA = {
    "trigger_conditions": [
        "서버 기동 실패 (docker compose ps = Exit / Error)",
        "API health check 200 아닌 경우",
        "GET /inbox 500 에러",
        "guard 함수 RuntimeError 실제 발생",
        "서버 HEAD != 0014f24 (pull 실패 또는 다른 commit)",
        "git status --short 비공백 (uncommitted 변경 있음)",
    ],
    "rollback_command": "git revert 0014f24 (또는 이전 stable commit으로 git reset --hard + force push 대표 승인 후)",
    "rollback_primary": "docker compose restart → 이전 이미지로 복구",
    "rollback_smoke": "restart 후 health check + GET /inbox smoke 재실행",
    "rollback_approval": "대표 승인 필요",
    "note": "git reset --hard는 대표 명시 승인 후에만. ff-only가 원칙.",
}

# ── 7. GET /inbox effective disabled 유지 확인 ────────────────────────────────
GET_INBOX_DEPLOY_CHECK = {
    "status": "EFFECTIVELY_DISABLED",
    "8400_handler": "ACTIVE_NORMAL — 유지 필수",
    "legacy_mount": "NOT_MOUNTED — 유지 필수",
    "check_before_deploy": "router.py @router.get('/inbox') 존재 확인",
    "check_after_deploy": "GET /inbox 8400 응답 확인",
    "regression_risk": "NONE",
}

# ── 8. POST /tasks BLOCKED_DESIGN_ONLY 유지 확인 ─────────────────────────────
POST_TASKS_DEPLOY_CHECK = {
    "status": "BLOCKED_DESIGN_ONLY",
    "deploy_impact": "NONE — 서버 반영해도 코드 변경 없음",
    "check_before_deploy": "router.py TASK guard False 확인",
    "check_after_deploy": "POST /tasks 기존 동작 유지 확인 (guard no-op)",
    "blockers_count": 5,
    "disable_allowed_now": False,
}

# ── 9. external site registry 정책 확인 ─────────────────────────────────────
EXTERNAL_SITE_DEPLOY_CHECK = {
    "registry_file": "scripts/ops/audit_external_site_canonical_registry.py",
    "policy_files": [
        "scripts/ops/audit_external_site_canonical_registry.py",
    ],
    "deploy_impact": "NONE — 정책 파일만, 서버 동작 변경 없음",
    "check": "파일 존재 + audit verdict PASS",
}

# ── 10. quality gate / layer audit / known baseline ──────────────────────────
GATE_CHECKS = {
    "quality_gate": {
        "command": "python scripts/quality_gate.py --staged --enforce --allow-existing-code-change",
        "expected": "errors: 0, warnings: 0",
        "when": "deploy 전",
    },
    "layer_audit": {
        "command": "pytest -q tests/test_codebase_layer_audit.py",
        "expected": "10 passed",
        "when": "deploy 전",
    },
    "known_baselines": {
        "tests": [
            "tests/test_5050_legacy_characterization_20260517.py",
            "tests/test_5050_phase1_8400_contract_freeze_20260517.py",
            "tests/test_5050_phase1r_actual_router_touch_feature_flag_off_20260517.py",
            "tests/test_5050_phase1s_disabled_router_guard_behavior_20260517.py",
            "tests/test_external_site_canonical_registry_20260517.py",
            "tests/test_codebase_layer_audit.py",
        ],
        "expected": "모두 PASS",
        "when": "deploy 전 + deploy 후",
    },
}


def _check_local_readiness() -> dict:
    """로컬 기준 deploy readiness 정적 확인."""
    router = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    results = {
        "touch_phase_1r": (
            'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router
            or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router
        ),
        "all_guards_false": not any([
            "LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = True" in router,
            "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = True" in router,
            "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = True" in router,
        ]),
        "has_8400_inbox_handler": (
            '@router.get("/inbox")' in router or "@router.get('/inbox')" in router
        ),
        "guard_function_exists": "_legacy_5050_should_use_route_wiring" in router,
        "no_unauthorized_modification": "BACKEND_PRE_DEPLOY" not in router,
        "legacy_5050_exists": (REPO_ROOT / "backend/compat/legacy_5050").exists(),
        "phase1t_audit_exists": (
            REPO_ROOT / "scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py"
        ).exists(),
        "stabilization_audit_exists": (
            REPO_ROOT / "scripts/ops/audit_backend_operation_stabilization_final.py"
        ).exists(),
    }
    results["all_ready"] = all(results.values())
    return results


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

    # 1. 로컬 readiness 확인
    local = _check_local_readiness()
    if not local["touch_phase_1r"]:
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    if not local["all_guards_false"]:
        errors.append("guard 중 enabled=True 항목 존재")
    if not local["has_8400_inbox_handler"]:
        errors.append("8400 GET /inbox handler 없음")
    if not local["guard_function_exists"]:
        errors.append("guard 함수 없음")
    if not local["legacy_5050_exists"]:
        errors.append("backend/compat/legacy_5050 없음")
    if not local["phase1t_audit_exists"]:
        errors.append("Phase 1-T audit 파일 없음")
    if not local["stabilization_audit_exists"]:
        errors.append("stabilization final audit 파일 없음")

    # 2. 운영 안전 플래그
    if SERVER_APPLY_ALLOWED:
        errors.append("SERVER_APPLY_ALLOWED must be False")
    if GIT_PULL_ALLOWED:
        errors.append("GIT_PULL_ALLOWED must be False")
    if CONTAINER_RESTART_ALLOWED:
        errors.append("CONTAINER_RESTART_ALLOWED must be False")
    if DB_CHANGE_ALLOWED:
        errors.append("DB_CHANGE_ALLOWED must be False")
    if NGINX_CHANGE_ALLOWED:
        errors.append("NGINX_CHANGE_ALLOWED must be False")
    if EXTERNAL_CALL_ALLOWED:
        errors.append("EXTERNAL_CALL_ALLOWED must be False")
    if not PLAN_ONLY:
        errors.append("PLAN_ONLY must be True")

    # 3. 체크리스트 항목 수
    if len(PRE_DEPLOY_LOCAL_CHECKLIST) < 6:
        errors.append("PRE_DEPLOY_LOCAL_CHECKLIST 항목 부족")
    if len(PRE_RESTART_SMOKE) < 8:
        errors.append("PRE_RESTART_SMOKE 항목 부족")
    if len(POST_RESTART_SMOKE) < 7:
        errors.append("POST_RESTART_SMOKE 항목 부족")

    # 4. rollback 기준
    if not ROLLBACK_CRITERIA.get("trigger_conditions"):
        errors.append("rollback trigger_conditions 없음")
    if not ROLLBACK_CRITERIA.get("rollback_command"):
        errors.append("rollback_command 없음")
    if not ROLLBACK_CRITERIA.get("rollback_approval"):
        errors.append("rollback_approval 없음")

    # 5. GET /inbox deploy check
    if GET_INBOX_DEPLOY_CHECK["status"] != "EFFECTIVELY_DISABLED":
        errors.append("GET /inbox status must be EFFECTIVELY_DISABLED")
    if GET_INBOX_DEPLOY_CHECK["regression_risk"] != "NONE":
        errors.append("GET /inbox regression_risk must be NONE")

    # 6. POST /tasks deploy check
    if POST_TASKS_DEPLOY_CHECK["disable_allowed_now"]:
        errors.append("POST /tasks disable_allowed_now must be False")
    if POST_TASKS_DEPLOY_CHECK["blockers_count"] < 5:
        errors.append("POST /tasks blockers_count < 5")

    # 7. HTTP import 없음
    ok, msg = _verify_no_http_import()
    if not ok:
        errors.append(msg)

    # 8. ff-only pull 조건
    if not FF_ONLY_PULL_CONDITIONS.get("allowed_when"):
        errors.append("ff-only pull conditions 없음")
    if "--force" in FF_ONLY_PULL_CONDITIONS.get("on_fail", ""):
        errors.append("ff-only fail에 force 옵션 포함 — 금지")

    # verdict
    if errors:
        verdict = "BACKEND_PRE_DEPLOY_SMOKE_PLAN_FAIL"
    elif warnings:
        verdict = "BACKEND_PRE_DEPLOY_SMOKE_PLAN_READY_WITH_WARN"
    else:
        verdict = "BACKEND_PRE_DEPLOY_SMOKE_PLAN_READY"

    return {
        "plan_id": PLAN_ID,
        "plan_date": PLAN_DATE,
        "target_commit": TARGET_COMMIT,
        "verdict": verdict,
        "local_readiness": local,
        "pre_deploy_checklist_count": len(PRE_DEPLOY_LOCAL_CHECKLIST),
        "pre_restart_smoke_count": len(PRE_RESTART_SMOKE),
        "post_restart_smoke_count": len(POST_RESTART_SMOKE),
        "rollback_defined": bool(ROLLBACK_CRITERIA.get("trigger_conditions")),
        "get_inbox_status": GET_INBOX_DEPLOY_CHECK["status"],
        "post_tasks_status": POST_TASKS_DEPLOY_CHECK["status"],
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "git_pull_allowed": GIT_PULL_ALLOWED,
        "container_restart_allowed": CONTAINER_RESTART_ALLOWED,
        "plan_only": PLAN_ONLY,
        "errors": errors,
        "warnings": warnings,
        "deploy_sequence": [
            "STEP 1: 로컬 기준 사전 체크 (L-1~L-6)",
            "STEP 2: 서버 HEAD 확인 (read-only ssh)",
            "STEP 3: ff-only pull 조건 확인",
            "STEP 4 (별도 승인): git pull --ff-only + 컨테이너 재시작",
            "STEP 5 (별도 승인): restart 후 smoke (PS-1~PS-7)",
            "STEP 6: rollback 기준 재확인",
        ],
        "rollback_instructions": [
            "서버 기동 실패 시: docker compose restart → 이전 이미지 복구",
            "git rollback 필요 시: 대표 명시 승인 후 git revert 또는 reset --hard",
        ],
        "next_step": "대표 승인 후 STEP 4 진행 (git pull --ff-only + 컨테이너 재시작)",
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Backend Pre-Deploy Smoke Plan: {result['verdict']} ===")
    print(f"  target_commit: {result['target_commit']}")
    print(f"  local_readiness.all_ready: {result['local_readiness']['all_ready']}")
    print(f"  pre_deploy_checklist: {result['pre_deploy_checklist_count']}개")
    print(f"  pre_restart_smoke: {result['pre_restart_smoke_count']}개")
    print(f"  post_restart_smoke: {result['post_restart_smoke_count']}개")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
