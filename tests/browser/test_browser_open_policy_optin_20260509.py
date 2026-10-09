"""browser.open opt-in 정책 검증."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_policy_integration import open_with_policy
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
        allowed_paths=("/notice", "/search"),
        blocked_paths=("/admin",),
    ))
    yield
    clear_all()


def test_site_id_allowed():
    res = open_with_policy(use_policy_registry=True,
                           site_id="g2b", path_key="/notice")
    assert res["ok"] is True
    assert res["policy_verdict"] == "ALLOWED"
    assert res["site_id"] == "g2b"


def test_raw_url_blocked_when_unregistered_host():
    res = open_with_policy(use_policy_registry=True,
                           raw_url="https://random.example.com/x")
    assert res["ok"] is False
    assert res["policy_verdict"] == "BLOCKED"


def test_raw_url_allowed_via_registered_host():
    res = open_with_policy(use_policy_registry=True,
                           raw_url="https://www.g2b.go.kr/notice",
                           path_key="/notice")
    assert res["ok"] is True


def test_blocked_path():
    res = open_with_policy(use_policy_registry=True,
                           site_id="g2b", path_key="/admin")
    assert res["ok"] is False
    assert res["policy_verdict"] == "BLOCKED"


def test_unknown_site_id():
    res = open_with_policy(use_policy_registry=True, site_id="nonexistent")
    assert res["ok"] is False


def test_no_site_no_url_blocked():
    res = open_with_policy(use_policy_registry=True)
    assert res["ok"] is False


def test_execution_location_local_agent_required():
    res = open_with_policy(use_policy_registry=True,
                           site_id="g2b", path_key="/notice")
    assert res["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_forbidden_purpose_blocked():
    res = open_with_policy(use_policy_registry=True,
                           site_id="g2b", path_key="/notice",
                           intended_purpose="cookie_capture")
    assert res["ok"] is False
