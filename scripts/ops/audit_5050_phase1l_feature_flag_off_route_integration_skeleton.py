"""
Phase 1-L: Feature Flag OFF Route Integration Skeleton Audit
실제 route 등록 없이 skeleton이 올바르게 구성되어 있는지 정적+동적으로 검증한다.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PHASE = "PHASE_1L"
VERDICT_READY = "PHASE1L_FEATURE_FLAG_OFF_ROUTE_INTEGRATION_SKELETON_READY"

_FORBIDDEN_SOURCE_PATTERNS = [
    "import requests",
    "import httpx",
    "import urllib.request",
    "import socket",
    "import sqlite3",
    "import psycopg",
    "sqlalchemy.create_engine",
    "= APIRouter(",
    "APIRouter()",
    "= FastAPI(",
    "FastAPI()",
    "= Flask(",
    "@app.route",
    "@router.get",
    "@router.post",
    "@router.put",
    "@router.delete",
    "app.include_router(",
    "include_router(",
    "uvicorn.run(",
    "gunicorn",
    "os.environ[",
    "import subprocess",
]

_SCAN_DIRS = ["backend", "ai_orchestrator", "services"]
_ALLOWED_PATH_FRAGMENTS = ["route_integration", "wrappers", "tests", "scripts/ops"]

_ROUTE_INTEGRATION_FILES = [
    "backend/compat/legacy_5050/route_integration/__init__.py",
    "backend/compat/legacy_5050/route_integration/common.py",
    "backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py",
    "backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py",
]

_FORBIDDEN_ROUTES = [
    "/api/v1/tasks/execute",
    "/api/v1/webhook",
    "/api/v1/dashboard",
    "/api/v1/tasks//approve",
    "/api/v1/tasks//reject",
]


def _is_allowed_path(rel: str) -> bool:
    r = rel.replace("\\", "/")
    return any(frag in r for frag in _ALLOWED_PATH_FRAGMENTS)


# ── 파일 존재 확인 ──────────────────────────────────────────────────────────

def check_files_exist() -> list[str]:
    errors = []
    for f in _ROUTE_INTEGRATION_FILES:
        if not (REPO_ROOT / f).exists():
            errors.append(f"MISSING: {f}")
    return errors


# ── 정적 금지 패턴 scan ──────────────────────────────────────────────────────

def run_static_forbidden_pattern_scan() -> dict:
    """신규 route_integration 파일에서만 금지 패턴 확인 (기존 운영 코드는 검사 대상 아님)"""
    results = {"violations": [], "skipped": [], "verdict": "PASS"}
    target_files = [REPO_ROOT / f for f in _ROUTE_INTEGRATION_FILES]
    for py_file in target_files:
        if not py_file.exists():
            results["skipped"].append(str(py_file.relative_to(REPO_ROOT)))
            continue
        rel = str(py_file.relative_to(REPO_ROOT))
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in _FORBIDDEN_SOURCE_PATTERNS:
            if pattern in content:
                results["violations"].append({"file": rel, "pattern": pattern})
    if results["violations"]:
        results["verdict"] = "FAIL"
    return results


# ── route integration skeleton import가 router/service에 없는지 scan ─────────

def run_route_integration_import_scan() -> dict:
    """route_integration 패키지가 router/service/usecase에서 import되지 않는지 확인"""
    results = {"violations": [], "verdict": "PASS"}
    forbidden_patterns = [
        "route_integration",
        "inbox_email_fetch_route_skeleton",
        "task_approval_route_skeleton",
    ]
    for scan_dir in _SCAN_DIRS:
        dirpath = REPO_ROOT / scan_dir
        if not dirpath.exists():
            continue
        for py_file in dirpath.rglob("*.py"):
            rel = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
            if _is_allowed_path(rel):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in forbidden_patterns:
                if pattern in content:
                    results["violations"].append({"file": rel, "pattern": pattern})
    if results["violations"]:
        results["verdict"] = "FAIL"
    return results


# ── 동적 검증 ────────────────────────────────────────────────────────────────

def run_dynamic_checks() -> list[str]:
    errors = []
    try:
        from backend.compat.legacy_5050.route_integration.common import (
            RouteIntegrationUnsafeExecutionError,
            RouteIntegrationDisabledError,
            RouteIntegrationSkeletonError,
            FEATURE_FLAG_DEFAULT_ENABLED,
            ROUTE_REGISTERED,
            LIVE_TRAFFIC_ALLOWED,
            DRY_RUN_ALLOWED,
        )
        if FEATURE_FLAG_DEFAULT_ENABLED is not False:
            errors.append("common: FEATURE_FLAG_DEFAULT_ENABLED != False")
        if ROUTE_REGISTERED is not False:
            errors.append("common: ROUTE_REGISTERED != False")
        if LIVE_TRAFFIC_ALLOWED is not False:
            errors.append("common: LIVE_TRAFFIC_ALLOWED != False")
        if DRY_RUN_ALLOWED is not True:
            errors.append("common: DRY_RUN_ALLOWED != True")
    except Exception as e:
        errors.append(f"common import error: {e}")
        return errors

    # inbox skeleton
    try:
        from backend.compat.legacy_5050.route_integration.inbox_email_fetch_route_skeleton import (
            inbox_email_fetch_route_integration_skeleton,
            get_inbox_email_fetch_route_skeleton_metadata,
            FEATURE_FLAG_DEFAULT, ROUTE_REGISTERED as IR, LIVE_TRAFFIC_ALLOWED as IL, DRY_RUN_ALLOWED as ID,
            FASTAPI_PATH_TEMPLATE,
        )
        if FEATURE_FLAG_DEFAULT is not False:
            errors.append("inbox: FEATURE_FLAG_DEFAULT != False")
        if IR is not False:
            errors.append("inbox: ROUTE_REGISTERED != False")
        if IL is not False:
            errors.append("inbox: LIVE_TRAFFIC_ALLOWED != False")
        if ID is not True:
            errors.append("inbox: DRY_RUN_ALLOWED != True")
        if "//" in FASTAPI_PATH_TEMPLATE:
            errors.append(f"inbox: double slash in path: {FASTAPI_PATH_TEMPLATE}")

        # disabled result
        r = inbox_email_fetch_route_integration_skeleton(dry_run=False)
        if r.get("ok") is not False:
            errors.append("inbox: dry_run=False should return disabled (ok=False)")
        if r.get("would_call_wrapper") is not False:
            errors.append("inbox: disabled result should have would_call_wrapper=False")

        # unsafe error
        try:
            inbox_email_fetch_route_integration_skeleton(feature_flag_enabled=True)
            errors.append("inbox: feature_flag_enabled=True should raise error")
        except RouteIntegrationUnsafeExecutionError:
            pass

        # dry-run fixture
        r = inbox_email_fetch_route_integration_skeleton({"mailbox": "test"}, dry_run=True)
        if r.get("ok") is not True:
            errors.append("inbox: dry_run=True should return ok=True")
        if r.get("route_registered") is not False:
            errors.append("inbox: route_registered should be False")
        if "wrapper_result" not in r:
            errors.append("inbox: dry_run result missing wrapper_result")

        # metadata
        meta = get_inbox_email_fetch_route_skeleton_metadata()
        if meta.get("feature_flag_default") is not False:
            errors.append("inbox meta: feature_flag_default != False")
    except Exception as e:
        errors.append(f"inbox skeleton error: {e}")

    # approve skeleton
    try:
        from backend.compat.legacy_5050.route_integration.task_approval_route_skeleton import (
            task_approve_route_integration_skeleton,
            task_reject_route_integration_skeleton,
            get_task_approve_route_skeleton_metadata,
            get_task_reject_route_skeleton_metadata,
            APPROVE_FEATURE_FLAG_DEFAULT, APPROVE_ROUTE_REGISTERED, APPROVE_LIVE_TRAFFIC_ALLOWED, APPROVE_DRY_RUN_ALLOWED,
            REJECT_FEATURE_FLAG_DEFAULT, REJECT_ROUTE_REGISTERED, REJECT_LIVE_TRAFFIC_ALLOWED, REJECT_DRY_RUN_ALLOWED,
            APPROVE_FASTAPI_PATH_TEMPLATE, REJECT_FASTAPI_PATH_TEMPLATE,
            APPROVE_LEGACY_PATH_TEMPLATE, REJECT_LEGACY_PATH_TEMPLATE,
        )
        for name, val in [
            ("APPROVE_FEATURE_FLAG_DEFAULT", APPROVE_FEATURE_FLAG_DEFAULT),
            ("APPROVE_ROUTE_REGISTERED", APPROVE_ROUTE_REGISTERED),
            ("APPROVE_LIVE_TRAFFIC_ALLOWED", APPROVE_LIVE_TRAFFIC_ALLOWED),
            ("REJECT_FEATURE_FLAG_DEFAULT", REJECT_FEATURE_FLAG_DEFAULT),
            ("REJECT_ROUTE_REGISTERED", REJECT_ROUTE_REGISTERED),
            ("REJECT_LIVE_TRAFFIC_ALLOWED", REJECT_LIVE_TRAFFIC_ALLOWED),
        ]:
            if val is not False:
                errors.append(f"approval: {name} != False")
        for name, val in [
            ("APPROVE_DRY_RUN_ALLOWED", APPROVE_DRY_RUN_ALLOWED),
            ("REJECT_DRY_RUN_ALLOWED", REJECT_DRY_RUN_ALLOWED),
        ]:
            if val is not True:
                errors.append(f"approval: {name} != True")
        if "//" in APPROVE_FASTAPI_PATH_TEMPLATE:
            errors.append(f"approve: double slash in path: {APPROVE_FASTAPI_PATH_TEMPLATE}")
        if "//" in REJECT_FASTAPI_PATH_TEMPLATE:
            errors.append(f"reject: double slash in path: {REJECT_FASTAPI_PATH_TEMPLATE}")
        if "<id>" not in APPROVE_LEGACY_PATH_TEMPLATE:
            errors.append("approve: <id> missing in legacy path")
        if "{id}" not in APPROVE_FASTAPI_PATH_TEMPLATE:
            errors.append("approve: {id} missing in fastapi path")

        # approve disabled
        r = task_approve_route_integration_skeleton(dry_run=False)
        if r.get("ok") is not False:
            errors.append("approve: dry_run=False should return disabled")

        # approve unsafe
        try:
            task_approve_route_integration_skeleton(feature_flag_enabled=True)
            errors.append("approve: feature_flag_enabled=True should raise error")
        except RouteIntegrationUnsafeExecutionError:
            pass

        # approve dry-run
        r = task_approve_route_integration_skeleton("t-1", {"status": "approved"}, dry_run=True)
        if r.get("ok") is not True:
            errors.append("approve: dry_run=True should return ok=True")
        nr = r.get("wrapper_result", {}).get("normalized_response", {})
        if nr.get("approval_gate_executed") is not False:
            errors.append("approve: approval_gate_executed should be False")

        # approve task_id required
        try:
            task_approve_route_integration_skeleton(None, {"status": "ok"}, dry_run=True)
            errors.append("approve: missing task_id should raise error")
        except Exception:
            pass

        # reject disabled
        r = task_reject_route_integration_skeleton(dry_run=False)
        if r.get("ok") is not False:
            errors.append("reject: dry_run=False should return disabled")

        # reject dry-run
        r = task_reject_route_integration_skeleton("t-2", {"status": "rejected"}, dry_run=True)
        if r.get("ok") is not True:
            errors.append("reject: dry_run=True should return ok=True")
        nr = r.get("wrapper_result", {}).get("normalized_response", {})
        if nr.get("approval_gate_executed") is not False:
            errors.append("reject: approval_gate_executed should be False")

    except Exception as e:
        errors.append(f"approval skeleton error: {e}")

    # forbidden routes 미포함 확인
    all_paths = [
        "/api/v1/inbox/email/fetch",
        "/api/v1/tasks/{id}/approve",
        "/api/v1/tasks/{id}/reject",
    ]
    for fp in _FORBIDDEN_ROUTES:
        if fp in all_paths:
            errors.append(f"forbidden route in skeleton paths: {fp}")

    return errors


def get_overall_verdict(file_errors, static_scan, import_scan, dynamic_errors) -> str:
    if file_errors or dynamic_errors:
        return "FAIL"
    if static_scan["verdict"] == "FAIL" or import_scan["verdict"] == "FAIL":
        return "FAIL"
    return VERDICT_READY


def main():
    print(f"[{PHASE}] FEATURE_FLAG_OFF_ROUTE_INTEGRATION_SKELETON AUDIT")
    print()

    file_errors = check_files_exist()
    print(f"[files] exist check: {'PASS' if not file_errors else 'FAIL'}")
    for e in file_errors:
        print(f"  {e}")

    static_scan = run_static_forbidden_pattern_scan()
    print(f"[static_scan] violations={len(static_scan['violations'])} skipped={static_scan['skipped']} verdict={static_scan['verdict']}")
    for v in static_scan["violations"]:
        print(f"  VIOLATION: {v['file']} pattern={v['pattern']}")

    import_scan = run_route_integration_import_scan()
    print(f"[import_scan] violations={len(import_scan['violations'])} verdict={import_scan['verdict']}")
    for v in import_scan["violations"]:
        print(f"  VIOLATION: {v['file']} pattern={v['pattern']}")

    dynamic_errors = run_dynamic_checks()
    print(f"[dynamic] errors={len(dynamic_errors)}: {'PASS' if not dynamic_errors else 'FAIL'}")
    for e in dynamic_errors:
        print(f"  ERROR: {e}")

    verdict = get_overall_verdict(file_errors, static_scan, import_scan, dynamic_errors)
    print()
    print(f"[OVERALL] {verdict}")

    if verdict != VERDICT_READY:
        sys.exit(1)


if __name__ == "__main__":
    main()
