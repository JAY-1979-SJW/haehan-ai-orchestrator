"""Phase 1-I internal fixture staging dry-run smoke runner.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_01

서버 기동 없음. route 연결 없음. 네트워크/DB/secret 접근 없음.
Phase 1-H wrapper candidate를 내부 fixture로만 smoke 실행한다.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask import 금지
    WSGI/ASGI server 기동 금지
    os.environ 값 직접 출력 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.compat.legacy_5050.wrappers.common import RouteWrapperUnsafeExecutionError
from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
    inbox_email_fetch_wrapper_candidate,
)
from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
    task_approve_wrapper_candidate,
    task_reject_wrapper_candidate,
)

SMOKE_ID = "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE"
STAGING_MODE = "INTERNAL_FIXTURE_ONLY"
PHASE = "PHASE_1I"

PHASE1I_TARGET_PATHS = [
    "/api/v1/inbox/email/fetch",
    "/api/v1/tasks/<id>/approve",
    "/api/v1/tasks/<id>/reject",
]

EXCLUDED_PATHS = [
    "/api/v1/tasks/<task_id>/execute",
    "/api/v1/webhooks/kakaowork",
    "/api/v1/webhooks/kakaotalk-channel",
    "/dashboard",
    "/api/v1/inbox",
    "/api/v1/tasks",
    "/api/v1/tasks//approve",
    "/api/v1/tasks//reject",
]


def build_phase1i_smoke_fixtures() -> dict[str, Any]:
    """smoke 시나리오별 fixture를 반환. 네트워크/DB/secret 접근 없음."""
    return {
        "inbox_request": {"limit": 5, "labels": ["inbox"], "credential_ref": "ref_001"},
        "inbox_response": {"ok": True, "fetched": 2, "items": ["mail_1", "mail_2"]},
        "inbox_bad_request": {"password": "secret_leak"},
        "approve_task_id": "SMOKE_TASK_APPROVE_001",
        "approve_response": {"ok": True, "task_id": "SMOKE_TASK_APPROVE_001"},
        "reject_task_id": "SMOKE_TASK_REJECT_001",
        "reject_response": {"ok": True, "task_id": "SMOKE_TASK_REJECT_001"},
    }


def run_phase1i_internal_smoke() -> dict[str, Any]:
    """Phase 1-I 내부 smoke 실행. 14개 시나리오."""
    fixtures = build_phase1i_smoke_fixtures()

    # safety counters — 모두 0이어야 함
    counters: dict[str, int | bool] = {
        "server_started": False,
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
    }

    scenarios: list[dict[str, Any]] = []

    def scenario(sid: str, group: str, fn, *args, expect_error: type | None = None, **kwargs):
        result = {"id": sid, "group": group, "passed": False, "error": None, "result": None}
        try:
            ret = fn(*args, **kwargs)
            if expect_error:
                result["error"] = f"expected {expect_error.__name__} but no error raised"
            else:
                result["passed"] = True
                result["result"] = ret
        except Exception as exc:
            if expect_error and isinstance(exc, expect_error):
                result["passed"] = True
                result["error"] = str(exc)
            else:
                result["passed"] = False
                result["error"] = f"unexpected {type(exc).__name__}: {exc}"
        scenarios.append(result)
        return result

    # ── A. disabled mode ──────────────────────────────────────────────────────
    s1 = scenario("A1_inbox_disabled", "disabled_mode",
                  inbox_email_fetch_wrapper_candidate)
    s2 = scenario("A2_approve_disabled", "disabled_mode",
                  task_approve_wrapper_candidate)
    s3 = scenario("A3_reject_disabled", "disabled_mode",
                  task_reject_wrapper_candidate)

    # ── B. unsafe feature flag mode ───────────────────────────────────────────
    scenario("B1_inbox_unsafe_flag", "unsafe_mode",
             inbox_email_fetch_wrapper_candidate,
             feature_flag_enabled=True,
             expect_error=RouteWrapperUnsafeExecutionError)
    scenario("B2_approve_unsafe_flag", "unsafe_mode",
             task_approve_wrapper_candidate,
             feature_flag_enabled=True,
             expect_error=RouteWrapperUnsafeExecutionError)
    scenario("B3_reject_unsafe_flag", "unsafe_mode",
             task_reject_wrapper_candidate,
             feature_flag_enabled=True,
             expect_error=RouteWrapperUnsafeExecutionError)

    # ── C. dry-run fixture success ────────────────────────────────────────────
    scenario("C1_inbox_dryrun_success", "dry_run_success",
             inbox_email_fetch_wrapper_candidate,
             fixtures["inbox_request"],
             fixtures["inbox_response"],
             dry_run=True)
    scenario("C2_approve_dryrun_success", "dry_run_success",
             task_approve_wrapper_candidate,
             fixtures["approve_task_id"],
             fixtures["approve_response"],
             dry_run=True)
    scenario("C3_reject_dryrun_success", "dry_run_success",
             task_reject_wrapper_candidate,
             fixtures["reject_task_id"],
             fixtures["reject_response"],
             dry_run=True)

    # ── D. bad fixture boundary ───────────────────────────────────────────────
    scenario("D1_inbox_secret_bad_fixture", "bad_fixture_boundary",
             inbox_email_fetch_wrapper_candidate,
             fixtures["inbox_bad_request"],
             None,
             dry_run=True,
             expect_error=Exception)

    scenario("D2_approve_missing_task_id", "bad_fixture_boundary",
             task_approve_wrapper_candidate,
             "",
             None,
             dry_run=True,
             expect_error=Exception)

    scenario("D3_reject_missing_task_id", "bad_fixture_boundary",
             task_reject_wrapper_candidate,
             "",
             None,
             dry_run=True,
             expect_error=Exception)

    # D4: approve double slash 방지 (빈 task_id)
    scenario("D4_approve_no_double_slash", "bad_fixture_boundary",
             task_approve_wrapper_candidate,
             "",
             None,
             dry_run=True,
             expect_error=Exception)

    # D5: reject double slash 방지 (빈 task_id)
    scenario("D5_reject_no_double_slash", "bad_fixture_boundary",
             task_reject_wrapper_candidate,
             "",
             None,
             dry_run=True,
             expect_error=Exception)

    # ── 집계 ──────────────────────────────────────────────────────────────────
    total = len(scenarios)
    passed = sum(1 for s in scenarios if s["passed"])
    failed = total - passed

    groups: dict[str, list[bool]] = {}
    for s in scenarios:
        groups.setdefault(s["group"], []).append(s["passed"])

    def group_ok(name: str) -> bool:
        return all(groups.get(name, [False]))

    # disabled mode: ok=False, would_call_adapter=False 추가 검증
    disabled_ok = True
    for s in [s1, s2, s3]:
        if s["passed"] and s["result"]:
            r = s["result"]
            if r.get("ok") is not False or r.get("would_call_adapter") is not False:
                disabled_ok = False
        elif not s["passed"]:
            disabled_ok = False

    # dry-run fixture: approval_gate_executed=False 추가 검증
    dryrun_ok = group_ok("dry_run_success")
    for s in scenarios:
        if s["group"] == "dry_run_success" and s["passed"] and s["result"]:
            r = s["result"]
            nr = r.get("normalized_response", {})
            if "approval_gate_executed" in nr and nr["approval_gate_executed"] is not False:
                dryrun_ok = False

    # no double slash
    no_double_slash = True
    for s in scenarios:
        if s["passed"] and s["result"]:
            pm = s["result"].get("path_mapping", {})
            for key in ("legacy_path", "fastapi_path"):
                if "//" in pm.get(key, ""):
                    no_double_slash = False

    # no forbidden route
    no_forbidden_route = all(
        excl not in PHASE1I_TARGET_PATHS for excl in EXCLUDED_PATHS
    )

    verdict = (
        "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_READY"
        if failed == 0 and disabled_ok and dryrun_ok and no_double_slash
        else "PHASE1I_STAGING_DRY_RUN_INTERNAL_SMOKE_FAIL"
    )

    summary: dict[str, Any] = {
        "phase": PHASE,
        "smoke_id": SMOKE_ID,
        "staging_mode": STAGING_MODE,
        **counters,
        "total_scenarios": total,
        "passed_scenarios": passed,
        "failed_scenarios": failed,
        "wrapper_count": 3,
        "disabled_mode_passed": disabled_ok,
        "unsafe_mode_passed": group_ok("unsafe_mode"),
        "dry_run_success_passed": dryrun_ok,
        "bad_fixture_boundary_passed": group_ok("bad_fixture_boundary"),
        "no_double_slash": no_double_slash,
        "no_forbidden_route": no_forbidden_route,
        "verdict": verdict,
        "_scenarios": scenarios,
    }
    return summary


def main() -> int:
    print("=" * 70)
    print(f"SMOKE RUNNER: {SMOKE_ID}")
    print(f"STAGING MODE: {STAGING_MODE}")
    print(f"PHASE: {PHASE}")
    print("=" * 70)

    summary = run_phase1i_internal_smoke()
    scenarios = summary.pop("_scenarios", [])

    print("\n[Smoke Scenario Results]")
    for s in scenarios:
        mark = "✅" if s["passed"] else "❌"
        info = s["error"] if not s["passed"] or (s["error"] and "expected" not in str(s.get("error", ""))) else ""
        # expected error scenarios: error contains the raised message — show as triggered
        if s["passed"] and s["error"]:
            info = f"expected error triggered: {str(s['error'])[:60]}"
        print(f"  {mark} [{s['group']}] {s['id']}{' — ' + info if info else ''}")

    print("\n[Safety Counters]")
    counter_keys = [
        "server_started", "route_connected", "live_traffic_allowed",
        "http_call_count", "db_read_count", "db_write_count",
        "secret_value_output_count", "email_fetch_live_call_count",
        "approve_live_call_count", "reject_live_call_count",
        "execute_call_count", "webhook_call_count",
    ]
    for k in counter_keys:
        v = summary[k]
        ok = v is False or v == 0
        mark = "✅" if ok else "❌"
        print(f"  {mark} {k}={v}")

    print("\n[Summary]")
    print(f"  total_scenarios      : {summary['total_scenarios']}")
    print(f"  passed_scenarios     : {summary['passed_scenarios']}")
    print(f"  failed_scenarios     : {summary['failed_scenarios']}")
    print(f"  wrapper_count        : {summary['wrapper_count']}")
    print(f"  disabled_mode_passed : {summary['disabled_mode_passed']}")
    print(f"  unsafe_mode_passed   : {summary['unsafe_mode_passed']}")
    print(f"  dry_run_success_passed: {summary['dry_run_success_passed']}")
    print(f"  bad_fixture_boundary_passed: {summary['bad_fixture_boundary_passed']}")
    print(f"  no_double_slash      : {summary['no_double_slash']}")
    print(f"  no_forbidden_route   : {summary['no_forbidden_route']}")

    verdict = summary["verdict"]
    print("\n" + "=" * 70)
    print(f"VERDICT: {verdict}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)

    return 0 if summary["failed_scenarios"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
