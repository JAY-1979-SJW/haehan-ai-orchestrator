"""browser.type opt-in 정책 검증."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_policy_integration import type_with_policy
from core.agent_runtime.runtime.site_profile.browser_value_registry import (
    VTYPE_SAMPLE_TEXT,
    ValuePolicy,
    clear_all,
    register_value,
)


@pytest.fixture(autouse=True)
def _setup():
    clear_all()
    register_value(ValuePolicy(
        value_key="sample_keyword",
        label="검색어",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="공고",
        allowed_fields=("search_input",),
    ))
    yield
    clear_all()


def test_value_key_based_input_allowed():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk_search",
                           value_key="sample_keyword",
                           field_id="search_input")
    assert res["ok"] is True
    assert res["sample_safe_value"] == "공고"


def test_raw_text_blocked():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk_search",
                           raw_text="hello")
    assert res["ok"] is False
    assert res["policy_verdict"] == "BLOCKED"


def test_raw_password_blocked():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk_pw",
                           raw_text="mypass",
                           field_id="password_field")
    assert res["ok"] is False


def test_raw_otp_blocked():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk_otp",
                           raw_text="123456",
                           field_id="otp_code")
    assert res["ok"] is False


def test_no_selector_key_blocked():
    res = type_with_policy(use_policy_registry=True,
                           value_key="sample_keyword",
                           field_id="search_input")
    assert res["ok"] is False


def test_unknown_value_key_blocked():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk",
                           value_key="nonexistent",
                           field_id="x")
    assert res["ok"] is False


def test_field_not_allowed_blocked():
    res = type_with_policy(use_policy_registry=True,
                           selector_key="sk",
                           value_key="sample_keyword",
                           field_id="other_field")
    assert res["ok"] is False
