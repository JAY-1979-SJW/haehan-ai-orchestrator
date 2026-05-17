"""
Phase 1-J3: SAME_CONTRACT Caller Migration Plan
GET /api/v1/inbox, POST /api/v1/tasks caller 분류 확정 및 migration plan 작성.
실제 caller 수정 금지. read-only / plan 공정.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J3"
PLAN_ID = "PHASE1J3_SAME_CONTRACT_CALLER_MIGRATION_PLAN"

# ── 절대 금지 상수 ────────────────────────────────────────────────────────────
CALLER_MODIFICATION_ALLOWED_NOW = False
LEGACY_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
PLAN_ONLY = True

# ── unknown caller 정적 분석 결과 (2026-05-18) ────────────────────────────────
# 분석 근거:
#   inbox_router.py / tasks_router.py:
#     - Flask Blueprint 기반. dashboard.py에서만 import + register_blueprint.
#     - 실제 FastAPI server(ai_orchestrator/server.py)는 from .router import router 만 사용.
#     - dashboard.py는 운영 대시보드 전용 Flask app (별도 프로세스).
#     - 따라서 8400 FastAPI /api/v1 경로와 무관. NOT_MOUNTED (FastAPI 기준).
#   mcp_server/server.py:
#     - /api/v1/tasks 문자열은 주석·에러메시지에만 존재. 실제 HTTP 호출 없음.
#   mcp_server/write_guard.py:
#     - /api/v1/tasks 문자열은 에러 메시지에만 존재. 실제 호출 없음.

UNKNOWN_CALLER_MOUNT_STATUS = {
    "inbox_router.py": {
        "status": "NOT_MOUNTED",
        "basis": (
            "Flask Blueprint (inbox_bp). dashboard.py에서 register_blueprint 됨. "
            "FastAPI server(ai_orchestrator/server.py)는 이 Blueprint를 import하지 않음. "
            "8400 FastAPI /api/v1/inbox 경로와 무관."
        ),
        "runtime_impact": "NONE_ON_FASTAPI",
        "follow_up_needed": False,
    },
    "tasks_router.py": {
        "status": "NOT_MOUNTED",
        "basis": (
            "Flask Blueprint (tasks_bp). dashboard.py에서 register_blueprint 됨. "
            "FastAPI server(ai_orchestrator/server.py)는 이 Blueprint를 import하지 않음. "
            "8400 FastAPI /api/v1/tasks 경로와 무관."
        ),
        "runtime_impact": "NONE_ON_FASTAPI",
        "follow_up_needed": False,
    },
    "mcp_server/server.py": {
        "status": "NOT_MOUNTED",
        "basis": (
            "/api/v1/tasks 참조는 주석 및 docstring에만 존재. "
            "실제 HTTP 호출 코드(httpx/requests/fetch) 없음. "
            "MCP 서버는 CAD 도구 레이어로 FastAPI router와 무관."
        ),
        "runtime_impact": "NONE_ON_FASTAPI",
        "follow_up_needed": False,
    },
    "mcp_server/write_guard.py": {
        "status": "NOT_MOUNTED",
        "basis": (
            "/api/v1/tasks 참조는 에러 메시지 문자열에만 존재. "
            "실제 HTTP 호출 없음. MCP write guard 레이어."
        ),
        "runtime_impact": "NONE_ON_FASTAPI",
        "follow_up_needed": False,
    },
}

# ── caller inventory (Phase 1-J2 + 정적 분석 결과 반영) ──────────────────────
CALLER_INVENTORY = {
    "real_frontend_callers": [
        {
            "file": "admin-web/src/app/external-tasks/page.tsx",
            "route": "/api/v1/inbox",
            "call_type": "HTTP GET (fetch 또는 axios)",
            "migration_target": "8400 GET /api/v1/inbox (동일 경로, SAME_CONTRACT)",
            "migration_risk": "LOW",
            "migration_note": "응답 스키마 동일. 경로 전환 불필요하나 endpoint 출처 확인 필요.",
        },
    ],
    "real_backend_callers": [
        {
            "file": "ai_orchestrator/external_work_registry.py",
            "route": "/api/v1/inbox",
            "call_type": "URL 문자열 참조 (정적 확인 필요)",
            "migration_target": "8400 GET /api/v1/inbox",
            "migration_risk": "LOW",
            "migration_note": "실제 HTTP 호출인지 URL 문자열 상수인지 Phase 1-J3 후속 확인 필요.",
        },
        {
            "file": "ai_orchestrator/gabia/autowork_subdomain_plan.py",
            "route": "/api/v1/tasks",
            "call_type": "URL 문자열 참조 (계획 문서 성격)",
            "migration_target": "8400 POST /api/v1/tasks",
            "migration_risk": "LOW",
            "migration_note": "자동화 계획 파일로 실제 HTTP 호출 코드인지 확인 필요.",
        },
    ],
    "backend_compat_callers": [
        "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
        "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
        "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
        "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
        "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
    ],
    "unknown_callers": [
        {
            "file": "inbox_router.py",
            "mount_status": "NOT_MOUNTED",
            "runtime_impact": "NONE_ON_FASTAPI",
        },
        {
            "file": "tasks_router.py",
            "mount_status": "NOT_MOUNTED",
            "runtime_impact": "NONE_ON_FASTAPI",
        },
        {
            "file": "mcp_server/server.py",
            "mount_status": "NOT_MOUNTED",
            "runtime_impact": "NONE_ON_FASTAPI",
        },
        {
            "file": "mcp_server/write_guard.py",
            "mount_status": "NOT_MOUNTED",
            "runtime_impact": "NONE_ON_FASTAPI",
        },
    ],
    "test_callers": [
        "tests/test_5050_legacy_characterization_20260517.py",
        "tests/test_5050_phase1_8400_contract_freeze_20260517.py",
        "ai_orchestrator/tests/test_approval_execution_flow.py",
        "ai_orchestrator/tests/test_router_smoke.py",
        "tests/test_email_task_approval.py",
    ],
    "audit_smoke_callers": [
        "scripts/ops/audit_5050_legacy_characterization.py",
        "scripts/ops/audit_5050_phase1_8400_contract_freeze.py",
        "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py",
        "scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py",
    ],
    "docs_report_callers": [],
    "scan_note": "2026-05-18. unknown 4개 NOT_MOUNTED 확정. admin-web/.next 제외.",
}

# ── migration plan matrix ─────────────────────────────────────────────────────
MIGRATION_PLAN = [
    {
        "phase": PHASE,
        "plan_id": PLAN_ID,
        "method": "GET",
        "path": "/api/v1/inbox",
        "side_effect_classification": "READ_ONLY_EXPECTED",
        "schema_freeze_status": "FROZEN",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "caller_modification_allowed_now": False,
        "real_frontend_callers": ["admin-web/src/app/external-tasks/page.tsx"],
        "real_backend_callers": ["ai_orchestrator/external_work_registry.py"],
        "backend_compat_callers": [
            "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
            "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
            "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        ],
        "unknown_callers": [
            {"file": "inbox_router.py", "mount_status": "NOT_MOUNTED"},
        ],
        "unknown_mount_status": "ALL_NOT_MOUNTED",
        "migration_priority": "FIRST",
        "migration_steps": [
            "1. real caller 목록 확정 (external_work_registry.py HTTP 호출 여부 재확인)",
            "2. admin-web external-tasks page.tsx가 8400 응답 스키마(InboxItem list)와 호환 확인",
            "3. external_work_registry.py URL 참조 성격 확인 (HTTP 호출 vs 상수)",
            "4. backend_compat 6개는 Phase 1-adapter 공정에서 별도 처리 — migration 범위 제외",
            "5. 8400 GET /inbox response schema contract test 작성",
            "6. frontend smoke fixture 작성 (실제 호출 금지, fixture 기반)",
            "7. 5050 legacy GET /inbox disable feature flag 설계",
            "8. rollback route 확인 (8400 → 5050 fallback 경로)",
        ],
        "required_before_migration": [
            "external_work_registry.py HTTP 호출 여부 재확인",
            "admin-web page.tsx 응답 스키마 호환 확인",
        ],
        "required_after_migration": [
            "admin-web frontend smoke 통과",
            "8400 response schema contract test 통과",
        ],
        "required_before_disable": [
            "caller migration 완료",
            "frontend smoke 통과",
            "backend smoke 통과",
            "8400 response schema contract test 완료",
            "disable feature flag 설계 완료",
            "rollback 검증 완료",
        ],
        "rollback_plan": (
            "5050 legacy GET /inbox disable flag → False 복귀. "
            "8400 handler는 이미 동작 중이므로 즉시 복귀 가능. "
            "READ_ONLY이므로 부작용 없음."
        ),
        "risk_level": "LOW",
        "blockers": [
            "external_work_registry.py HTTP 호출 여부 미확인",
            "admin-web caller 전환 계획 미완",
        ],
        "next_phase": "Phase 1-J4: caller migration dry-run smoke",
        "verdict": "CALLER_MIGRATION_PLAN_READY",
    },
    {
        "phase": PHASE,
        "plan_id": PLAN_ID,
        "method": "POST",
        "path": "/api/v1/tasks",
        "side_effect_classification": "WRITE_POSSIBLE",
        "schema_freeze_status": "FROZEN",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "caller_modification_allowed_now": False,
        "real_frontend_callers": [],
        "real_backend_callers": ["ai_orchestrator/gabia/autowork_subdomain_plan.py"],
        "backend_compat_callers": [
            "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
            "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
            "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
        ],
        "unknown_callers": [
            {"file": "tasks_router.py", "mount_status": "NOT_MOUNTED"},
            {"file": "mcp_server/server.py", "mount_status": "NOT_MOUNTED"},
            {"file": "mcp_server/write_guard.py", "mount_status": "NOT_MOUNTED"},
        ],
        "unknown_mount_status": "ALL_NOT_MOUNTED",
        "migration_priority": "LATER",
        "migration_steps": [
            "1. real caller 목록 확정 (gabia/autowork_subdomain_plan.py HTTP 호출 여부 재확인)",
            "2. write side effect 확인: plan() → execute() 전체 경로 추적",
            "3. approval_token 발행 영향 분류 (cancel/revoke path 존재 여부)",
            "4. backend caller 전환 계획 작성 (legacy 5050 호출 → 8400 직접 호출)",
            "5. frontend caller 영향 확인 (없음으로 보이나 재확인)",
            "6. dry-run smoke fixture 작성 (실제 POST 금지)",
            "7. 5050 legacy POST /tasks disable feature flag 설계",
            "8. rollback route 확인 (approval_token 미발행 rollback path)",
            "9. 대표님 별도 승인 gate 확인 (WRITE_POSSIBLE route disable)",
        ],
        "required_before_migration": [
            "gabia/autowork_subdomain_plan.py HTTP 호출 여부 재확인",
            "plan() → execute() side effect 전체 경로 추적",
            "approval_token 발행 cancel/revoke path 확인",
        ],
        "required_after_migration": [
            "dry-run smoke 통과",
            "8400 request/response schema contract test 통과",
            "DB write 영향 없음 확인",
        ],
        "required_before_disable": [
            "request schema exact freeze (완료)",
            "response schema exact freeze (완료)",
            "side effect confirmation 완료",
            "caller migration 완료",
            "approval_token 영향 분석 완료",
            "DB write 영향 분석 완료",
            "disable feature flag 설계 완료",
            "rollback 검증 완료",
            "대표님 user approval gate 확인",
        ],
        "rollback_plan": (
            "5050 legacy POST /tasks disable flag → False 복귀. "
            "approval_token 발행 영향은 executor rollback으로 별도 관리. "
            "router.py 수정 불필요. WRITE_POSSIBLE이므로 rollback 이전 대표님 승인 필수."
        ),
        "risk_level": "MEDIUM",
        "blockers": [
            "plan() → execute() side effect 전체 경로 추적 미완",
            "approval_token 발행 영향 분석 미완",
            "DB write 영향 분석 미완",
            "대표님 user approval gate 미설계",
        ],
        "next_phase": "Phase 1-J4: caller migration dry-run smoke",
        "verdict": "CALLER_MIGRATION_PLAN_WITH_WARN",
    },
]


def run_audit():
    errors = []
    warnings = []

    # 1. plan matrix 기본 검증
    if len(MIGRATION_PLAN) != 2:
        errors.append(f"migration plan row count != 2: {len(MIGRATION_PLAN)}")

    paths = [r["path"] for r in MIGRATION_PLAN]
    if "/api/v1/inbox" not in paths:
        errors.append("GET /api/v1/inbox row missing")
    if "/api/v1/tasks" not in paths:
        errors.append("POST /api/v1/tasks row missing")

    for row in MIGRATION_PLAN:
        for field in ["migration_steps", "required_before_migration",
                      "required_after_migration", "required_before_disable", "rollback_plan"]:
            if not row.get(field):
                errors.append(f"{field} missing: {row['path']}")
        if row["disable_allowed_now"]:
            errors.append(f"disable_allowed_now must be False: {row['path']}")
        if row["caller_modification_allowed_now"]:
            errors.append(f"caller_modification_allowed_now must be False: {row['path']}")
        if row["schema_freeze_status"] != "FROZEN":
            errors.append(f"schema_freeze_status must be FROZEN: {row['path']}")

    # 2. GET inbox migration priority가 POST tasks보다 빠름
    inbox_row = next((r for r in MIGRATION_PLAN if r["path"] == "/api/v1/inbox"), None)
    tasks_row = next((r for r in MIGRATION_PLAN if r["path"] == "/api/v1/tasks"), None)
    if inbox_row and tasks_row:
        if inbox_row["migration_priority"] != "FIRST":
            errors.append("GET /inbox migration_priority must be FIRST")
        if tasks_row["migration_priority"] != "LATER":
            errors.append("POST /tasks migration_priority must be LATER")
        if inbox_row["side_effect_classification"] != "READ_ONLY_EXPECTED":
            errors.append("GET /inbox side_effect must be READ_ONLY_EXPECTED")
        if tasks_row["side_effect_classification"] != "WRITE_POSSIBLE":
            errors.append("POST /tasks side_effect must be WRITE_POSSIBLE")

    # 3. unknown caller mount status 분류 확인
    all_unknown_statuses = []
    for key, val in UNKNOWN_CALLER_MOUNT_STATUS.items():
        status = val.get("status")
        if status not in ("RUNTIME_MOUNTED", "POSSIBLY_MOUNTED", "NOT_MOUNTED",
                           "TEST_ONLY", "UNKNOWN_NEEDS_FOLLOWUP"):
            errors.append(f"invalid unknown_mount_status for {key}: {status}")
        all_unknown_statuses.append(status)
        if status == "UNKNOWN_NEEDS_FOLLOWUP" and not val.get("basis"):
            errors.append(f"UNKNOWN_NEEDS_FOLLOWUP requires basis: {key}")
        if status in ("RUNTIME_MOUNTED", "POSSIBLY_MOUNTED"):
            if not LEGACY_DISABLE_ALLOWED_NOW is False:
                errors.append(f"RUNTIME_MOUNTED found but LEGACY_DISABLE_ALLOWED_NOW is True")
            warnings.append(f"runtime mounted unknown caller: {key} — disable_allowed_now=False 유지")

    if "UNKNOWN_NEEDS_FOLLOWUP" in all_unknown_statuses:
        warnings.append("UNKNOWN_NEEDS_FOLLOWUP 존재 — 추가 확인 필요")

    # 4. 전역 금지 상수
    for name, val in [
        ("CALLER_MODIFICATION_ALLOWED_NOW", CALLER_MODIFICATION_ALLOWED_NOW),
        ("LEGACY_DISABLE_ALLOWED_NOW", LEGACY_DISABLE_ALLOWED_NOW),
        ("ROUTER_FILE_MODIFICATION_ALLOWED", ROUTER_FILE_MODIFICATION_ALLOWED),
        ("SERVER_APPLY_ALLOWED", SERVER_APPLY_ALLOWED),
        ("LIVE_TRAFFIC_ALLOWED", LIVE_TRAFFIC_ALLOWED),
        ("DB_WRITE_ALLOWED", DB_WRITE_ALLOWED),
    ]:
        if val:
            errors.append(f"{name} must be False")

    # 5. 제외 대상 확인
    plan_paths = [r["path"] for r in MIGRATION_PLAN]
    for excl in ["/execute", "/dashboard", "/webhook", "/approve", "/reject", "/email/fetch"]:
        if any(excl in p for p in plan_paths):
            errors.append(f"excluded route found in plan: {excl}")

    # 6. router.py 추가 수정 없음
    router_content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J3" in router_content:
        errors.append("router.py contains PHASE_1J3 — router modification detected")

    # 7. caller inventory 기본 확인
    inv = CALLER_INVENTORY
    real_fe = len(inv.get("real_frontend_callers", []))
    real_be = len(inv.get("real_backend_callers", []))
    if real_fe + real_be > 0:
        warnings.append(
            f"real callers remain (frontend={real_fe}, backend={real_be}) — "
            "migration 완료 전 disable 금지"
        )

    # 8. POST tasks blockers WARN
    if tasks_row:
        blockers = tasks_row.get("blockers", [])
        if blockers:
            warnings.append(
                f"POST /tasks has {len(blockers)} blockers — migration plan with warn"
            )

    # 9. verdict
    row_verdicts = [r.get("verdict") for r in MIGRATION_PLAN]
    any_row_warn = any(v == "CALLER_MIGRATION_PLAN_WITH_WARN" for v in row_verdicts)
    if errors:
        verdict = "PHASE1J3_CALLER_MIGRATION_PLAN_FAIL"
    elif any_row_warn or warnings:
        verdict = "CALLER_MIGRATION_PLAN_WITH_WARN"
    else:
        verdict = "PHASE1J3_CALLER_MIGRATION_PLAN_READY"

    return {
        "phase": PHASE,
        "plan_id": PLAN_ID,
        "verdict": verdict,
        "caller_modification_allowed_now": CALLER_MODIFICATION_ALLOWED_NOW,
        "legacy_disable_allowed_now": LEGACY_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "plan_only": PLAN_ONLY,
        "unknown_caller_mount_status": UNKNOWN_CALLER_MOUNT_STATUS,
        "caller_inventory": CALLER_INVENTORY,
        "migration_plan": MIGRATION_PLAN,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J3는 read-only plan 공정. router.py / caller 파일 수정 없음.",
            "롤백 필요 시: 이 스크립트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J3 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
