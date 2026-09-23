"""build_readonly_smoke_plan 스크립트 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_readonly_smoke_plan import build_step

from ai_orchestrator.local_agent.browser_allowlist_expansion_preflight import VERDICT_ALLOW


def _allow_item(ctype: str, label: str) -> dict:
    return {
        "verdict": VERDICT_ALLOW,
        "candidate_type": ctype,
        "label": label,
        "selector_fingerprint": "abc123def456abcd",
        "risk_level": "LOW",
        "auto_approve": True,
    }


def test_menu_candidate_maps_navigate():
    step = build_step(1, _allow_item("menu_candidate", "입찰공고"))
    assert step["action"] == "navigate_and_check_label"


def test_download_link_maps_verify_link():
    step = build_step(2, _allow_item("download_link_candidate", "공고문"))
    assert step["action"] == "verify_link_visible"


def test_submit_button_no_click_true():
    step = build_step(3, _allow_item("submit_button_candidate", "투찰"))
    assert step["no_click"] is True


def test_step_execution_mode_dryrun():
    step = build_step(1, _allow_item("menu_candidate", "메뉴"))
    assert step["execution_mode"] == "DRY_RUN"


def test_step_no_input_always_true():
    step = build_step(1, _allow_item("field_candidate", "검색어"))
    assert step["no_input"] is True
