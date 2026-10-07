"""5050 legacy → FastAPI 이관 준비 감사 테스트.

ASSISTANT_BACKEND_5050_LEGACY_FASTAPI_MIGRATION_PLAN_01
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "audit_5050_legacy_fastapi_migration_readiness.py"


def _run_json() -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_script_exists():
    assert SCRIPT.exists()


def test_shutdown_5050_forbidden():
    report = _run_json()
    assert report["shutdown_5050_forbidden"] is True


def test_nginx_change_forbidden():
    report = _run_json()
    assert report["nginx_change_forbidden"] is True


def test_full_route_switch_forbidden():
    report = _run_json()
    assert report["full_route_switch_forbidden"] is True


def test_read_only():
    report = _run_json()
    assert report["read_only"] is True


def test_verdict_migration_plan_ready():
    report = _run_json()
    assert report["verdict"] == "MIGRATION_PLAN_READY"


def test_5050_routes_total():
    report = _run_json()
    assert report["routes_5050_total"] >= 15


def test_migration_matrix_has_dashboard():
    report = _run_json()
    matrix = report["migration_matrix"]
    dashboard_routes = [r for tier in matrix.values() for r in tier if "dashboard" in r["path"]]
    assert len(dashboard_routes) >= 2


def test_migration_matrix_has_webhook():
    report = _run_json()
    matrix = report["migration_matrix"]
    webhook_routes = [r for tier in matrix.values() for r in tier if "webhook" in r["path"]]
    assert len(webhook_routes) >= 2


def test_migration_matrix_has_inbox():
    report = _run_json()
    matrix = report["migration_matrix"]
    inbox_routes = [r for tier in matrix.values() for r in tier if "inbox" in r["path"]]
    assert len(inbox_routes) >= 3


def test_migration_matrix_has_tasks():
    report = _run_json()
    matrix = report["migration_matrix"]
    task_routes = [r for tier in matrix.values() for r in tier if "/tasks" in r["path"]]
    assert len(task_routes) >= 4


def test_do_not_touch_contains_kakaowork():
    report = _run_json()
    assert any("kakaowork" in p for p in report["do_not_touch_routes"])


def test_do_not_touch_contains_kakaotalk():
    report = _run_json()
    assert any("kakaotalk" in p for p in report["do_not_touch_routes"])


def test_5050_actually_receives_only_dashboard():
    report = _run_json()
    actual = report["5050_actually_receives_via_nginx"]
    assert all("/dashboard" in p for p in actual), f"5050이 dashboard 외 경로를 받음: {actual}"


def test_already_routed_to_8400_exists():
    report = _run_json()
    matrix = report["migration_matrix"]
    assert "ALREADY_ROUTED_TO_8400" in matrix
    assert len(matrix["ALREADY_ROUTED_TO_8400"]) >= 3


def test_hold_dangerous_contains_execute():
    report = _run_json()
    matrix = report["migration_matrix"]
    assert "HOLD_DANGEROUS" in matrix
    execute_routes = [r for r in matrix["HOLD_DANGEROUS"] if "execute" in r["path"]]
    assert len(execute_routes) >= 1


def test_overlap_routes_exist():
    report = _run_json()
    assert len(report["overlap_routes"]) >= 3


def test_critical_finding_mentions_nginx():
    report = _run_json()
    finding = report["critical_finding"]
    assert "nginx" in finding or "8400" in finding


def test_migration_roadmap_6_phases():
    report = _run_json()
    assert len(report["migration_roadmap"]) == 6


def test_migration_roadmap_phase6_forbidden_now():
    report = _run_json()
    phase6 = report["migration_roadmap"][5]
    prereq = phase6["prerequisite"].lower()
    assert "1~5단계" in prereq or "1" in prereq


def test_immediate_action_possible_exists():
    report = _run_json()
    assert len(report["immediate_action_possible"]) >= 3
