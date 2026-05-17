"""
Phase 1-J2: SAME_CONTRACT Response Schema Freeze
GET /api/v1/inbox, POST /api/v1/tasks 요청/응답 스키마 정적 고정.
실제 비활성화 금지. read-only / schema freeze 공정.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

PHASE = "PHASE_1J2"
FREEZE_ID = "PHASE1J2_SAME_CONTRACT_RESPONSE_SCHEMA_FREEZE"

# ── 절대 금지 상수 ────────────────────────────────────────────────────────────
LEGACY_DISABLE_ALLOWED_NOW = False
ROUTER_FILE_MODIFICATION_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DB_WRITE_ALLOWED = False
SCHEMA_FREEZE_ONLY = True

# ── caller inventory (2026-05-18 Phase 1-J 스캔 결과 재분류) ─────────────────
CALLER_INVENTORY = {
    "real_frontend_callers": [
        "admin-web/src/app/external-tasks/page.tsx",   # /api/v1/inbox 호출
    ],
    "real_backend_callers": [
        "ai_orchestrator/external_work_registry.py",   # /api/v1/inbox 참조
        "ai_orchestrator/gabia/autowork_subdomain_plan.py",  # /api/v1/tasks 참조
    ],
    "backend_compat_callers": [
        # backend/compat/legacy_5050 내 wrapper/adapter/skeleton — 실제 호출자 아닌 계약 참조
        "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
        "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
        "backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py",
        "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
        "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
        "backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py",
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
    "unknown_callers": [
        # Phase 1-J2 이후 별도 검토 필요
        "inbox_router.py",           # root-level legacy router, 실제 서버 마운트 여부 불명
        "tasks_router.py",           # root-level legacy router, 실제 서버 마운트 여부 불명
        "mcp_server/server.py",      # MCP 레이어, tasks path 문자열 참조
        "mcp_server/write_guard.py", # MCP write guard, path 패턴 참조
    ],
    "unknown_warning_reason": (
        "inbox_router.py / tasks_router.py는 root-level legacy router로 "
        "실제 서버 마운트 여부가 정적 분석만으로 불확실. "
        "mcp_server는 MCP 레이어 path 참조로 실제 HTTP 호출자인지 불명. "
        "Phase 1-J3 (caller migration plan)에서 확인 필요."
    ),
    "scan_note": "2026-05-18 Phase 1-J 스캔 기반 재분류. admin-web/.next 빌드 산출물 제외.",
}

# ── InboxItem schema (ai_orchestrator/inbox.py @dataclass 기준) ──────────────
_INBOX_ITEM_SCHEMA = {
    "type": "object",
    "required_keys": [
        "item_id", "source_type", "source_account", "external_id",
        "sender", "title", "body_raw", "body_summary",
        "received_at", "saved_at", "status", "linked_task_id",
    ],
    "optional_keys": ["metadata"],
    "key_types": {
        "item_id": "str", "source_type": "str", "source_account": "str",
        "external_id": "str", "sender": "str", "title": "str",
        "body_raw": "str", "body_summary": "str", "received_at": "str",
        "saved_at": "str", "status": "str", "linked_task_id": "str",
        "metadata": "dict",
    },
    "status_values": ["new", "reviewed", "task_created", "archived"],
    "source": "ai_orchestrator/inbox.py::InboxItem (dataclass)",
}

# ── TaskSubmit request schema (ai_orchestrator/router.py::TaskSubmit) ─────────
_TASK_SUBMIT_REQUEST_SCHEMA = {
    "type": "object",
    "required_keys": ["task_id", "source", "action_type", "target", "description"],
    "optional_keys": ["payload", "requested_by"],
    "key_types": {
        "task_id": "str", "source": "str", "action_type": "str",
        "target": "str", "description": "str",
        "payload": "dict (default={})", "requested_by": "Optional[str]",
    },
    "notes": "requested_by는 서버가 무시하고 current_user.actor로 덮어씀.",
    "source": "ai_orchestrator/router.py::TaskSubmit (Pydantic BaseModel)",
}

# ── TaskSubmit response schema (router.py::submit_task 반환값 기준) ───────────
_TASK_SUBMIT_RESPONSE_SCHEMA = {
    "type": "object",
    "required_keys": [
        "task_id", "risk_level", "allowed", "requires_approval",
        "approval_token_id", "status", "steps", "blocked_reasons",
    ],
    "optional_keys": [],
    "key_types": {
        "task_id": "str", "risk_level": "str", "allowed": "bool",
        "requires_approval": "bool", "approval_token_id": "Optional[str]",
        "status": "str", "steps": "list", "blocked_reasons": "list",
    },
    "source": "ai_orchestrator/router.py::submit_task return dict",
}

# ── freeze matrix ─────────────────────────────────────────────────────────────
FREEZE_MATRIX = [
    {
        "phase": PHASE,
        "freeze_id": FREEZE_ID,
        "method": "GET",
        "legacy_path": "/api/v1/inbox",
        "fastapi_path": "/api/v1/inbox",
        "overlap_class": "SAME_CONTRACT",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "request_schema_frozen": True,
        "response_schema_frozen": True,
        "request_schema": {
            "method": "GET",
            "path": "/api/v1/inbox",
            "body_required": False,
            "query_params": {"limit": "int (default=20, min=1, max=500)"},
            "auth_required": False,
            "auth_note": "router.py에 Depends(require_role) 없음 — 공개 엔드포인트",
        },
        "response_schema": {
            "top_level_type": "list",
            "item_schema": _INBOX_ITEM_SCHEMA,
            "empty_list_on_no_data": True,
        },
        "status_code_contract": {
            "success": 200,
            "error_500": "서버 내부 오류 시 FastAPI 기본 500",
        },
        "error_schema_contract": {
            "format": "FastAPI default HTTPException detail JSON",
            "known_errors": [],
        },
        "auth_contract": {
            "required": False,
            "note": "현재 8400 handler에 auth Depends 없음. 비활성화 전 auth 일치 여부 재확인 필요.",
        },
        "side_effect_classification": "READ_ONLY_EXPECTED",
        "caller_inventory_status": "REAL_CALLERS_PRESENT",
        "real_caller_count": 2,
        "frontend_caller_count": 1,
        "backend_caller_count": 1,
        "unknown_caller_count": 4,
        "required_before_disable": [
            "admin-web/src/app/external-tasks/page.tsx caller 경로 전환 확인",
            "8400 GET /inbox response schema contract test 작성 및 통과",
            "auth contract 재확인 (5050 vs 8400 동일 여부)",
            "frontend smoke 통과 (caller 전환 후)",
            "5050 route disable feature flag 설계 및 검토",
            "unknown caller 4개 마운트 여부 확인 (Phase 1-J3)",
        ],
        "rollback_plan": (
            "5050 route disable flag → False 복귀 (router.py 수정 불필요). "
            "GET /inbox는 read-only라 롤백 위험도 LOW."
        ),
        "risk_level": "LOW",
        "blockers": [
            "frontend caller admin-web/src/app/external-tasks/page.tsx 전환 미완",
            "auth contract 일치 여부 미확인",
            "unknown caller 4개 마운트 여부 미확인",
        ],
        "verdict": "SCHEMA_FREEZE_READY",
    },
    {
        "phase": PHASE,
        "freeze_id": FREEZE_ID,
        "method": "POST",
        "legacy_path": "/api/v1/tasks",
        "fastapi_path": "/api/v1/tasks",
        "overlap_class": "SAME_CONTRACT",
        "disable_candidate": True,
        "disable_allowed_now": False,
        "request_schema_frozen": True,
        "response_schema_frozen": True,
        "request_schema": _TASK_SUBMIT_REQUEST_SCHEMA,
        "response_schema": _TASK_SUBMIT_RESPONSE_SCHEMA,
        "status_code_contract": {
            "success": 200,
            "auth_failure": 403,
            "plan_block": 200,
            "rate_limited": 200,
            "error_500": "서버 내부 오류 시 FastAPI 기본 500",
            "note": "blocked/rate_limited도 200으로 반환하며 status 필드로 구분",
        },
        "error_schema_contract": {
            "format": "FastAPI default HTTPException detail JSON",
            "known_errors": [403],
        },
        "auth_contract": {
            "required": True,
            "roles": ["operator", "admin", "owner"],
            "source": "ai_orchestrator/router.py::submit_task Depends(require_role)",
        },
        "side_effect_classification": "WRITE_POSSIBLE",
        "side_effect_detail": (
            "plan() → execute() 흐름으로 실행. "
            "executor는 DRY_RUN / BLOCKED / EXECUTION_RATE_LIMITED / EXECUTION_TIMEOUT 분기. "
            "plan()은 risk 평가만. execute()는 실제 외부 동작 가능성 있음. "
            "approval_token 발행도 side effect. "
            "자동 비활성화 금지."
        ),
        "caller_inventory_status": "REAL_CALLERS_PRESENT",
        "real_caller_count": 2,
        "frontend_caller_count": 0,
        "backend_caller_count": 2,
        "unknown_caller_count": 4,
        "required_before_disable": [
            "request schema exact freeze (현재 완료)",
            "response schema exact freeze (현재 완료)",
            "side effect confirmation: execute() 경로 전체 추적",
            "caller 전환 확인 (ai_orchestrator/external_work_registry.py 포함)",
            "DB write 영향 분석 (executor 내부 포함)",
            "unknown caller 4개 마운트 여부 확인 (Phase 1-J3)",
            "5050 route disable feature flag 설계 및 검토",
            "smoke 통과",
        ],
        "rollback_plan": (
            "5050 route disable flag → False 복귀. "
            "execute() 호출 영향은 별도 executor rollback으로 관리. "
            "router.py 수정 불필요."
        ),
        "risk_level": "MEDIUM",
        "blockers": [
            "execute() 경로 side effect 전체 추적 미완",
            "DB write 영향 분석 미완",
            "unknown caller 4개 마운트 여부 미확인",
            "backend caller 전환 계획 미완",
        ],
        "verdict": "SCHEMA_FREEZE_WITH_WARN",
    },
]


def run_audit():
    errors = []
    warnings = []

    # 1. freeze matrix 기본 검증
    if len(FREEZE_MATRIX) != 2:
        errors.append(f"freeze matrix row count != 2: {len(FREEZE_MATRIX)}")

    paths = [r["legacy_path"] for r in FREEZE_MATRIX]
    if "/api/v1/inbox" not in paths:
        errors.append("GET /api/v1/inbox row missing")
    if "/api/v1/tasks" not in paths:
        errors.append("POST /api/v1/tasks row missing")

    for row in FREEZE_MATRIX:
        if row["overlap_class"] != "SAME_CONTRACT":
            errors.append(f"overlap_class != SAME_CONTRACT: {row['legacy_path']}")
        if not row["disable_candidate"]:
            errors.append(f"disable_candidate not True: {row['legacy_path']}")
        if row["disable_allowed_now"]:
            errors.append(f"disable_allowed_now must be False: {row['legacy_path']}")
        if not row["request_schema_frozen"]:
            errors.append(f"request_schema_frozen must be True: {row['legacy_path']}")
        if not row["response_schema_frozen"]:
            errors.append(f"response_schema_frozen must be True: {row['legacy_path']}")
        if not row.get("request_schema"):
            errors.append(f"request_schema missing: {row['legacy_path']}")
        if not row.get("response_schema"):
            errors.append(f"response_schema missing: {row['legacy_path']}")
        if not row.get("required_before_disable"):
            errors.append(f"required_before_disable missing: {row['legacy_path']}")
        if not row.get("rollback_plan"):
            errors.append(f"rollback_plan missing: {row['legacy_path']}")

    # 2. GET inbox — READ_ONLY, body_required=False
    inbox = next((r for r in FREEZE_MATRIX if r["legacy_path"] == "/api/v1/inbox"), None)
    if inbox:
        if inbox["side_effect_classification"] != "READ_ONLY_EXPECTED":
            errors.append("GET /inbox side_effect != READ_ONLY_EXPECTED")
        if inbox["request_schema"].get("body_required") is not False:
            errors.append("GET /inbox body_required must be False")

    # 3. POST tasks — WRITE_POSSIBLE, side_effect_detail 존재
    tasks = next((r for r in FREEZE_MATRIX if r["legacy_path"] == "/api/v1/tasks"), None)
    if tasks:
        if tasks["side_effect_classification"] != "WRITE_POSSIBLE":
            errors.append("POST /tasks side_effect != WRITE_POSSIBLE")
        if not tasks.get("side_effect_detail"):
            errors.append("POST /tasks side_effect_detail missing")
        if tasks["risk_level"] not in ("MEDIUM", "HIGH"):
            errors.append(f"POST /tasks risk_level must be MEDIUM or HIGH: {tasks['risk_level']}")

    # 4. 전역 금지 상수
    for const_name, val in [
        ("LEGACY_DISABLE_ALLOWED_NOW", LEGACY_DISABLE_ALLOWED_NOW),
        ("ROUTER_FILE_MODIFICATION_ALLOWED", ROUTER_FILE_MODIFICATION_ALLOWED),
        ("SERVER_APPLY_ALLOWED", SERVER_APPLY_ALLOWED),
        ("LIVE_TRAFFIC_ALLOWED", LIVE_TRAFFIC_ALLOWED),
        ("DB_WRITE_ALLOWED", DB_WRITE_ALLOWED),
    ]:
        if val:
            errors.append(f"{const_name} must be False")

    # 5. 제외 대상 확인
    matrix_paths = [r["legacy_path"] for r in FREEZE_MATRIX]
    for excl in ["/execute", "/dashboard", "/webhook"]:
        if any(excl in p for p in matrix_paths):
            errors.append(f"excluded route found in matrix: {excl}")
    adapter_paths = [
        "/api/v1/inbox/email/fetch",
        "/api/v1/tasks/{task_id}/approve",
        "/api/v1/tasks/{task_id}/reject",
    ]
    for ap in adapter_paths:
        if ap in matrix_paths:
            errors.append(f"adapter route in Phase 1-J2 matrix: {ap}")

    # 6. caller inventory 검증
    inv = CALLER_INVENTORY
    real_fe = len(inv.get("real_frontend_callers", []))
    real_be = len(inv.get("real_backend_callers", []))
    real_total = real_fe + real_be
    unknown = len(inv.get("unknown_callers", []))
    if real_total > 0:
        warnings.append(
            f"real callers present (frontend={real_fe}, backend={real_be}) — "
            "schema freeze 완료 후 caller migration 필요"
        )
    if unknown > 0:
        if not inv.get("unknown_warning_reason"):
            errors.append("unknown_callers present but unknown_warning_reason missing")
        else:
            warnings.append(f"unknown callers ({unknown}): {inv['unknown_warning_reason'][:80]}")

    # 7. router.py 추가 수정 없음
    router_content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "PHASE_1J2" in router_content:
        errors.append("router.py contains PHASE_1J2 — router modification detected")

    # 8. SCHEMA_FREEZE_ONLY
    if not SCHEMA_FREEZE_ONLY:
        errors.append("SCHEMA_FREEZE_ONLY must be True")

    # 9. verdict
    row_verdicts = [r.get("verdict") for r in FREEZE_MATRIX]
    any_row_warn = any(v == "SCHEMA_FREEZE_WITH_WARN" for v in row_verdicts)
    has_errors = bool(errors)
    if has_errors:
        verdict = "PHASE1J2_SAME_CONTRACT_RESPONSE_SCHEMA_FREEZE_FAIL"
    elif any_row_warn or warnings:
        verdict = "SCHEMA_FREEZE_WITH_WARN"
    else:
        verdict = "PHASE1J2_SAME_CONTRACT_RESPONSE_SCHEMA_FREEZE_READY"

    return {
        "phase": PHASE,
        "freeze_id": FREEZE_ID,
        "verdict": verdict,
        "legacy_disable_allowed_now": LEGACY_DISABLE_ALLOWED_NOW,
        "router_file_modification_allowed": ROUTER_FILE_MODIFICATION_ALLOWED,
        "server_apply_allowed": SERVER_APPLY_ALLOWED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "db_write_allowed": DB_WRITE_ALLOWED,
        "schema_freeze_only": SCHEMA_FREEZE_ONLY,
        "freeze_matrix": FREEZE_MATRIX,
        "caller_inventory": CALLER_INVENTORY,
        "caller_real_total": real_total,
        "caller_unknown_total": unknown,
        "errors": errors,
        "warnings": warnings,
        "rollback_instructions": [
            "Phase 1-J2는 read-only schema freeze 공정. router.py 수정 없음.",
            "롤백 필요 시: 이 스크립트 파일만 삭제.",
            "Phase 1-R rollback: git revert 847f0ee 또는 git checkout 0d74129 -- ai_orchestrator/router.py",
        ],
    }


if __name__ == "__main__":
    import json
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Phase 1-J2 Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
