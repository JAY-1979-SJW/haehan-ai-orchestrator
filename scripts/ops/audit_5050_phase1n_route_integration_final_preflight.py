"""Phase 1-N: Route Integration Final Preflight Before Real Router Touch.

[ASSISTANT_BACKEND_5050_LEGACY_PHASE1N_ROUTE_INTEGRATION_FINAL_PREFLIGHT_BEFORE_REAL_ROUTER_TOUCH_01]

실제 router touch 전 최종 감리표.
route 등록 없음. APIRouter 없음. include_router 없음. 서버 반영 없음.
HTTP/DB/secret/env 접근 없음.

성공 verdict: PHASE1N_ROUTE_INTEGRATION_FINAL_PREFLIGHT_READY
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PHASE = "PHASE_1N"
PREFLIGHT_ID = "PHASE1N_ROUTE_INTEGRATION_FINAL_PREFLIGHT_BEFORE_REAL_ROUTER_TOUCH"
VERDICT_READY = "PHASE1N_ROUTE_INTEGRATION_FINAL_PREFLIGHT_READY"

# ── 전역 안전 상수 ────────────────────────────────────────────────────────────

REAL_ROUTER_TOUCH_ALLOWED            = False
ROUTE_REGISTRATION_ALLOWED           = False
APIROUTER_ALLOWED                    = False
INCLUDE_ROUTER_ALLOWED               = False
ROUTE_DECORATOR_ALLOWED              = False
FEATURE_FLAG_RUNTIME_HOOK_ALLOWED    = False
LIVE_TRAFFIC_ALLOWED                 = False
DRY_RUN_ONLY                         = True
SERVER_APPLY_ALLOWED                 = False

# ── 금지 route ────────────────────────────────────────────────────────────────

FORBIDDEN_ROUTES = ("execute", "webhook", "dashboard", "same_contract")

# ── final preflight matrix ────────────────────────────────────────────────────

FINAL_PREFLIGHT_MATRIX: tuple[dict, ...] = (

    # ── A. INBOX_EMAIL_FETCH ──────────────────────────────────────────────────
    {
        "phase": PHASE,
        "final_preflight_id": PREFLIGHT_ID,
        "route_skeleton_id": "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "INBOX_EMAIL_FETCH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/inbox/email/fetch",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/inbox/email/fetch",
        "route_skeleton_module": "backend.compat.legacy_5050.route_integration.inbox_email_fetch_route_skeleton",
        "route_skeleton_function": "inbox_email_fetch_route_integration_skeleton",
        "proposed_future_router_search_scope": ("ai_orchestrator", "backend"),
        "proposed_future_router_file_candidates": (
            "ai_orchestrator/",
            "backend/",
        ),
        "proposed_future_integration_boundary": "BEFORE_EMAIL_FETCH_HANDLER_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_registered_now": False,
        "real_router_touch_allowed_now": False,
        "include_router_allowed_now": False,
        "route_decorator_allowed_now": False,
        "feature_flag_runtime_hook_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": False,
        "approval_gate_executed_allowed": False,
        "required_before_real_router_touch": (
            "Phase 1-N preflight 통과",
            "feature flag default false 확인",
            "wrapper dry-run smoke 통과",
            "actual email fetch 코드 경로 분리 확인",
        ),
        "required_after_real_router_touch": (
            "feature flag integration test",
            "route 등록 후 disabled state smoke",
        ),
        "stop_conditions": (
            "route decorator 생성 시 STOP",
            "include_router 생성 시 STOP",
            "feature flag default true 발견 시 STOP",
            "HTTP client import 발생 시 STOP",
            "DB client import 발생 시 STOP",
            "DB write 발생 시 STOP",
            "secret/env value 접근 발생 시 STOP",
            "actual email fetch 발생 시 STOP",
            "external site cookie 저장 발생 시 STOP",
        ),
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": (
            "5050 Flask route 파일",
            "8400 FastAPI handler 파일",
            "executor",
            "webhook handler",
        ),
        "next_phase": "PHASE_1O_OR_PHASE_1J_AFTER_FINAL_PREFLIGHT",
        "verdict": "FINAL_PREFLIGHT_READY",
    },

    # ── B. TASK_APPROVE ───────────────────────────────────────────────────────
    {
        "phase": PHASE,
        "final_preflight_id": PREFLIGHT_ID,
        "route_skeleton_id": "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_APPROVE_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/approve",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/approve",
        "route_skeleton_module": "backend.compat.legacy_5050.route_integration.task_approval_route_skeleton",
        "route_skeleton_function": "task_approve_route_integration_skeleton",
        "proposed_future_router_search_scope": ("ai_orchestrator", "backend"),
        "proposed_future_router_file_candidates": (
            "ai_orchestrator/",
            "backend/",
        ),
        "proposed_future_integration_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_registered_now": False,
        "real_router_touch_allowed_now": False,
        "include_router_allowed_now": False,
        "route_decorator_allowed_now": False,
        "feature_flag_runtime_hook_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": True,
        "approval_gate_executed_allowed": False,
        "required_before_real_router_touch": (
            "Phase 1-N preflight 통과",
            "feature flag default false 확인",
            "wrapper dry-run smoke 통과",
            "approval gate executed=false 원칙 유지 확인",
            "double slash 경로 없음 확인",
        ),
        "required_after_real_router_touch": (
            "feature flag integration test",
            "approval gate disabled smoke",
        ),
        "stop_conditions": (
            "route decorator 생성 시 STOP",
            "include_router 생성 시 STOP",
            "feature flag default true 발견 시 STOP",
            "approval gate executed true 발생 시 STOP",
            "actual approve 발생 시 STOP",
            "DB write 발생 시 STOP",
            "secret/env value 접근 발생 시 STOP",
            "double slash 생성 시 STOP",
            "/execute boundary 침범 시 STOP",
            "external site approval gate 위반 시 STOP",
        ),
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": (
            "5050 Flask route 파일",
            "8400 FastAPI handler 파일",
            "executor",
            "webhook handler",
        ),
        "next_phase": "PHASE_1O_OR_PHASE_1J_AFTER_FINAL_PREFLIGHT",
        "verdict": "FINAL_PREFLIGHT_READY",
    },

    # ── C. TASK_REJECT ────────────────────────────────────────────────────────
    {
        "phase": PHASE,
        "final_preflight_id": PREFLIGHT_ID,
        "route_skeleton_id": "TASK_REJECT_ROUTE_INTEGRATION_SKELETON",
        "wrapper_id": "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE",
        "adapter_id": "TASK_REJECT_PATH_AUTH_ADAPTER",
        "legacy_method": "POST",
        "legacy_path_template": "/api/v1/tasks/<id>/reject",
        "fastapi_method": "POST",
        "fastapi_path_template": "/api/v1/tasks/{id}/reject",
        "route_skeleton_module": "backend.compat.legacy_5050.route_integration.task_approval_route_skeleton",
        "route_skeleton_function": "task_reject_route_integration_skeleton",
        "proposed_future_router_search_scope": ("ai_orchestrator", "backend"),
        "proposed_future_router_file_candidates": (
            "ai_orchestrator/",
            "backend/",
        ),
        "proposed_future_integration_boundary": "BEFORE_APPROVAL_SERVICE_BOUNDARY",
        "feature_flag": "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED",
        "feature_flag_default": False,
        "route_registered_now": False,
        "real_router_touch_allowed_now": False,
        "include_router_allowed_now": False,
        "route_decorator_allowed_now": False,
        "feature_flag_runtime_hook_allowed_now": False,
        "live_traffic_allowed_now": False,
        "dry_run_only_now": True,
        "approval_gate_required": True,
        "approval_gate_executed_allowed": False,
        "required_before_real_router_touch": (
            "Phase 1-N preflight 통과",
            "feature flag default false 확인",
            "wrapper dry-run smoke 통과",
            "approval gate executed=false 원칙 유지 확인",
            "double slash 경로 없음 확인",
        ),
        "required_after_real_router_touch": (
            "feature flag integration test",
            "approval gate disabled smoke",
        ),
        "stop_conditions": (
            "route decorator 생성 시 STOP",
            "include_router 생성 시 STOP",
            "feature flag default true 발견 시 STOP",
            "approval gate executed true 발생 시 STOP",
            "actual reject 발생 시 STOP",
            "DB write 발생 시 STOP",
            "secret/env value 접근 발생 시 STOP",
            "double slash 생성 시 STOP",
            "/execute boundary 침범 시 STOP",
            "external site approval gate 위반 시 STOP",
        ),
        "forbidden_routes": FORBIDDEN_ROUTES,
        "forbidden_files": (
            "5050 Flask route 파일",
            "8400 FastAPI handler 파일",
            "executor",
            "webhook handler",
        ),
        "next_phase": "PHASE_1O_OR_PHASE_1J_AFTER_FINAL_PREFLIGHT",
        "verdict": "FINAL_PREFLIGHT_READY",
    },
)


# ── router 후보 정적 스캔 ─────────────────────────────────────────────────────

_ROUTER_SEARCH_PATTERNS = [
    "APIRouter", "FastAPI", "Flask",
    "@router.", "@app.route", "include_router",
    "/api/v1/inbox", "/api/v1/tasks",
    "approve", "reject", "email/fetch",
]

_ROUTER_SEARCH_DIRS = ["ai_orchestrator", "backend"]

_SCAN_EXCLUDE_DIRS = {
    "route_integration", "__pycache__", ".venv", "venv",
    "wrappers", "adapters",
}


def scan_router_candidates() -> dict:
    candidates = []
    for search_dir in _ROUTER_SEARCH_DIRS:
        target = REPO_ROOT / search_dir
        if not target.exists():
            continue
        for py_file in target.rglob("*.py"):
            if any(excl in py_file.parts for excl in _SCAN_EXCLUDE_DIRS):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            matched = [p for p in _ROUTER_SEARCH_PATTERNS if p in content]
            if matched:
                candidates.append({
                    "file": str(py_file.relative_to(REPO_ROOT)),
                    "matched_patterns": matched,
                    "modified": False,
                    "wrapper_imported": False,
                    "route_integration_imported": False,
                })
    return {
        "search_dirs": _ROUTER_SEARCH_DIRS,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "scan_readonly": True,
        "files_modified": False,
    }


# ── 정적 검사 ─────────────────────────────────────────────────────────────────

_AUDIT_SOURCE_FILES = [
    "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py",
    "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
    "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
    "backend/compat/legacy_5050/route_integration/common.py",
]

_FORBIDDEN_CODE_PATTERNS = [
    "import requests", "import httpx", "import urllib.request",
    "import socket", "import sqlite3", "import psycopg",
    "sqlalchemy.create_engine",
    "= APIRouter(", "APIRouter()",
    "= FastAPI(", "FastAPI()",
    "= Flask(", "@app.route",
    "@router.get", "@router.post",
    "app.include_router(", "include_router(",
    "uvicorn.run(", "gunicorn",
    "os.environ[", "import subprocess",
]


def run_static_pattern_scan() -> dict:
    violations = []
    for rel in _AUDIT_SOURCE_FILES:
        fpath = REPO_ROOT / rel
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        for pattern in _FORBIDDEN_CODE_PATTERNS:
            if pattern in content:
                violations.append({"file": rel, "pattern": pattern})
    return {"violations": violations, "verdict": "PASS" if not violations else "FAIL"}


def check_phase1m_smoke_ready() -> list[str]:
    errors = []
    try:
        import scripts.ops.smoke_5050_phase1m_route_integration_skeleton_internal as m
        summary = m.run_phase1m_internal_smoke()
        if summary.get("failed_scenarios", 1) != 0:
            errors.append(f"Phase 1-M smoke failed_scenarios={summary.get('failed_scenarios')}")
        if summary.get("verdict") != "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE_READY":
            errors.append(f"Phase 1-M smoke verdict={summary.get('verdict')}")
    except Exception as e:
        errors.append(f"Phase 1-M smoke import/run error: {e}")
    return errors


def check_external_site_registry() -> list[str]:
    errors = []
    try:
        from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY
        for p in PROVIDER_REGISTRY:
            if p.cookie_storage_allowed:
                errors.append(f"{p.provider_id}: cookie_storage_allowed=True 위반")
            if p.server_remote_login_allowed:
                errors.append(f"{p.provider_id}: server_remote_login_allowed=True 위반")
        from ai_orchestrator.external_sites.approval_gate_registry import assert_all_critical_gates_blocked
        errors += assert_all_critical_gates_blocked()
    except Exception as e:
        errors.append(f"external site registry 검사 오류: {e}")
    return errors


def check_matrix_integrity() -> list[str]:
    errors = []
    if len(FINAL_PREFLIGHT_MATRIX) != 3:
        errors.append(f"preflight row 수 불일치: {len(FINAL_PREFLIGHT_MATRIX)} != 3")
    for row in FINAL_PREFLIGHT_MATRIX:
        for forbidden in FORBIDDEN_ROUTES:
            sid = row.get("route_skeleton_id", "").lower()
            if forbidden in sid:
                errors.append(f"금지 route 포함: {sid}")
        if row.get("feature_flag_default") is not False:
            errors.append(f"{row.get('route_skeleton_id')}: feature_flag_default != False")
        if row.get("real_router_touch_allowed_now") is not False:
            errors.append(f"{row.get('route_skeleton_id')}: real_router_touch_allowed_now != False")
        if row.get("approval_gate_executed_allowed") is not False:
            errors.append(f"{row.get('route_skeleton_id')}: approval_gate_executed_allowed != False")
        if "//" in row.get("fastapi_path_template", ""):
            errors.append(f"{row.get('route_skeleton_id')}: double slash in fastapi path")
        if "//" in row.get("legacy_path_template", ""):
            errors.append(f"{row.get('route_skeleton_id')}: double slash in legacy path")
    return errors


def get_overall_verdict(file_errors, static_scan, matrix_errors, phase1m_errors, ext_errors) -> str:
    if (file_errors or static_scan["verdict"] == "FAIL"
            or matrix_errors or phase1m_errors or ext_errors):
        return "FAIL"
    return VERDICT_READY


def main():
    print(f"[{PHASE}] {PREFLIGHT_ID}")
    print(f"  REAL_ROUTER_TOUCH_ALLOWED: {REAL_ROUTER_TOUCH_ALLOWED}")
    print(f"  ROUTE_REGISTRATION_ALLOWED: {ROUTE_REGISTRATION_ALLOWED}")
    print(f"  DRY_RUN_ONLY: {DRY_RUN_ONLY}")
    print()

    # 1. matrix 정합성
    matrix_errors = check_matrix_integrity()
    print(f"[matrix_integrity]   {'PASS' if not matrix_errors else 'FAIL'}")
    for e in matrix_errors:
        print(f"  ERROR: {e}")

    # 2. 정적 패턴 스캔
    static_scan = run_static_pattern_scan()
    print(f"[static_scan]        violations={len(static_scan['violations'])} verdict={static_scan['verdict']}")
    for v in static_scan["violations"]:
        print(f"  VIOLATION: {v['file']} pattern={v['pattern']}")

    # 3. router 후보 스캔 (read-only)
    scan = scan_router_candidates()
    print(f"[router_candidates]  count={scan['candidate_count']} readonly={scan['scan_readonly']}")

    # 4. Phase 1-M smoke 유지
    phase1m_errors = check_phase1m_smoke_ready()
    print(f"[phase1m_smoke]      {'PASS' if not phase1m_errors else 'FAIL'}")
    for e in phase1m_errors:
        print(f"  ERROR: {e}")

    # 5. external site registry 정책 확인
    ext_errors = check_external_site_registry()
    print(f"[external_site]      {'PASS' if not ext_errors else 'FAIL'}")
    for e in ext_errors:
        print(f"  ERROR: {e}")

    verdict = get_overall_verdict([], static_scan, matrix_errors, phase1m_errors, ext_errors)

    print()
    print(f"  preflight rows: {len(FINAL_PREFLIGHT_MATRIX)}")
    for row in FINAL_PREFLIGHT_MATRIX:
        print(f"  [{row['route_skeleton_id']}]")
        print(f"    real_router_touch_allowed_now: {row['real_router_touch_allowed_now']}")
        print(f"    feature_flag_default: {row['feature_flag_default']}")
        print(f"    approval_gate_executed_allowed: {row['approval_gate_executed_allowed']}")
        print(f"    verdict: {row['verdict']}")

    print()
    print(f"VERDICT: {verdict}")
    print("=" * 70)

    if verdict != VERDICT_READY:
        sys.exit(1)


if __name__ == "__main__":
    main()
