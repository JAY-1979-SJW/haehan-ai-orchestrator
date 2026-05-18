"""
Phase 1-J4: Caller Migration Dry-Run Audit
smoke runner 결과와 safety boundary를 검증한다.
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J4"
AUDIT_ID = "PHASE1J4_CALLER_MIGRATION_DRY_RUN"

CALLER_MODIFICATION_ALLOWED_NOW = False
LEGACY_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False

# ── migration dry-run matrix ──────────────────────────────────────────────────
DRY_RUN_MATRIX = [
    {
        "phase": PHASE,
        "method": "GET",
        "path": "/api/v1/inbox",
        "side_effect_classification": "READ_ONLY_EXPECTED",
        "schema_freeze_status": "FROZEN",
        "disable_allowed_now": False,
        "caller_modification_allowed_now": False,
        "migration_dry_run_allowed": True,
        "migration_execution_allowed": False,
        "schema_compatible": True,
        "frontend_fixture_compatible": True,
        "backend_fixture_compatible": True,
        "frontend_is_real_http_caller": False,
        "frontend_migration_impact": "NONE",
        "next_action": "CALLER_MIGRATION_IMPLEMENTATION_PLAN_OR_FRONTEND_SMOKE",
        "risk_level": "LOW",
        "verdict": "DRY_RUN_READY",
    },
    {
        "phase": PHASE,
        "method": "POST",
        "path": "/api/v1/tasks",
        "side_effect_classification": "WRITE_POSSIBLE",
        "schema_freeze_status": "FROZEN",
        "disable_allowed_now": False,
        "caller_modification_allowed_now": False,
        "migration_dry_run_allowed": False,
        "migration_execution_allowed": False,
        "blocked_design_only": True,
        "blockers": [
            "WRITE_POSSIBLE",
            "execute_side_effect",
            "approval_token_side_effect",
            "db_write_impact",
            "approval_gate_not_designed",
        ],
        "next_action": "POST_TASKS_SIDE_EFFECT_GATE_DESIGN",
        "risk_level": "MEDIUM",
        "verdict": "BLOCKED_DESIGN_ONLY",
    },
]


def _load_smoke_result():
    smoke_path = REPO_ROOT / "scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py"
    spec = importlib.util.spec_from_file_location("_smoke_phase1j4", smoke_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_phase1j4_caller_migration_dry_run(), mod


def run_audit():
    errors = []
    warnings = []

    # 1. smoke runner 파일 존재 확인
    smoke_path = REPO_ROOT / "scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py"
    if not smoke_path.exists():
        errors.append("smoke runner 파일 없음: smoke_5050_phase1j4_caller_migration_dry_run.py")
        return {
            "phase": PHASE, "audit_id": AUDIT_ID,
            "verdict": "PHASE1J4_CALLER_MIGRATION_DRY_RUN_FAIL",
            "errors": errors, "warnings": warnings,
        }

    smoke_result, smoke_mod = _load_smoke_result()

    # 2. smoke 함수 존재
    if not hasattr(smoke_mod, "run_phase1j4_caller_migration_dry_run"):
        errors.append("run_phase1j4_caller_migration_dry_run 함수 없음")
    if not hasattr(smoke_mod, "build_phase1j4_caller_migration_fixtures"):
        errors.append("build_phase1j4_caller_migration_fixtures 함수 없음")

    # 3. smoke verdict
    if smoke_result.get("verdict") not in (
        "PHASE1J4_CALLER_MIGRATION_DRY_RUN_SMOKE_READY",
        "PHASE1J4_CALLER_MIGRATION_DRY_RUN_SMOKE_WITH_WARN",
    ):
        errors.append(f"smoke verdict not READY: {smoke_result.get('verdict')}")

    # 4. failed_scenarios
    if smoke_result.get("failed_scenarios", 1) != 0:
        errors.append(f"smoke failed_scenarios != 0: {smoke_result.get('failed_scenarios')}")

    # 5. total_scenarios
    if smoke_result.get("total_scenarios", 0) < 18:
        errors.append(f"total_scenarios < 18: {smoke_result.get('total_scenarios')}")

    # 6. target / mode
    if smoke_result.get("target_priority") != "GET_INBOX_FIRST":
        errors.append("target_priority != GET_INBOX_FIRST")
    if smoke_result.get("post_tasks_mode") != "BLOCKED_DESIGN_ONLY":
        errors.append("post_tasks_mode != BLOCKED_DESIGN_ONLY")

    # 7. fixture compatibility
    if not smoke_result.get("frontend_fixture_compatible"):
        errors.append("frontend_fixture_compatible must be True")
    if not smoke_result.get("backend_fixture_compatible"):
        errors.append("backend_fixture_compatible must be True")
    if not smoke_result.get("schema_compatible"):
        errors.append("schema_compatible must be True")

    # 8. safety checks
    if not smoke_result.get("post_tasks_blocked"):
        errors.append("post_tasks_blocked must be True")
    if not smoke_result.get("unknown_callers_not_mounted"):
        errors.append("unknown_callers_not_mounted must be True")
    if smoke_result.get("caller_files_modified"):
        errors.append("caller_files_modified must be False")
    if smoke_result.get("route_disable_performed"):
        errors.append("route_disable_performed must be False")
    if smoke_result.get("live_http_call_count", 1) != 0:
        errors.append(f"live_http_call_count must be 0: {smoke_result.get('live_http_call_count')}")
    if smoke_result.get("db_write_count", 1) != 0:
        errors.append(f"db_write_count must be 0: {smoke_result.get('db_write_count')}")
    if smoke_result.get("secret_env_access_count", 1) != 0:
        errors.append(f"secret_env_access_count must be 0: {smoke_result.get('secret_env_access_count')}")

    # 9. frontend fixture 존재 확인
    fixtures = smoke_result.get("fixtures", {})
    if not fixtures.get("frontend_fixture"):
        errors.append("frontend_fixture missing")
    if not fixtures.get("backend_callers_fixture"):
        errors.append("backend_callers_fixture missing")

    # 10. POST /tasks blockers 4개 유지
    tasks_row = next((r for r in DRY_RUN_MATRIX if r["path"] == "/api/v1/tasks"), None)
    if tasks_row:
        if len(tasks_row.get("blockers", [])) < 4:
            errors.append(f"POST /tasks blockers < 4: {tasks_row.get('blockers')}")
        if not tasks_row.get("blocked_design_only"):
            errors.append("POST /tasks blocked_design_only must be True")

    # 11. matrix 검증
    for row in DRY_RUN_MATRIX:
        if row["disable_allowed_now"]:
            errors.append(f"disable_allowed_now must be False: {row['path']}")
        if row["caller_modification_allowed_now"]:
            errors.append(f"caller_modification_allowed_now must be False: {row['path']}")
        if row["schema_freeze_status"] != "FROZEN":
            errors.append(f"schema_freeze_status must be FROZEN: {row['path']}")

    # 12. router.py 추가 수정 없음
    router_content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J4" in router_content:
        errors.append("router.py contains PHASE_1J4 — modification detected")

    # 13. frontend 수정 없음
    tsx = REPO_ROOT / "admin-web/src/app/external-tasks/page.tsx"
    if tsx.exists():
        if "PHASE_1J4" in tsx.read_text(encoding="utf-8", errors="ignore"):
            errors.append("admin-web page.tsx contains PHASE_1J4 — modification detected")

    # 14. forbidden patterns in smoke script
    smoke_content = smoke_path.read_text(encoding="utf-8", errors="ignore")
    for bad in ["import requests", "import httpx", "os.environ[", "os.getenv("]:
        if bad in smoke_content:
            errors.append(f"forbidden pattern in smoke: {bad}")

    # 15. external_work_registry NEEDS_CONFIRM → WARN
    for b in fixtures.get("backend_callers_fixture", []):
        if b.get("is_runtime_http_caller") == "NEEDS_CONFIRM":
            warnings.append(
                f"{b['file']} HTTP 호출 여부 NEEDS_CONFIRM — Phase 1-J5에서 확인 필요"
            )

    # 16. smoke warnings 전달
    for w in smoke_result.get("warnings", []):
        warnings.append(f"[smoke] {w}")

    # 17. verdict
    if errors:
        verdict = "PHASE1J4_CALLER_MIGRATION_DRY_RUN_FAIL"
    elif warnings:
        verdict = "PHASE1J4_CALLER_MIGRATION_DRY_RUN_READY_WITH_WARN"
    else:
        verdict = "PHASE1J4_CALLER_MIGRATION_DRY_RUN_READY"

    return {
        "phase": PHASE,
        "audit_id": AUDIT_ID,
        "verdict": verdict,
        "caller_modification_allowed_now": CALLER_MODIFICATION_ALLOWED_NOW,
        "legacy_disable_allowed_now": LEGACY_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "smoke_verdict": smoke_result.get("verdict"),
        "smoke_total": smoke_result.get("total_scenarios"),
        "smoke_passed": smoke_result.get("passed_scenarios"),
        "smoke_failed": smoke_result.get("failed_scenarios"),
        "dry_run_matrix": DRY_RUN_MATRIX,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J4는 fixture 기반 dry-run 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 / smoke 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J4 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
