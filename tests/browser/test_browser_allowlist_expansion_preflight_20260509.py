"""Allowlist Expansion Preflight 테스트."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_allowlist_expansion_preflight import (
    VERDICT_ALLOW,
    VERDICT_BLOCKED,
    VERDICT_REVIEW,
    can_auto_approve,
    preflight_expansion,
)
from core.agent_runtime.runtime.site_profile.browser_discovery_candidates import (
    CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_MENU,
    CANDIDATE_SUBMIT_BUTTON,
    build_candidate,
)
from core.agent_runtime.runtime.site_profile.browser_site_registry import (
    SitePolicy,
    clear_all,
    register_site,
)


@pytest.fixture(autouse=True)
def _setup():
    clear_all()
    register_site(SitePolicy(
        site_id="g2b", label="조달청",
        allowed_hosts=("www.g2b.go.kr",),
    ))
    yield
    clear_all()


def test_readonly_candidate_allow_register():
    cand = build_candidate(CANDIDATE_MENU, "공고검색", "link", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_ALLOW
    assert res["required_approval"] is False


def test_submit_candidate_review_required():
    cand = build_candidate(CANDIDATE_SUBMIT_BUTTON, "제출", "button", "g2b", "/form")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW


def test_delete_candidate_review_or_blocked():
    cand = build_candidate(CANDIDATE_DESTRUCTIVE_BUTTON, "삭제", "button", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] in (VERDICT_REVIEW, VERDICT_BLOCKED)


def test_credential_candidate_blocked():
    res = preflight_expansion(
        value_candidate={"value_key": "user_password", "raw_value": "x"},
    )
    assert res["verdict"] == VERDICT_BLOCKED


def test_server_external_browser_blocked():
    res = preflight_expansion(server_external_browser_attempt=True)
    assert res["verdict"] == VERDICT_BLOCKED


def test_raw_selector_attempt_blocked():
    res = preflight_expansion(raw_selector_attempt="#x")
    assert res["verdict"] == VERDICT_BLOCKED


def test_raw_url_attempt_blocked_unregistered():
    res = preflight_expansion(raw_url_attempt="https://random.example.com")
    assert res["verdict"] == VERDICT_BLOCKED


def test_raw_url_attempt_allowed_via_registry():
    res = preflight_expansion(
        raw_url_attempt="https://www.g2b.go.kr/notice",
        selector_candidate=build_candidate(
            CANDIDATE_MENU, "공고", "link", "g2b", "/notice",
        )["candidate"],
    )
    assert res["verdict"] == VERDICT_ALLOW


def test_registry_patch_returned_for_allow():
    cand = build_candidate(CANDIDATE_MENU, "공고", "link", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["registry_patch"] is not None
    assert res["registry_patch"]["register_as"] == "selector_key_low_risk"


def test_required_approval_for_review():
    cand = build_candidate(CANDIDATE_SUBMIT_BUTTON, "저장", "button", "g2b", "/form")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["required_approval"] is True


def test_warnings_present_for_destructive():
    cand = build_candidate(CANDIDATE_DESTRUCTIVE_BUTTON, "송금", "button", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert len(res["warnings"]) > 0


def test_can_auto_approve_only_allow_low_risk():
    cand_low = build_candidate(CANDIDATE_MENU, "공고", "link", "g2b", "/")["candidate"]
    res_low = preflight_expansion(selector_candidate=cand_low)
    assert can_auto_approve(res_low) is True

    cand_high = build_candidate(CANDIDATE_SUBMIT_BUTTON, "제출", "button", "g2b", "/")["candidate"]
    res_high = preflight_expansion(selector_candidate=cand_high)
    assert can_auto_approve(res_high) is False


def test_destructive_action_candidate_review():
    res = preflight_expansion(action_candidate="submit")
    assert res["verdict"] in (VERDICT_REVIEW, VERDICT_BLOCKED)


def test_forbidden_purpose_blocked():
    cand = build_candidate(CANDIDATE_MENU, "x", "link", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand,
                              intended_purpose="cookie_capture")
    assert res["verdict"] == VERDICT_BLOCKED


def test_empty_input_blocked():
    res = preflight_expansion()
    assert res["verdict"] == VERDICT_BLOCKED
