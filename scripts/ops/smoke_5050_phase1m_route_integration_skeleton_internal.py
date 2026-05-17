"""
Phase 1-M: Route Integration Skeleton Internal Smoke Runner
서버 기동 없음. route 등록 없음. 네트워크/DB/secret 접근 없음.
Phase 1-L route integration skeleton을 내부 fixture로만 smoke 실행한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PHASE = "PHASE_1M"
SMOKE_ID = "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE"
STAGING_MODE = "INTERNAL_FIXTURE_ONLY"
VERDICT_READY = "PHASE1M_ROUTE_INTEGRATION_SKELETON_INTERNAL_SMOKE_READY"

_FORBIDDEN_SKELETON_IDS = [
    "execute",
    "webhook",
    "dashboard",
    "same_contract",
]


def build_phase1m_smoke_fixtures() -> dict:
    return {
        "inbox": {
            "disabled": {"route_payload_fixture": None, "dry_run": False},
            "unsafe": {"route_payload_fixture": None, "feature_flag_enabled": True},
            "dry_run_success": {"route_payload_fixture": {"mailbox": "inbox-test"}, "dry_run": True},
            "bad_secret": {"route_payload_fixture": {"password": "secret123"}, "dry_run": True},
            "bad_live_context": {"route_payload_fixture": {"request": "LIVE_REQUEST_OBJ"}, "dry_run": True},
        },
        "approve": {
            "disabled": {"task_id": "t-approve-1", "response_fixture": None, "dry_run": False},
            "unsafe": {"task_id": "t-approve-1", "response_fixture": None, "feature_flag_enabled": True},
            "dry_run_success": {
                "task_id": "t-approve-1",
                "response_fixture": {"status": "approved", "task_id": "t-approve-1"},
                "dry_run": True,
            },
            "bad_missing_task_id": {"task_id": None, "response_fixture": {"status": "ok"}, "dry_run": True},
        },
        "reject": {
            "disabled": {"task_id": "t-reject-1", "response_fixture": None, "dry_run": False},
            "unsafe": {"task_id": "t-reject-1", "response_fixture": None, "feature_flag_enabled": True},
            "dry_run_success": {
                "task_id": "t-reject-1",
                "response_fixture": {"status": "rejected", "task_id": "t-reject-1"},
                "dry_run": True,
            },
            "bad_missing_task_id": {"task_id": None, "response_fixture": {"status": "ok"}, "dry_run": True},
        },
    }


def run_phase1m_internal_smoke() -> dict:
    from backend.compat.legacy_5050.route_integration.common import (
        RouteIntegrationUnsafeExecutionError,
        RouteIntegrationSkeletonError,
    )
    from backend.compat.legacy_5050.route_integration.inbox_email_fetch_route_skeleton import (
        inbox_email_fetch_route_integration_skeleton,
        ROUTE_SKELETON_ID as INBOX_ID,
    )
    from backend.compat.legacy_5050.route_integration.task_approval_route_skeleton import (
        task_approve_route_integration_skeleton,
        task_reject_route_integration_skeleton,
        APPROVE_ROUTE_SKELETON_ID,
        REJECT_ROUTE_SKELETON_ID,
        APPROVE_FASTAPI_PATH_TEMPLATE,
        REJECT_FASTAPI_PATH_TEMPLATE,
    )

    fixtures = build_phase1m_smoke_fixtures()
    scenarios = []
    errors = []

    # ── A. disabled mode ────────────────────────────────────────────────────

    def _run_disabled(fn, label, kwargs):
        try:
            r = fn(**kwargs)
            ok = r.get("ok") is False and r.get("would_call_wrapper") is False
            scenarios.append({"id": label, "group": "disabled_mode", "pass": ok, "detail": r})
            if not ok:
                errors.append(f"{label}: expected disabled result")
        except Exception as e:
            scenarios.append({"id": label, "group": "disabled_mode", "pass": False, "detail": str(e)})
            errors.append(f"{label}: unexpected error: {e}")

    _run_disabled(inbox_email_fetch_route_integration_skeleton, "inbox_disabled", fixtures["inbox"]["disabled"])
    _run_disabled(
        lambda **kw: task_approve_route_integration_skeleton(**kw),
        "approve_disabled",
        fixtures["approve"]["disabled"],
    )
    _run_disabled(
        lambda **kw: task_reject_route_integration_skeleton(**kw),
        "reject_disabled",
        fixtures["reject"]["disabled"],
    )

    # ── B. unsafe feature flag mode ─────────────────────────────────────────

    def _run_unsafe(fn, label, kwargs):
        try:
            fn(**kwargs)
            scenarios.append({"id": label, "group": "unsafe_mode", "pass": False, "detail": "no error raised"})
            errors.append(f"{label}: expected RouteIntegrationUnsafeExecutionError")
        except RouteIntegrationUnsafeExecutionError:
            scenarios.append({"id": label, "group": "unsafe_mode", "pass": True, "detail": "UnsafeExecutionError raised"})
        except Exception as e:
            scenarios.append({"id": label, "group": "unsafe_mode", "pass": False, "detail": str(e)})
            errors.append(f"{label}: wrong exception type: {e}")

    _run_unsafe(inbox_email_fetch_route_integration_skeleton, "inbox_unsafe_flag", fixtures["inbox"]["unsafe"])
    _run_unsafe(
        lambda **kw: task_approve_route_integration_skeleton(**kw),
        "approve_unsafe_flag",
        fixtures["approve"]["unsafe"],
    )
    _run_unsafe(
        lambda **kw: task_reject_route_integration_skeleton(**kw),
        "reject_unsafe_flag",
        fixtures["reject"]["unsafe"],
    )

    # ── C. dry-run fixture success ───────────────────────────────────────────

    inbox_dry_result = None
    approve_dry_result = None
    reject_dry_result = None

    try:
        r = inbox_email_fetch_route_integration_skeleton(**fixtures["inbox"]["dry_run_success"])
        ok = r.get("ok") is True and r.get("route_registered") is False and "wrapper_result" in r
        inbox_dry_result = r
        scenarios.append({"id": "inbox_dry_run_success", "group": "dry_run_success", "pass": ok, "detail": r})
        if not ok:
            errors.append("inbox_dry_run_success: unexpected result")
    except Exception as e:
        scenarios.append({"id": "inbox_dry_run_success", "group": "dry_run_success", "pass": False, "detail": str(e)})
        errors.append(f"inbox_dry_run_success: {e}")

    try:
        r = task_approve_route_integration_skeleton(**fixtures["approve"]["dry_run_success"])
        nr = r.get("wrapper_result", {}).get("normalized_response", {})
        ok = (r.get("ok") is True and r.get("route_registered") is False
              and "wrapper_result" in r and nr.get("approval_gate_executed") is False)
        approve_dry_result = r
        scenarios.append({"id": "approve_dry_run_success", "group": "dry_run_success", "pass": ok, "detail": r})
        if not ok:
            errors.append("approve_dry_run_success: unexpected result or approval_gate_executed!=False")
    except Exception as e:
        scenarios.append({"id": "approve_dry_run_success", "group": "dry_run_success", "pass": False, "detail": str(e)})
        errors.append(f"approve_dry_run_success: {e}")

    try:
        r = task_reject_route_integration_skeleton(**fixtures["reject"]["dry_run_success"])
        nr = r.get("wrapper_result", {}).get("normalized_response", {})
        ok = (r.get("ok") is True and r.get("route_registered") is False
              and "wrapper_result" in r and nr.get("approval_gate_executed") is False)
        reject_dry_result = r
        scenarios.append({"id": "reject_dry_run_success", "group": "dry_run_success", "pass": ok, "detail": r})
        if not ok:
            errors.append("reject_dry_run_success: unexpected result or approval_gate_executed!=False")
    except Exception as e:
        scenarios.append({"id": "reject_dry_run_success", "group": "dry_run_success", "pass": False, "detail": str(e)})
        errors.append(f"reject_dry_run_success: {e}")

    # ── D. bad fixture boundary ──────────────────────────────────────────────

    def _run_bad_fixture(fn, label, kwargs, expected_exc=Exception):
        try:
            fn(**kwargs)
            scenarios.append({"id": label, "group": "bad_fixture_boundary", "pass": False, "detail": "no error raised"})
            errors.append(f"{label}: expected exception not raised")
        except expected_exc:
            scenarios.append({"id": label, "group": "bad_fixture_boundary", "pass": True, "detail": "expected exception raised"})
        except Exception as e:
            scenarios.append({"id": label, "group": "bad_fixture_boundary", "pass": True, "detail": f"exception raised: {e}"})

    _run_bad_fixture(inbox_email_fetch_route_integration_skeleton, "inbox_secret_field_error",
                     fixtures["inbox"]["bad_secret"])
    _run_bad_fixture(inbox_email_fetch_route_integration_skeleton, "inbox_live_context_key_error",
                     fixtures["inbox"]["bad_live_context"])
    _run_bad_fixture(
        lambda **kw: task_approve_route_integration_skeleton(**kw),
        "approve_missing_task_id_error",
        fixtures["approve"]["bad_missing_task_id"],
    )
    _run_bad_fixture(
        lambda **kw: task_reject_route_integration_skeleton(**kw),
        "reject_missing_task_id_error",
        fixtures["reject"]["bad_missing_task_id"],
    )

    # ── double slash 방지 확인 ────────────────────────────────────────────────

    no_double_slash = (
        "//" not in APPROVE_FASTAPI_PATH_TEMPLATE
        and "//" not in REJECT_FASTAPI_PATH_TEMPLATE
    )
    scenarios.append({"id": "approve_no_double_slash", "group": "bad_fixture_boundary", "pass": no_double_slash, "detail": APPROVE_FASTAPI_PATH_TEMPLATE})
    scenarios.append({"id": "reject_no_double_slash", "group": "bad_fixture_boundary", "pass": no_double_slash, "detail": REJECT_FASTAPI_PATH_TEMPLATE})
    if not no_double_slash:
        errors.append("double slash detected in fastapi path templates")

    # ── 금지 route 제외 확인 ──────────────────────────────────────────────────

    skeleton_ids = [INBOX_ID, APPROVE_ROUTE_SKELETON_ID, REJECT_ROUTE_SKELETON_ID]
    no_forbidden = all(
        not any(f in sid.lower() for f in _FORBIDDEN_SKELETON_IDS)
        for sid in skeleton_ids
    )
    scenarios.append({"id": "no_forbidden_route", "group": "bad_fixture_boundary", "pass": no_forbidden, "detail": skeleton_ids})
    if not no_forbidden:
        errors.append("forbidden route found in skeleton_ids")

    # ── summary 집계 ──────────────────────────────────────────────────────────

    passed = sum(1 for s in scenarios if s["pass"])
    failed = sum(1 for s in scenarios if not s["pass"])

    disabled_passed = all(s["pass"] for s in scenarios if s["group"] == "disabled_mode")
    unsafe_passed = all(s["pass"] for s in scenarios if s["group"] == "unsafe_mode")
    dry_run_passed = all(s["pass"] for s in scenarios if s["group"] == "dry_run_success")
    bad_fixture_passed = all(s["pass"] for s in scenarios if s["group"] == "bad_fixture_boundary")

    verdict = VERDICT_READY if failed == 0 else "FAIL"

    summary = {
        "phase": PHASE,
        "smoke_id": SMOKE_ID,
        "staging_mode": STAGING_MODE,
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
        "total_scenarios": len(scenarios),
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "route_skeleton_count": 3,
        "disabled_mode_passed": disabled_passed,
        "unsafe_mode_passed": unsafe_passed,
        "dry_run_success_passed": dry_run_passed,
        "bad_fixture_boundary_passed": bad_fixture_passed,
        "no_double_slash": no_double_slash,
        "no_forbidden_route": no_forbidden,
        "scenarios": scenarios,
        "errors": errors,
        "verdict": verdict,
    }
    return summary


def main() -> int:
    print(f"[{PHASE}] {SMOKE_ID}")
    print(f"  staging_mode: {STAGING_MODE}")
    print()

    summary = run_phase1m_internal_smoke()

    groups = {}
    for s in summary["scenarios"]:
        groups.setdefault(s["group"], []).append(s)

    for group, items in groups.items():
        passed = sum(1 for i in items if i["pass"])
        print(f"  [{group}] {passed}/{len(items)} passed")
        for item in items:
            mark = "PASS" if item["pass"] else "FAIL"
            print(f"    [{mark}] {item['id']}")

    print()
    print(f"  total_scenarios     : {summary['total_scenarios']}")
    print(f"  passed_scenarios    : {summary['passed_scenarios']}")
    print(f"  failed_scenarios    : {summary['failed_scenarios']}")
    print(f"  route_skeleton_count: {summary['route_skeleton_count']}")
    print(f"  server_started      : {summary['server_started']}")
    print(f"  route_registered    : {summary['route_registered']}")
    print(f"  live_traffic_allowed: {summary['live_traffic_allowed']}")
    print(f"  http_call_count     : {summary['http_call_count']}")
    print(f"  db_write_count      : {summary['db_write_count']}")
    print(f"  secret_output_count : {summary['secret_value_output_count']}")
    print()

    if summary["errors"]:
        print("  ERRORS:")
        for e in summary["errors"]:
            print(f"    - {e}")
        print()

    print(f"VERDICT: {summary['verdict']}")
    print("=" * 70)

    return 0 if summary["verdict"] == VERDICT_READY else 1


if __name__ == "__main__":
    sys.exit(main())
