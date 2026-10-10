"""opt-in flag 기본값 동작 검증 (backward compat)."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_policy_integration import (
    attach_with_policy,
    download_with_policy,
    open_with_policy,
    submit_with_policy,
    type_with_policy,
)
from core.agent_runtime.runtime.site_profile.browser_site_registry import clear_all
from core.agent_runtime.runtime.site_profile.browser_value_registry import clear_all as clear_values


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    clear_values()
    yield
    clear_all()
    clear_values()


def test_open_default_opt_out_legacy_bypass():
    res = open_with_policy(raw_url="https://anything.example.com")
    assert res["ok"] is True
    assert res["policy_verdict"] == "LEGACY_BYPASS"


def test_type_default_opt_out_legacy_bypass():
    res = type_with_policy(raw_text="anything")
    assert res["ok"] is True
    assert res["policy_verdict"] == "LEGACY_BYPASS"


def test_submit_default_opt_out_legacy_bypass():
    res = submit_with_policy(selector_label="제출")
    assert res["ok"] is True
    assert res["policy_verdict"] == "LEGACY_BYPASS"


def test_download_default_opt_out_legacy_bypass():
    res = download_with_policy(source_url="https://anything.example.com/x.pdf")
    assert res["ok"] is True
    assert res["policy_verdict"] == "LEGACY_BYPASS"


def test_attach_default_opt_out_legacy_bypass():
    res = attach_with_policy(file_basename="x.pdf")
    assert res["ok"] is True
    assert res["policy_verdict"] == "LEGACY_BYPASS"


def test_opt_in_flag_keyword_only():
    """use_policy_registry는 명시적으로 True 전달해야 함."""
    res = open_with_policy(use_policy_registry=False, raw_url="https://x")
    assert res["policy_verdict"] == "LEGACY_BYPASS"
