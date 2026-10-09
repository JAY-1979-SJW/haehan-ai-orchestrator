"""
Backend Operation Final Closeout Audit
ASSISTANT_BACKEND_OPERATION_FINAL_CLOSEOUT_01

백엔드 Phase 1 준공 보고서.
실제 코드 기능 추가 / docker-compose 수정 / 서버 반영 / 컨테이너 재시작 전면 금지.
현재 운영 기준선을 machine-readable로 확정하는 감사 공정.
"""

from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

AUDIT_ID = "BACKEND_OPERATION_FINAL_CLOSEOUT"
AUDIT_DATE = "2026-05-18"
PHASE = "PHASE_1_CLOSEOUT"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
ROUTER_MODIFY_ALLOWED = False
DOCKER_COMPOSE_MODIFY_ALLOWED = False
SERVER_APPLY_ALLOWED = False
CONTAINER_RESTART_ALLOWED = False
DB_WRITE_ALLOWED = False
EXTERNAL_HTTP_ALLOWED = False
CLOSEOUT_ONLY = True

# ── Phase 1 완료 공정 이력 ────────────────────────────────────────────────────
COMPLETED_PHASES = [
    {"phase": "SERVER_DEPLOY_AND_POST_RESTART_SMOKE", "commit": "4ae9d18", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_SIDE_EFFECT_GATE_DESIGN", "commit": "4cdab7a", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_MEDIUM_APPROVE_GATE_PREFLIGHT", "commit": "319aee7", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_DRY_RUN_FLAG_IMPLEMENTATION", "commit": "fe17642", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_MEDIUM_ISOLATION_SMOKE", "commit": "b031994", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_SERVER_SYNC_AND_POST_SMOKE", "commit": "b031994", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "IMAGE_REBUILD_AND_RUNTIME_SMOKE_RECOVERY", "commit": "b031994", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "POST_TASKS_RUNTIME_DRY_RUN_GATE_PASS", "commit": "b031994", "date": "2026-05-18", "verdict": "PASS"},
    {
        "phase": "RUNTIME_STORAGE_PERSISTENCE_AUDIT",
        "commit": "e175444",
        "date": "2026-05-18",
        "verdict": "PASS_WITH_WARN",
    },
    {"phase": "RUNTIME_STORAGE_BIND_MOUNT_DESIGN", "commit": "6bc3fdc", "date": "2026-05-18", "verdict": "PASS"},
    {"phase": "RUNTIME_STORAGE_BIND_MOUNT_APPLY", "commit": "8e72025", "date": "2026-05-18", "verdict": "PASS"},
]

# ── 1. 서버/배포 기준선 ──────────────────────────────────────────────────────
DEPLOYMENT_BASELINE: dict[str, Any] = {
    "server_head": "8e72025",
    "local_head": "8e72025",
    "origin_master": "8e72025",
    "all_synced": True,
    "api_container": "haehan-ai-orchestrator-api:local",
    "api_port": "127.0.0.1:8400",
    "health_endpoint": "GET /api/v1/health → {status: ok}",
    "edge_proxy": "nginx container → /orchestrator/api/v1/",
    "deploy_sop": {
        "steps": [
            "git pull --ff-only",
            "docker compose build ai-orchestrator-api",
            "docker compose up -d ai-orchestrator-api",
            "컨테이너 내부 import 확인 (python -c from ai_orchestrator.routers.registry import X)",
            "GET /api/v1/health",
            "smoke 1회",
        ],
        "warning": "docker compose restart 단독 사용 금지 — baked-in 이미지라 코드 미반영",
        "confirmed_by_incident": "2026-05-18 DRY_RUN 플래그 미반영 실장애",
    },
}

# ── 2. POST /api/v1/tasks dry-run gate 상태 ──────────────────────────────────
POST_TASKS_GATE_STATUS: dict[str, Any] = {
    "flag": "POST_TASKS_DRY_RUN_ENABLED",
    "value": True,
    "location": "ai_orchestrator/routers/registry.py:39",
    "effect": "medium risk + requires_approval=True + allowed=True → token 발행 차단, DRY_RUN 반환",
    "runtime_verified": True,
    "runtime_smoke_date": "2026-05-18",
    "smoke_result": {
        "approval_token_id": None,
        "status": "DRY_RUN: would issue token — gate active",
        "dry_run": True,
    },
    "low_path_unaffected": True,
    "blocked_path_unaffected": True,
    "approve_execute_not_connected": True,
    "remaining_blocker": "approval gate 설계 미완 — approve → execute 연결 없음 (SAFE_BY_INCOMPLETENESS)",
}

# ── 3. Legacy 5050 → 8400 integration 상태 ──────────────────────────────────
LEGACY_5050_STATUS = {
    "touch_phase": "PHASE_1R",
    "router_enabled": False,
    "inbox_email_fetch_wiring": False,
    "task_approve_wiring": False,
    "task_reject_wiring": False,
    "guards_active": True,
    "guard_behavior": "wiring_enabled=False 시 RuntimeError 발생 (실수 활성화 방지)",
    "inbox_get_route": "등록됨 — 실제 DB/storage 읽기는 가능, email fetch는 guard로 차단",
    "status": "PHASE_1R_GUARD_ACTIVE_WIRING_DISABLED",
}

# ── 4. Runtime Storage 영속성 ────────────────────────────────────────────────
STORAGE_PERSISTENCE_STATUS: dict[str, Any] = {
    "storage_named_volume": {
        "path": "/app/ai_orchestrator/storage",
        "volume": "haehan-ai-orchestrator-api-storage",
        "persisted": True,
        "contains": [
            "audit_logs.jsonl",
            "approval_tokens.jsonl",
            "task_states.jsonl",
            "app.log",
            "execution_history.jsonl (생성 시)",
        ],
    },
    "app_logs_bind_mount": {
        "path": "/app/logs",
        "host": "./data/app-logs",
        "persisted": True,
        "applied_date": "2026-05-18",
        "applied_commit": "8e72025",
    },
    "secrets_bind": {
        "path": "/run/secrets/api",
        "mode": "read-only",
        "persisted": True,
    },
    "LOG_DIR_env": "/app/ai_orchestrator/storage",
    "all_critical_paths_persisted": True,
}

# ── 5. External Site Registry ────────────────────────────────────────────────
EXTERNAL_SITE_REGISTRY_STATUS = {
    "canonical_registry_committed": True,
    "safety_policies_committed": True,
    "gabia_site_settings_committed": True,
    "cookie_storage_blocked": True,
    "plaintext_cookie_forbidden": True,
    "sessions_path_protected": True,
    "registry_module": "ai_orchestrator/external_sites/",
    "audit_script": "scripts/ops/audit_external_site_canonical_registry.py",
    "test_file": "tests/app_contracts/test_external_site_canonical_registry_20260517.py",
    "verdict": "PASS",
}

# ── 6. Known Baseline Failures / Warnings ───────────────────────────────────
KNOWN_BASELINE_ISSUES: dict[str, Any] = {
    "known_failures": [
        {
            "id": "KF-1",
            "description": "chrome_ui_monitor_state.json — M(modified) 상태로 git status에 표시",
            "file": "scripts/archive/data/chrome_ui_monitor_state.json",
            "classification": "RUNTIME_CACHE_DISPOSABLE",
            "action": "gitignore 추가 또는 archive 유지",
            "risk": "LOW",
        },
    ],
    "known_warnings": [
        {
            "id": "KW-1",
            "description": "layer audit ROOT_PY_SCRIPT WARN — 루트 레벨 Python 파일 다수",
            "count_approx": 52,
            "classification": "LEGACY_ROOT_SCRIPTS",
            "action": "별도 모듈화 공정에서 처리",
            "risk": "LOW",
        },
        {
            "id": "KW-2",
            "description": "/app/logs/audit.jsonl — legacy 경로, 쓰기 비활성 추정",
            "classification": "LEGACY_AUDIT_PATH",
            "action": "모니터링 유지",
            "risk": "LOW",
        },
        {
            "id": "KW-3",
            "description": "approval_tokens.json (legacy json) — storage에 존재, 내용 확인 미완",
            "classification": "FLAGGED_FOR_REVIEW",
            "action": "TOKEN_CONTENT_AUDIT 공정에서 확인",
            "risk": "MEDIUM",
        },
        {
            "id": "KW-4",
            "description": "docker-compose.yml version 속성 obsolete 경고",
            "classification": "DOCKER_COMPOSE_COSMETIC",
            "action": "version 줄 삭제 (무해)",
            "risk": "LOW",
        },
    ],
}

# ── 7. POST /tasks 남은 blockers ─────────────────────────────────────────────
POST_TASKS_REMAINING_BLOCKERS: dict[str, Any] = {
    "status": "MEDIUM_PATH_DRY_RUN_ACTIVE",
    "blockers": [
        {
            "id": "B-1",
            "description": "approve_task → execute_task 미연결 (SAFE_BY_INCOMPLETENESS)",
            "required_before_enable": "approve gate 설계 + execute 연결 + execute_task whitelist 확장 + 대표 승인",
        },
        {
            "id": "B-2",
            "description": "POST_TASKS_DRY_RUN_ENABLED=True — False 전환 미승인",
            "required_before_disable": "approval gate 완성 + runtime smoke + 대표 명시 승인 'DRY_RUN 해제 승인'",
        },
        {
            "id": "B-3",
            "description": "approval token content audit 미완 (approval_tokens.json 내용 확인 필요)",
            "required_before_enable": "TOKEN_CONTENT_AUDIT 공정 완료",
        },
    ],
    "enable_condition": "blockers B-1 ~ B-3 모두 해소 + 대표 명시 승인",
}

# ── 8. 앱 착공 가능 조건 ─────────────────────────────────────────────────────
APP_FOUNDATION_CONDITIONS: dict[str, Any] = {
    "phase": "APP_FOUNDATION_MVP_PREP_01",
    "backend_ready": True,
    "conditions_met": [
        "서버 API 건강 (GET /health 정상)",
        "POST /tasks dry-run gate 운영 반영 완료",
        "runtime storage 영속성 확보",
        "external site registry 완료",
        "배포 SOP 확정 (build → up -d)",
        "Phase 1-R guard 활성 (LEGACY wiring disabled)",
    ],
    "conditions_pending": [
        "approve → execute 연결 (DRY_RUN 해제 전 필요)",
        "approval token content audit",
        "POST /tasks medium path 실제 실행 (현재 dry-run)",
    ],
    "app_can_start": True,
    "note": "앱 착공은 현재 backend baseline에서 가능. POST /tasks medium 실제 실행은 DRY_RUN 해제 후 가능.",
}


def _verify_router_state() -> dict:
    content = (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")
    return {
        "dry_run_flag_true": "POST_TASKS_DRY_RUN_ENABLED = True" in content,
        "phase_1r": (
            'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in content
            or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in content
        ),
        "task_approve_wiring_false": "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in content,
        "task_reject_wiring_false": "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in content,
        "approve_guard_active": (
            '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in content
            or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in content
        ),
        "execute_task_not_imported": all(
            "execute_task" not in line
            for line in content.splitlines()
            if line.strip().startswith(("import", "from")) and "execute_task" in line
        ),
        "dry_run_branch": "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval" in content,
        "dry_run_log_event": "DRY_RUN_GATE_BLOCKED" in content,
    }


def _verify_docker_compose() -> dict:
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8", errors="ignore")
    return {
        "storage_named_volume": "api_storage:/app/ai_orchestrator/storage" in content,
        "app_logs_bind_mount": "data/app-logs:/app/logs" in content,
        "secrets_bind_ro": "./secrets/api:/run/secrets/api:ro" in content,
        "log_dir_env": "LOG_DIR: /app/ai_orchestrator/storage" in content,
    }


def _verify_external_site_registry() -> dict:
    # 실제 registry는 ai_orchestrator/external_sites/ 패키지에 위치
    registry_path = REPO_ROOT / "ai_orchestrator/external_sites"
    audit_script = REPO_ROOT / "tools/audits/app/audit_external_site_canonical_registry.py"
    test_file = REPO_ROOT / "tests/app_contracts/test_external_site_canonical_registry_20260517.py"
    return {
        "registry_dir_exists": registry_path.exists(),
        "audit_script_exists": audit_script.exists(),
        "test_file_exists": test_file.exists(),
    }


def _check_safety_flags_and_closeout() -> list[str]:
    """0. 운영 안전 플래그."""
    errors = []
    for flag, name in [
        (ROUTER_MODIFY_ALLOWED, "ROUTER_MODIFY_ALLOWED"),
        (DOCKER_COMPOSE_MODIFY_ALLOWED, "DOCKER_COMPOSE_MODIFY_ALLOWED"),
        (SERVER_APPLY_ALLOWED, "SERVER_APPLY_ALLOWED"),
        (CONTAINER_RESTART_ALLOWED, "CONTAINER_RESTART_ALLOWED"),
        (DB_WRITE_ALLOWED, "DB_WRITE_ALLOWED"),
        (EXTERNAL_HTTP_ALLOWED, "EXTERNAL_HTTP_ALLOWED"),
    ]:
        if flag:
            errors.append(f"{name} must be False")
    if not CLOSEOUT_ONLY:
        errors.append("CLOSEOUT_ONLY must be True")
    return errors


def _check_router_state_findings(rs: dict) -> list[str]:
    """1. router 상태."""
    errors = []
    if not rs["dry_run_flag_true"]:
        errors.append("POST_TASKS_DRY_RUN_ENABLED != True")
    if not rs["phase_1r"]:
        errors.append("ROUTER_TOUCH_PHASE != PHASE_1R")
    if not rs["task_approve_wiring_false"]:
        errors.append("TASK_APPROVE_WIRING != False")
    if not rs["task_reject_wiring_false"]:
        errors.append("TASK_REJECT_WIRING != False")
    if not rs["approve_guard_active"]:
        errors.append("TASK_APPROVE guard 없음")
    if not rs["execute_task_not_imported"]:
        errors.append("execute_task가 router.py에 import됨 — 미승인 연결")
    if not rs["dry_run_branch"]:
        errors.append("dry-run 분기 없음")
    if not rs["dry_run_log_event"]:
        errors.append("DRY_RUN_GATE_BLOCKED 이벤트 없음")
    return errors


def _check_docker_compose_findings(dc: dict) -> list[str]:
    """2. docker-compose 스토리지 상태."""
    errors = []
    if not dc["storage_named_volume"]:
        errors.append("storage named volume 없음")
    if not dc["app_logs_bind_mount"]:
        errors.append("/app/logs bind mount 없음")
    if not dc["secrets_bind_ro"]:
        errors.append("secrets bind mount 없음")
    if not dc["log_dir_env"]:
        errors.append("LOG_DIR 환경변수 없음")
    return errors


def _check_external_site_registry_findings(ex: dict) -> tuple[list[str], list[str]]:
    """3. external site registry."""
    errors: list[str] = []
    warnings: list[str] = []
    if not ex["registry_dir_exists"]:
        warnings.append("external site registry 디렉터리 없음 — 경로 확인 필요")
    if not ex["audit_script_exists"]:
        errors.append("external site registry audit 스크립트 없음")
    if not ex["test_file_exists"]:
        errors.append("external site registry 테스트 없음")
    return errors, warnings


def _check_completed_phases() -> list[str]:
    """4. 완료 공정 수."""
    if len(COMPLETED_PHASES) < 10:
        return ["완료 공정 기록 부족"]
    return []


def _check_post_tasks_gate() -> list[str]:
    """5. POST tasks gate 상태."""
    errors = []
    gate = POST_TASKS_GATE_STATUS
    if not gate["runtime_verified"]:
        errors.append("runtime smoke 미검증")
    if gate["smoke_result"]["approval_token_id"] is not None:
        errors.append("smoke 결과 approval_token_id != null")
    if not gate["approve_execute_not_connected"]:
        errors.append("approve → execute 연결됨 — blocker 해소 전 허용 불가")
    return errors


def _check_known_baseline_warnings() -> list[str]:
    """6. known baseline warnings 확인."""
    return [
        f"KNOWN_WARN [{w['id']}]: {w['description']}"
        for w in KNOWN_BASELINE_ISSUES["known_warnings"]
        if w["risk"] == "MEDIUM"
    ]


def _check_deployment_sop() -> list[str]:
    """7. 배포 SOP 확정."""
    sop = DEPLOYMENT_BASELINE["deploy_sop"]
    if len(sop["steps"]) < 5:
        return ["배포 SOP 단계 부족"]
    return []


def _check_app_foundation() -> list[str]:
    """8. 앱 착공 조건."""
    errors = []
    app = APP_FOUNDATION_CONDITIONS
    if not app["app_can_start"]:
        errors.append("앱 착공 불가 — 조건 미충족")
    if len(app["conditions_met"]) < 5:
        errors.append("앱 착공 완료 조건 부족")
    return errors


def run_audit() -> dict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 이 함수 하나(C901=30)에 있던 원본 주석의 0.~8. 번호
    # 섹션을 위 _check_*() 함수로 분리(순서·조건·문자열 그대로, 순수 추출) — #48/#49/#50 과
    # 같은 계열의 독립 체크리스트 패턴.
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_safety_flags_and_closeout())

    rs = _verify_router_state()
    errors.extend(_check_router_state_findings(rs))

    dc = _verify_docker_compose()
    errors.extend(_check_docker_compose_findings(dc))

    ex = _verify_external_site_registry()
    e, w = _check_external_site_registry_findings(ex)
    errors.extend(e)
    warnings.extend(w)

    errors.extend(_check_completed_phases())
    errors.extend(_check_post_tasks_gate())
    warnings.extend(_check_known_baseline_warnings())
    errors.extend(_check_deployment_sop())
    errors.extend(_check_app_foundation())

    if errors:
        verdict = "BACKEND_PHASE1_CLOSEOUT_FAIL"
    elif warnings:
        verdict = "BACKEND_PHASE1_CLOSEOUT_READY_WITH_WARN"
    else:
        verdict = "BACKEND_PHASE1_CLOSEOUT_READY"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "phase": PHASE,
        "verdict": verdict,
        "closeout_only": CLOSEOUT_ONLY,
        "completed_phases_count": len(COMPLETED_PHASES),
        "all_phases_pass": all(p["verdict"].startswith("PASS") for p in COMPLETED_PHASES),
        "router_state": rs,
        "docker_compose_storage": dc,
        "external_site_registry": ex,
        "dry_run_gate_active": rs["dry_run_flag_true"],
        "dry_run_gate_runtime_verified": POST_TASKS_GATE_STATUS["runtime_verified"],
        "storage_all_persisted": STORAGE_PERSISTENCE_STATUS["all_critical_paths_persisted"],
        "post_tasks_blockers_count": len(POST_TASKS_REMAINING_BLOCKERS["blockers"]),
        "app_can_start": APP_FOUNDATION_CONDITIONS["app_can_start"],
        "known_failures_count": len(KNOWN_BASELINE_ISSUES["known_failures"]),
        "known_warnings_count": len(KNOWN_BASELINE_ISSUES["known_warnings"]),
        "deploy_sop_confirmed": True,
        "next_phase": APP_FOUNDATION_CONDITIONS["phase"],
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json

    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Backend Phase 1 Final Closeout: {result['verdict']} ===")
    print(f"  완료 공정: {result['completed_phases_count']}개")
    print(f"  dry-run gate 운영 확인: {result['dry_run_gate_runtime_verified']}")
    print(f"  storage 영속성: {result['storage_all_persisted']}")
    print(f"  POST /tasks 남은 blockers: {result['post_tasks_blockers_count']}개")
    print(f"  앱 착공 가능: {result['app_can_start']}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
