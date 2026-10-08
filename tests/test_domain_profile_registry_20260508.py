"""도메인 프로필 레지스트리 테스트 (LOCAL_BROWSER_DEFAULT 아키텍처 반영)"""
from __future__ import annotations

import pytest

from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
    get_all_registered_domains,
    get_domain_profile,
    get_login_execution,
    is_action_blocked_for_domain,
    is_domain_registered,
    is_user_direct_action_for_domain,
    register_domain_profile,
)


# B-1: g2b.go.kr 등록 확인
def test_g2b_registered():
    assert is_domain_registered("g2b.go.kr")

def test_www_g2b_registered():
    assert is_domain_registered("www.g2b.go.kr")

def test_hometax_registered():
    assert is_domain_registered("hometax.go.kr")

# B-2: g2b category
def test_g2b_category():
    p = get_domain_profile("g2b.go.kr")
    assert p["category"] == "government_procurement"

# B-3: g2b default_execution → LOCAL_BROWSER_DEFAULT
def test_g2b_default_execution_local_browser_default():
    p = get_domain_profile("g2b.go.kr")
    assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

# B-4: g2b login_execution → LOCAL_BROWSER_DEFAULT
def test_g2b_login_local_browser_default():
    assert get_login_execution("g2b.go.kr") == "LOCAL_BROWSER_DEFAULT"

# B-5: hometax default_execution → LOCAL_BROWSER_DEFAULT
def test_hometax_default_execution_local():
    p = get_domain_profile("hometax.go.kr")
    assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

# B-6: hometax server_to_local_fallback=False
def test_hometax_no_fallback():
    p = get_domain_profile("hometax.go.kr")
    assert p["server_to_local_fallback"] is False

# B-7: 미등록 도메인 → 기본값 LOCAL_BROWSER_DEFAULT
def test_unknown_domain_default():
    p = get_domain_profile("unknown-site.com")
    assert p["category"] == "unknown"
    assert p["default_execution"] == "LOCAL_BROWSER_DEFAULT"

# B-8: 빈 도메인 → 기본값
def test_empty_domain_default():
    p = get_domain_profile("")
    assert p["category"] == "unknown"

# B-9: bid_submit 차단
def test_bid_submit_blocked_g2b():
    assert is_action_blocked_for_domain("g2b.go.kr", "bid_submit") is True

# B-10: cookie_export 차단
def test_cookie_export_blocked():
    assert is_action_blocked_for_domain("g2b.go.kr", "cookie_export") is True

# B-11: otp_input → user_direct
def test_otp_input_user_direct():
    assert is_user_direct_action_for_domain("g2b.go.kr", "otp_input") is True

# B-12: get_all_registered_domains
def test_registered_domains_list():
    domains = get_all_registered_domains()
    assert "g2b.go.kr" in domains
    assert "www.g2b.go.kr" in domains
    assert "hometax.go.kr" in domains

# B-13: wildcard 등록 불가
def test_wildcard_domain_register_blocked():
    with pytest.raises(ValueError):
        register_domain_profile({"domain": "*.go.kr", "category": "test"})

# B-14: 동적 등록
def test_dynamic_register():
    register_domain_profile({
        "domain": "test-dynamic.example.com",
        "category": "test",
        "default_execution": "LOCAL_BROWSER_DEFAULT",
        "login_execution": "LOCAL_BROWSER_DEFAULT",
        "security_auth_required": False,
        "server_to_local_fallback": True,
        "blocked_actions": [],
        "user_direct_actions": [],
        "allowed_readonly": True,
        "notes": "",
    })
    assert is_domain_registered("test-dynamic.example.com")
