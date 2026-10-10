"""browser.submit opt-in 정책 검증."""
from __future__ import annotations

from core.agent_runtime.runtime.site_profile.browser_discovery_candidates import (
    CANDIDATE_BUTTON,
    CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_SUBMIT_BUTTON,
)
from core.agent_runtime.runtime.site_profile.browser_policy_integration import submit_with_policy


def test_submit_no_approval_blocked():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk_submit",
                             selector_label="제출",
                             candidate_type=CANDIDATE_SUBMIT_BUTTON)
    assert res["ok"] is False
    assert res["required_approval"] is True


def test_submit_with_approval_handoff_required():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk_submit",
                             selector_label="제출",
                             candidate_type=CANDIDATE_SUBMIT_BUTTON,
                             approval_token="tok123")
    assert res["ok"] is True
    assert res["handoff_required"] is True
    assert res["risk_level"] == "HIGH"


def test_destructive_high_risk():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk_del",
                             selector_label="삭제",
                             candidate_type=CANDIDATE_DESTRUCTIVE_BUTTON,
                             approval_token="tok")
    assert res["ok"] is True
    assert res["risk_level"] == "HIGH"


def test_save_label_destructive():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk",
                             selector_label="저장",
                             candidate_type=CANDIDATE_BUTTON)
    assert res["ok"] is False


def test_sign_label_destructive():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk",
                             selector_label="전자서명",
                             candidate_type=CANDIDATE_BUTTON)
    assert res["ok"] is False


def test_payment_label_destructive():
    res = submit_with_policy(use_policy_registry=True,
                             selector_key="sk",
                             selector_label="결제",
                             candidate_type=CANDIDATE_BUTTON)
    assert res["ok"] is False


def test_no_selector_key_blocked():
    res = submit_with_policy(use_policy_registry=True,
                             selector_label="제출")
    assert res["ok"] is False
