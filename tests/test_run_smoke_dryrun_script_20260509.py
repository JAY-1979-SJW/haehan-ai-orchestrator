"""run_readonly_smoke_dryrun 스크립트 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from run_readonly_smoke_dryrun import simulate_step


def _step(action: str, label: str = "테스트", no_click: bool = False) -> dict:
    return {
        "step": 1,
        "action": action,
        "label": label,
        "no_click": no_click,
        "no_input": True,
        "execution_mode": "DRY_RUN",
        "selector_fingerprint": "abc123def456abcd",
        "auto_approve": True,
    }


def test_navigate_and_check_label_passes():
    r = simulate_step(_step("navigate_and_check_label"))
    assert r["passed"] is True
    assert r["result"] == "DRY_RUN_PASS"


def test_verify_link_visible_passes():
    r = simulate_step(_step("verify_link_visible"))
    assert r["passed"] is True


def test_verify_page_title_passes():
    r = simulate_step(_step("verify_page_title"))
    assert r["passed"] is True


def test_verify_table_column_passes():
    r = simulate_step(_step("verify_table_column"))
    assert r["passed"] is True


def test_click_blocked():
    r = simulate_step(_step("click"))
    assert r["passed"] is False
    assert r["result"] == "BLOCKED"


def test_submit_blocked():
    r = simulate_step(_step("submit"))
    assert r["passed"] is False


def test_login_blocked():
    r = simulate_step(_step("login"))
    assert r["passed"] is False
    assert r["result"] == "BLOCKED"


def test_screenshot_blocked():
    r = simulate_step(_step("screenshot"))
    assert r["passed"] is False


def test_non_dryrun_mode_blocked():
    step = _step("navigate_and_check_label")
    step["execution_mode"] = "LIVE"
    r = simulate_step(step)
    assert r["passed"] is False
    assert r["result"] == "BLOCKED"
