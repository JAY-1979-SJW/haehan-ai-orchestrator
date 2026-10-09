"""Selector Resolver Policy 테스트 (selector_key 기반, raw selector 차단).

기존 selector_pack_registry.py + 신규 browser_discovery_candidates.py 조합 검증.
"""

from __future__ import annotations

from core.agent_runtime.runtime.site_profile.browser_allowlist_expansion_preflight import (
    VERDICT_ALLOW,
    VERDICT_BLOCKED,
    VERDICT_REVIEW,
    preflight_expansion,
)
from core.agent_runtime.runtime.site_profile.browser_discovery_candidates import (
    CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_MENU,
    CANDIDATE_SUBMIT_BUTTON,
    RISK_HIGH,
    build_candidate,
)


def test_selector_key_via_fingerprint():
    """raw selector 대신 fingerprint(selector_key) 사용."""
    res = build_candidate(CANDIDATE_MENU, "공고검색", "link", "g2b", "/")
    assert "selector_fingerprint" in res["candidate"]
    assert len(res["candidate"]["selector_fingerprint"]) == 16


def test_raw_selector_direct_execution_blocked():
    res = preflight_expansion(raw_selector_attempt="#submit-btn-123")
    assert res["verdict"] == VERDICT_BLOCKED
    assert "raw selector" in res["reason"].lower()


def test_save_button_high_risk():
    cand = build_candidate(CANDIDATE_SUBMIT_BUTTON, "저장", "button", "g2b", "/form")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW
    assert res["risk_level"] == RISK_HIGH


def test_submit_button_high_risk():
    cand = build_candidate(CANDIDATE_SUBMIT_BUTTON, "제출", "button", "g2b", "/form")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW


def test_sign_button_high_risk():
    cand = build_candidate(CANDIDATE_DESTRUCTIVE_BUTTON, "전자서명", "button", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW
    assert res["risk_level"] == RISK_HIGH


def test_delete_button_high_risk():
    cand = build_candidate(CANDIDATE_DESTRUCTIVE_BUTTON, "삭제", "button", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW


def test_low_risk_readonly_auto_register():
    cand = build_candidate(CANDIDATE_MENU, "공고검색", "link", "g2b", "/")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_ALLOW


def test_low_confidence_review_required():
    cand = build_candidate(CANDIDATE_MENU, "공고검색", "link", "g2b", "/", confidence="LOW")["candidate"]
    res = preflight_expansion(selector_candidate=cand)
    assert res["verdict"] == VERDICT_REVIEW
