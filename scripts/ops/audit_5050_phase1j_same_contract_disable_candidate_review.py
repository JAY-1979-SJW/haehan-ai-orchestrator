"""
Phase 1-J: SAME_CONTRACT Legacy Disable Candidate Review
GET /api/v1/inbox, POST /api/v1/tasks 비활성화 후보 검토.
실제 비활성화 금지. read-only / audit / test 공정.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J"
REVIEW_ID = "PHASE1J_SAME_CONTRACT_LEGACY_DISABLE_CANDIDATE_REVIEW"

# ── 절대 금지 상수 ────────────────────────────────────────────────────────────
LEGACY_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False

# ── 제외 대상 (Phase 1-J 범위 외) ─────────────────────────────────────────────
EXCLUDED_ROUTES = [
    "/api/v1/tasks/{task_id}/execute",   # HOLD_DANGEROUS
    "/api/v1/webhooks/telegram",          # DO_NOT_TOUCH
    "/api/v1/tasks/{task_id}/approve",    # COMPATIBLE_WITH_ADAPTER
    "/api/v1/tasks/{task_id}/reject",     # COMPATIBLE_WITH_ADAPTER
    "/api/v1/inbox/email/fetch",          # COMPATIBLE_WITH_ADAPTER
    "/dashboard",                         # HOLD
]

# ── SAME_CONTRACT review matrix ──────────────────────────────────────────────
REVIEW_MATRIX = [
    {
        "phase": PHASE,
        "review_id": REVIEW_ID,
        "legacy_method": "GET",
        "legacy_path": "/api/v1/inbox",
        "fastapi_method": "GET",
        "fastapi_path": "/api/v1/inbox",
        "overlap_class": "SAME_CONTRACT",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "same_contract_confidence": "HIGH",
        "side_effect_classification": "READ_ONLY",
        "required_before_disable": [
            "8400 response schema freeze 완료",
            "caller inventory 확인 (frontend: admin-web/src/app/external-tasks/page.tsx)",
            "fallback/rollback route 확인",
            "5050 route disable flag 설계",
            "smoke 통과",
            "frontend caller 경로 전환 확인",
        ],
        "required_tests_before_disable": [
            "GET /api/v1/inbox response schema 일치 테스트",
            "caller 전환 후 E2E smoke 테스트",
            "fallback 동작 확인 테스트",
        ],
        "rollback_plan": "5050 route disable flag → False 복귀 (router.py 수정 불필요)",
        "risk_level": "LOW",
        "blockers": [
            "frontend caller admin-web/src/app/external-tasks/page.tsx 전환 미완",
            "response schema freeze 미완",
        ],
        "next_phase": "Phase 1-J2: SAME_CONTRACT response schema freeze",
        "verdict": "DISABLE_CANDIDATE_REVIEW_READY",
    },
    {
        "phase": PHASE,
        "review_id": REVIEW_ID,
        "legacy_method": "POST",
        "legacy_path": "/api/v1/tasks",
        "fastapi_method": "POST",
        "fastapi_path": "/api/v1/tasks",
        "overlap_class": "SAME_CONTRACT",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "same_contract_confidence": "MEDIUM",
        "side_effect_classification": "WRITE_POSSIBLE",
        "side_effect_detail": (
            "task 생성/등록/요청 처리 — approve/reject/execute와 구분됨. "
            "plan/execute 내부 호출로 DB/외부 연동 가능성 있음. "
            "자동 비활성화 금지."
        ),
        "required_before_disable": [
            "request/response schema freeze 완료",
            "side effect 전체 경로 추적 (plan → execute 흐름)",
            "caller inventory 확인 (ai_orchestrator, backend 내부 호출 포함)",
            "rollback route 확인",
            "5050 route disable flag 설계",
            "smoke 통과",
            "DB write path 격리 확인",
        ],
        "required_tests_before_disable": [
            "POST /api/v1/tasks request/response schema 일치 테스트",
            "side effect 없는 경우 동등 동작 확인 테스트",
            "fallback 동작 확인 테스트",
        ],
        "rollback_plan": "5050 route disable flag → False 복귀. plan/execute 호출 영향 없음.",
        "risk_level": "MEDIUM",
        "blockers": [
            "side effect 전체 경로 추적 미완",
            "request/response schema freeze 미완",
            "caller inventory 내부 호출 (mcp_server/tasks_router.py 포함) 미확인",
        ],
        "next_phase": "Phase 1-J2: SAME_CONTRACT response schema freeze",
        "verdict": "DISABLE_CANDIDATE_REVIEW_READY",
    },
]


def _caller_inventory():
    """SAME_CONTRACT 2개 route caller — 정적 스캔 결과 (2026-05-18 기준)."""
    # rglob 기반 런타임 스캔은 admin-web .next 빌드 결과물로 타임아웃 발생.
    # 수동 스캔 결과를 정적으로 기록.
    return {
        "real_backend": [
            "ai_orchestrator/external_work_registry.py",                                    # /api/v1/inbox
            "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",             # /api/v1/inbox
            "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
            "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
            "ai_orchestrator/gabia/autowork_subdomain_plan.py",                             # /api/v1/tasks
            "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
            "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
            "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
        ],
        "real_frontend": [
            "admin-web/src/app/external-tasks/page.tsx",                                    # /api/v1/inbox
        ],
        "test": [
            "tests/test_5050_legacy_characterization_20260517.py",
            "tests/test_5050_phase1_8400_contract_freeze_20260517.py",
            "ai_orchestrator/tests/test_approval_execution_flow.py",
            "ai_orchestrator/tests/test_router_smoke.py",
            "tests/test_email_task_approval.py",
        ],
        "audit_smoke": [
            "scripts/ops/audit_5050_legacy_characterization.py",
            "scripts/ops/audit_5050_phase1_8400_contract_freeze.py",
            "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py",
            "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py",
        ],
        "unknown": [
            "inbox_router.py",
            "tasks_router.py",
            "mcp_server/server.py",
            "mcp_server/write_guard.py",
        ],
        "scan_note": "2026-05-18 수동 스캔. admin-web/.next 빌드 산출물 제외.",
    }


def run_audit():
    errors = []
    warnings = []

    # 1. SAME_CONTRACT 2개 matrix 검증
    if len(REVIEW_MATRIX) != 2:
        errors.append(f"review matrix row count != 2: {len(REVIEW_MATRIX)}")

    paths = [r["legacy_path"] for r in REVIEW_MATRIX]
    if "/api/v1/inbox" not in paths:
        errors.append("GET /api/v1/inbox row missing")
    if "/api/v1/tasks" not in paths:
        errors.append("POST /api/v1/tasks row missing")

    for row in REVIEW_MATRIX:
        if row["overlap_class"] != "SAME_CONTRACT":
            errors.append(f"overlap_class != SAME_CONTRACT: {row['legacy_path']}")
        if not row["disable_candidate"]:
            errors.append(f"disable_candidate not True: {row['legacy_path']}")
        if row["disable_allowed_now"]:
            errors.append(f"disable_allowed_now must be False: {row['legacy_path']}")
        if not row.get("required_before_disable"):
            errors.append(f"required_before_disable missing: {row['legacy_path']}")
        if not row.get("rollback_plan"):
            errors.append(f"rollback_plan missing: {row['legacy_path']}")

    # POST /api/v1/tasks side effect 분류 확인
    tasks_row = next((r for r in REVIEW_MATRIX if r["legacy_path"] == "/api/v1/tasks"), None)
    if tasks_row:
        if tasks_row.get("side_effect_classification") != "WRITE_POSSIBLE":
            warnings.append("POST /api/v1/tasks side_effect_classification != WRITE_POSSIBLE")
        if not tasks_row.get("side_effect_detail"):
            errors.append("POST /api/v1/tasks side_effect_detail missing")

    # 2. 제외 대상 확인
    matrix_paths = [r["legacy_path"] for r in REVIEW_MATRIX]
    for excl in ["/execute", "/dashboard", "/webhook"]:
        if any(excl in p for p in matrix_paths):
            errors.append(f"excluded route found in matrix: {excl}")

    # 3. 전역 금지 상수
    if LEGACY_DISABLE_ALLOWED_NOW:
        errors.append("LEGACY_DISABLE_ALLOWED_NOW must be False")
    if ROUTER_FILE_MODIFICATION_ALLOWED:
        errors.append("ROUTER_FILE_MODIFICATION_ALLOWED must be False")
    if SERVER_APPLY_ALLOWED:
        errors.append("SERVER_APPLY_ALLOWED must be False")
    if LIVE_TRAFFIC_ALLOWED:
        errors.append("LIVE_TRAFFIC_ALLOWED must be False")
    if DB_WRITE_ALLOWED:
        errors.append("DB_WRITE_ALLOWED must be False")

    # 4. router.py 추가 수정 없음 확인
    router_content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J" in router_content:
        errors.append("router.py contains PHASE_1J — router modification detected")

    # 5. caller inventory
    caller_inv = _caller_inventory()
    real_caller_count = len(caller_inv.get("real_backend", [])) + len(
        caller_inv.get("real_frontend", [])
    )
    if real_caller_count > 0:
        warnings.append(
            f"real callers found ({real_caller_count}) — schema freeze required before disable"
        )

    # 6. verdict
    row_verdicts = [r.get("verdict") for r in REVIEW_MATRIX]
    any_warn = any(v == "REVIEW_WITH_WARN" for v in row_verdicts) or bool(warnings)
    verdict = (
        "REVIEW_WITH_WARN"
        if (errors == [] and any_warn)
        else (
            "PHASE1J_SAME_CONTRACT_DISABLE_CANDIDATE_REVIEW_FAIL"
            if errors
            else "PHASE1J_SAME_CONTRACT_DISABLE_CANDIDATE_REVIEW_READY"
        )
    )

    return {
        "phase": PHASE,
        "review_id": REVIEW_ID,
        "verdict": verdict,
        "legacy_disable_allowed_now": LEGACY_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "review_matrix": REVIEW_MATRIX,
        "caller_inventory": caller_inv,
        "caller_inventory_real_count": real_caller_count,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J은 read-only 검토 공정. router.py 수정 없음.",
            "롤백 필요 시: git revert 를 이용하거나 이 스크립트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J Audit: {result['verdict']} ===")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARN:  {w}")
