"""Browser Site Registry Policy 테스트 (LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1)."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_site_registry import (
    CAPTURE_NONE,
    CRED_NO_CAPTURE,
    EXECUTION_LOCAL_AGENT_REQUIRED,
    LOGIN_PUBLIC_READONLY,
    SitePolicy,
    clear_all,
    get_site,
    list_sites,
    register_site,
    resolve_url,
    validate_raw_url,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


def _sample(site_id="g2b", host="www.g2b.go.kr") -> SitePolicy:
    return SitePolicy(
        site_id=site_id,
        label="조달청 나라장터",
        allowed_hosts=(host,),
        allowed_paths=("/notice", "/search"),
        blocked_paths=("/admin",),
        allowed_purposes=("readonly_browse",),
    )


def test_site_id_register_and_lookup():
    register_site(_sample())
    assert get_site("g2b") is not None
    assert "g2b" in list_sites()


def test_raw_url_blocked_when_unregistered():
    res = validate_raw_url("https://random.example.com/path")
    assert res["ok"] is False
    assert res["verdict"] == "RAW_URL_BLOCKED"


def test_raw_url_allowed_only_via_registry():
    register_site(_sample())
    res = validate_raw_url("https://www.g2b.go.kr/notice")
    assert res["ok"] is True
    assert res["verdict"] == "ALLOWED_VIA_REGISTRY"
    assert res["site_id"] == "g2b"


def test_allowed_hosts_required():
    with pytest.raises(ValueError):
        register_site(SitePolicy(site_id="bad", label="x", allowed_hosts=()))


def test_allowed_paths_enforced():
    register_site(_sample())
    bad = resolve_url("g2b", "/admin")
    assert bad["ok"] is False
    assert bad["verdict"] in ("PATH_BLOCKED", "PATH_NOT_ALLOWED")


def test_blocked_paths_enforced():
    register_site(_sample())
    res = resolve_url("g2b", "/admin")
    assert res["ok"] is False


def test_execution_location_local_agent_required():
    p = _sample()
    assert p.execution_location == EXECUTION_LOCAL_AGENT_REQUIRED


def test_credential_policy_no_capture():
    p = _sample()
    assert p.credential_policy == CRED_NO_CAPTURE


def test_capture_policy_no_screenshot_no_har():
    p = _sample()
    assert p.capture_policy == CAPTURE_NONE


def test_default_login_mode_public_readonly():
    p = _sample()
    assert p.login_mode == LOGIN_PUBLIC_READONLY


def test_unknown_site_resolve():
    res = resolve_url("nonexistent")
    assert res["ok"] is False
    assert res["verdict"] == "UNKNOWN_SITE"
