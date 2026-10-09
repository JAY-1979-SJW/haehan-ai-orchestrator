"""tests/test_learned_site_profile_store_20260508.py"""

import pytest

from core.agent_runtime.runtime.universal.learned_site_profile_store import (
    clear_all,
    delete_learned_profile,
    get_learned_profile,
    has_learned_profile,
    list_learned_hosts,
    save_learned_profile,
    update_learned_profile,
)

_SENSITIVE_FIELDS = [
    "password_stored",
    "otp_stored",
    "cookie_stored",
    "session_stored",
    "storage_state_stored",
    "cert_password_stored",
]


def setup_function():
    clear_all()


def test_save_and_get():
    save_learned_profile(host="example.com", site_type="blog")
    p = get_learned_profile("example.com")
    assert p is not None
    assert p["host"] == "example.com"
    assert p["site_type"] == "blog"


def test_sensitive_fields_always_false():
    save_learned_profile(host="test.com", site_type="unknown")
    p = get_learned_profile("test.com")
    for f in _SENSITIVE_FIELDS:
        assert p[f] is False, f"{f} != False"


def test_no_password_stored():
    save_learned_profile(host="secure.com", site_type="blog")
    p = get_learned_profile("secure.com")
    assert p["password_stored"] is False


def test_no_cookie_stored():
    save_learned_profile(host="secure2.com", site_type="blog")
    p = get_learned_profile("secure2.com")
    assert p["cookie_stored"] is False


def test_forbidden_key_raises():
    # safe_selector_candidates의 key가 아니라 top-level 저장 금지 key를 검사
    # password_value 같은 forbidden prefix가 있는 key는 _sanitize_entry에서 제거됨
    # validate_entry는 sanitize 후에 실행 — 직접 forbidden key로 entry 생성 시 테스트
    from core.agent_runtime.runtime.universal.learned_site_profile_store import _validate_entry

    errors = _validate_entry({"password_value": "secret"})
    assert len(errors) > 0


def test_safe_selector_candidates_saved():
    save_learned_profile(
        host="safe.com",
        site_type="blog",
        safe_selector_candidates={"publish_button": ["button.publish"]},
    )
    p = get_learned_profile("safe.com")
    assert "publish_button" in p["safe_selector_candidates"]


def test_capability_hints_saved():
    save_learned_profile(
        host="hints.com",
        site_type="blog",
        capability_hints=["READONLY_EXPLORE", "SEARCH"],
    )
    p = get_learned_profile("hints.com")
    assert "READONLY_EXPLORE" in p["capability_hints"]


def test_update_learned_profile():
    save_learned_profile(host="update.com", site_type="blog")
    result = update_learned_profile("update.com", {"workflow_template_id": "blog_publish"})
    assert result is not None
    assert result["workflow_template_id"] == "blog_publish"


def test_update_nonexistent_returns_none():
    result = update_learned_profile("nonexistent.com", {"x": "y"})
    assert result is None


def test_forbidden_key_in_update_raises():
    save_learned_profile(host="secure3.com", site_type="blog")
    with pytest.raises(ValueError):
        update_learned_profile("secure3.com", {"cookie_value": "secretcookie"})


def test_delete_learned_profile():
    save_learned_profile(host="del.com", site_type="blog")
    assert has_learned_profile("del.com")
    delete_learned_profile("del.com")
    assert not has_learned_profile("del.com")


def test_list_learned_hosts():
    save_learned_profile(host="h1.com", site_type="blog")
    save_learned_profile(host="h2.com", site_type="forum")
    hosts = list_learned_hosts()
    assert "h1.com" in hosts
    assert "h2.com" in hosts


def test_no_host_raises():
    with pytest.raises(ValueError):
        save_learned_profile(host="", site_type="blog")


def test_action_risk_mapping_saved():
    save_learned_profile(
        host="risk.com",
        site_type="blog",
        action_risk_mapping={"publish_post": "USER_DELEGATED_PERMISSION_REQUIRED"},
    )
    p = get_learned_profile("risk.com")
    assert p["action_risk_mapping"]["publish_post"] == "USER_DELEGATED_PERMISSION_REQUIRED"
