"""
Phase 1-M: Route Integration Skeleton Internal Smoke Audit
smoke runner와 skeleton이 안전 경계를 지키는지 정적/동적으로 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PHASE = "PHASE_1M"
VERDICT_READY = "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE_READY"

_SMOKE_FILES = [
    "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py",
]

_AUDIT_SOURCE_FILES = [
    "scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py",
]

_FORBIDDEN_CODE_PATTERNS = [
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
    "app.include_router(",
    "include_router(",
    "uvicorn.run(",
    "gunicorn",
    "os.environ[",
    "import subprocess",
]


def check_files_exist() -> list[str]:
    errors = []
    for f in _SMOKE_FILES:
        if not (REPO_ROOT / f).exists():
            errors.append(f"MISSING: {f}")
    return errors


def run_static_pattern_scan() -> dict:
    results = {"violations": [], "verdict": "PASS"}
    for rel in _AUDIT_SOURCE_FILES:
        fpath = REPO_ROOT / rel
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in _FORBIDDEN_CODE_PATTERNS:
            if pattern in content:
                results["violations"].append({"file": rel, "pattern": pattern})
    if results["violations"]:
        results["verdict"] = "FAIL"
    return results


def run_dynamic_smoke_check() -> dict:
    errors = []
    summary = {}
    try:
        import scripts.ops.smoke_5050_phase1m_route_integration_skeleton_internal as m
        summary = m.run_phase1m_internal_smoke()
    except Exception as e:
        return {"errors": [f"smoke import/run error: {e}"], "summary": {}, "verdict": "FAIL"}

    required_fields = {
        "phase": "PHASE_1M",
        "smoke_id": "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE",
        "staging_mode": "INTERNAL_FIXTURE_ONLY",
        "server_started": False,
        "route_registered": False,
        "route_connected": False,
        "live_traffic_allowed": False,
        "http_call_count": 0,
        "db_read_count": 0,
        "db_write_count": 0,
        "secret_value_output_count": 0,
        "email_fetch_live_call_count": 0,
        "approve_live_call_count": 0,
        "reject_live_call_count": 0,
        "execute_call_count": 0,
        "webhook_call_count": 0,
        "route_skeleton_count": 3,
        "disabled_mode_passed": True,
        "unsafe_mode_passed": True,
        "dry_run_success_passed": True,
        "bad_fixture_boundary_passed": True,
        "no_double_slash": True,
        "no_forbidden_route": True,
    }

    for field, expected in required_fields.items():
        actual = summary.get(field)
        if actual != expected:
            errors.append(f"summary.{field}: expected={expected!r} actual={actual!r}")

    if summary.get("total_scenarios", 0) < 15:
        errors.append(f"total_scenarios < 15: got {summary.get('total_scenarios')}")
    if summary.get("failed_scenarios", 1) != 0:
        errors.append(f"failed_scenarios != 0: got {summary.get('failed_scenarios')}")

    verdict_ok = summary.get("verdict") == VERDICT_READY
    if not verdict_ok:
        errors.append(f"verdict mismatch: {summary.get('verdict')}")

    return {
        "errors": errors,
        "summary": summary,
        "verdict": "PASS" if not errors else "FAIL",
    }


def get_overall_verdict(file_errors, static_scan, dynamic) -> str:
    if file_errors or static_scan["verdict"] == "FAIL" or dynamic["verdict"] == "FAIL":
        return "FAIL"
    return VERDICT_READY


def main():
    print(f"[{PHASE}] ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE AUDIT")
    print()

    file_errors = check_files_exist()
    print(f"[files] {'PASS' if not file_errors else 'FAIL'}")
    for e in file_errors:
        print(f"  {e}")

    static_scan = run_static_pattern_scan()
    print(f"[static_scan] violations={len(static_scan['violations'])} verdict={static_scan['verdict']}")
    for v in static_scan["violations"]:
        print(f"  VIOLATION: {v['file']} pattern={v['pattern']}")

    dynamic = run_dynamic_smoke_check()
    s = dynamic.get("summary", {})
    print(f"[dynamic] total={s.get('total_scenarios')} passed={s.get('passed_scenarios')} failed={s.get('failed_scenarios')} verdict={dynamic['verdict']}")
    for e in dynamic["errors"]:
        print(f"  ERROR: {e}")

    verdict = get_overall_verdict(file_errors, static_scan, dynamic)
    print()
    print(f"VERDICT: {verdict}")
    print("=" * 70)

    if verdict != VERDICT_READY:
        sys.exit(1)


if __name__ == "__main__":
    main()
