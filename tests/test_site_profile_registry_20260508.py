"""tests/test_site_profile_registry_20260508.py - site_profile_registry 단위 테스트"""

from core.agent_runtime.runtime.site_profile.site_profile_registry import (
    _COMMON_BLOCKED,
    _REGISTRY,
    CAT_GENERIC,
    LOGIN_WAITING_AUTH,
    get_profile_by_domain,
    get_site_profile,
    is_action_blocked_for_site,
    is_action_delegated,
    is_site_registered,
    register_site_profile,
)


def test_builtin_profiles_registered():
    for site_id in ("naver", "naver_blog", "naver_cafe", "g2b_public", "generic_content_site"):
        assert is_site_registered(site_id), f"{site_id} 미등록"


def test_get_site_profile_naver():
    p = get_site_profile("naver")
    assert p["site_id"] == "naver"
    assert "naver.com" in p["domains"]
    assert p["requires_audit_log"] is True


def test_get_profile_by_domain():
    p = get_profile_by_domain("blog.naver.com")
    assert p is not None
    assert p["site_id"] == "naver_blog"


def test_get_profile_by_domain_unknown():
    assert get_profile_by_domain("totally.unknown.xyz") is None


def test_common_blocked_actions_in_all_profiles():
    common = set(_COMMON_BLOCKED)
    for site_id, profile in _REGISTRY.items():
        blocked = set(profile.get("blocked_actions", []))
        missing = common - blocked
        assert not missing, f"{site_id}: blocked_actions에서 공통 금지 action 누락 {missing}"


def test_is_action_blocked_for_site():
    assert is_action_blocked_for_site("naver_blog", "password_save")
    assert is_action_blocked_for_site("naver_blog", "cookie_export")
    assert is_action_blocked_for_site("naver_blog", "auto_esign")


def test_is_action_delegated_blog():
    assert is_action_delegated("naver_blog", "blog_publish")
    assert not is_action_delegated("naver_blog", "password_save")


def test_is_action_direct_required_login():
    p = get_site_profile("naver")
    direct = set(p.get("direct_required_actions", []))
    # direct_required_actions는 _COMMON_DIRECT 포함
    assert len(direct) > 0


def test_register_custom_profile():
    custom = {
        "site_id": "test_custom_site_registry",
        "display_name": "테스트 커스텀",
        "domains": ["custom-test-registry.example.com"],
        "category": CAT_GENERIC,
        "default_execution": "LOCAL_BROWSER_DEFAULT",
        "login_policy": LOGIN_WAITING_AUTH,
        "supported_capabilities": ["READONLY_EXPLORE"],
        "delegated_actions": [],
        "direct_required_actions": [],
        "blocked_actions": list(_COMMON_BLOCKED),
        "max_default_executions": 1,
        "requires_audit_log": True,
        "notes": "",
    }
    register_site_profile(custom)
    assert is_site_registered("test_custom_site_registry")


def test_register_duplicate_overwrites():
    # register_site_profile은 중복 등록 시 덮어씀 (ValueError 없음)
    profile = dict(get_site_profile("naver"))
    profile["notes"] = "overwrite test"
    register_site_profile(profile)
    updated = get_site_profile("naver")
    assert updated["notes"] == "overwrite test"


def test_requires_audit_log_all_profiles():
    for site_id, profile in _REGISTRY.items():
        assert profile.get("requires_audit_log") is True, f"{site_id}: requires_audit_log != True"


def test_server_browser_used_not_true():
    for site_id, profile in _REGISTRY.items():
        assert profile.get("server_browser_used") is not True, f"{site_id}: server_browser_used=True 금지"
