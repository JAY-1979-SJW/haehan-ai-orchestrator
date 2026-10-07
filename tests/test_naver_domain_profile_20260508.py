"""
네이버 도메인 프로필 테스트
"""

import pytest

from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
    get_domain_profile,
    is_action_blocked_for_domain,
    is_domain_registered,
)

NAVER_DOMAINS = [
    "naver.com",
    "www.naver.com",
    "nid.naver.com",
    "cafe.naver.com",
    "m.cafe.naver.com",
    "blog.naver.com",
    "m.blog.naver.com",
]


class TestNaverDomainRegistered:
    @pytest.mark.parametrize("domain", NAVER_DOMAINS)
    def test_naver_domain_registered(self, domain):
        assert is_domain_registered(domain), f"{domain} 미등록"

    @pytest.mark.parametrize("domain", NAVER_DOMAINS)
    def test_naver_domain_local_browser_default(self, domain):
        profile = get_domain_profile(domain)
        assert profile["default_execution"] == "LOCAL_BROWSER_DEFAULT", f"{domain} default_execution 불일치"

    @pytest.mark.parametrize("domain", NAVER_DOMAINS)
    def test_naver_domain_allowed_readonly(self, domain):
        profile = get_domain_profile(domain)
        assert profile["allowed_readonly"] is True

    @pytest.mark.parametrize("domain", NAVER_DOMAINS)
    def test_naver_domain_portal_sns_category(self, domain):
        profile = get_domain_profile(domain)
        assert profile["category"] == "portal_sns"


class TestNaverLoginDomain:
    def test_nid_login_domain_registered(self):
        assert is_domain_registered("nid.naver.com")

    def test_nid_local_browser_default(self):
        profile = get_domain_profile("nid.naver.com")
        assert profile["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_nid_login_in_user_direct(self):
        profile = get_domain_profile("nid.naver.com")
        assert "login_password_input" in profile["user_direct_actions"]

    def test_nid_otp_in_user_direct(self):
        profile = get_domain_profile("nid.naver.com")
        assert "otp_input" in profile["user_direct_actions"]


class TestNaverCafeProfile:
    def test_cafe_registered(self):
        assert is_domain_registered("cafe.naver.com")

    def test_cafe_local_browser_default(self):
        profile = get_domain_profile("cafe.naver.com")
        assert profile["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_cafe_bulk_spam_blocked(self):
        profile = get_domain_profile("cafe.naver.com")
        assert "bulk_spam_post" in profile["blocked_actions"] or "bulk_spam_comment" in profile["blocked_actions"]

    def test_cafe_cookie_export_blocked(self):
        assert is_action_blocked_for_domain("cafe.naver.com", "cookie_export")

    def test_cafe_session_export_blocked(self):
        assert is_action_blocked_for_domain("cafe.naver.com", "session_export")

    def test_mobile_cafe_registered(self):
        assert is_domain_registered("m.cafe.naver.com")


class TestNaverBlogProfile:
    def test_blog_registered(self):
        assert is_domain_registered("blog.naver.com")

    def test_blog_local_browser_default(self):
        profile = get_domain_profile("blog.naver.com")
        assert profile["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_blog_cookie_export_blocked(self):
        assert is_action_blocked_for_domain("blog.naver.com", "cookie_export")

    def test_blog_auto_sign_blocked(self):
        assert is_action_blocked_for_domain("blog.naver.com", "auto_sign")

    def test_mobile_blog_registered(self):
        assert is_domain_registered("m.blog.naver.com")
