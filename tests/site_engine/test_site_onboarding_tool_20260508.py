"""tests/test_site_onboarding_tool_20260508.py - site onboarding 도구 단위 테스트"""

from core.agent_runtime.runtime.site_profile.selector_pack_registry import (
    _FORBIDDEN_SELECTOR_KEYS,
    get_selector_pack,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import (
    _COMMON_BLOCKED,
    CAT_FORUM,
    CAT_GENERIC,
    LOGIN_WAITING_AUTH,
    is_site_registered,
)
from scripts.site_engine.create_site_profile import create_site_profile
from scripts.site_engine.validate_site_profile import validate_all_registered, validate_profile


def test_create_site_profile_basic():
    profile = create_site_profile(
        site_id="test_onboard_site_basic",
        display_name="테스트 온보딩 사이트",
        domains=["onboard-basic.example.com"],
        category=CAT_GENERIC,
    )
    assert profile["site_id"] == "test_onboard_site_basic"
    assert is_site_registered("test_onboard_site_basic")


def test_create_site_profile_registers_selector_pack():
    create_site_profile(
        site_id="test_onboard_selector",
        display_name="셀렉터 온보딩",
        domains=["onboard-selector.example.com"],
        category=CAT_FORUM,
    )
    pack = get_selector_pack("test_onboard_selector")
    assert isinstance(pack, dict)
    for key in _FORBIDDEN_SELECTOR_KEYS:
        assert key not in pack, f"금지 selector 포함: {key}"


def test_create_site_profile_blocked_actions_include_common():
    profile = create_site_profile(
        site_id="test_onboard_blocked",
        display_name="금지 검사",
        domains=["onboard-blocked.example.com"],
        category=CAT_GENERIC,
    )
    blocked = set(profile["blocked_actions"])
    missing = set(_COMMON_BLOCKED) - blocked
    assert not missing, f"공통 blocked action 누락: {missing}"


def test_create_site_profile_requires_audit_log():
    profile = create_site_profile(
        site_id="test_onboard_audit",
        display_name="감사 로그 검사",
        domains=["onboard-audit.example.com"],
        category=CAT_GENERIC,
    )
    assert profile["requires_audit_log"] is True


def test_validate_profile_clean():
    profile = create_site_profile(
        site_id="test_onboard_validate_clean",
        display_name="유효성 테스트",
        domains=["onboard-validate.example.com"],
        category=CAT_GENERIC,
    )
    result = validate_profile(profile)
    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_profile_missing_blocked():
    bad_profile = {
        "site_id": "bad_profile",
        "display_name": "나쁜",
        "domains": ["bad.example.com"],
        "category": CAT_GENERIC,
        "login_policy": LOGIN_WAITING_AUTH,
        "supported_capabilities": ["READONLY_EXPLORE"],
        "delegated_actions": [],
        "direct_required_actions": [],
        "blocked_actions": [],  # 비어 있음 — 오류 발생해야 함
        "max_default_executions": 1,
        "requires_audit_log": True,
        "notes": "",
    }
    result = validate_profile(bad_profile)
    assert result["ok"] is False


def test_validate_profile_audit_log_false():
    bad_profile = {
        "site_id": "bad_audit",
        "display_name": "감사 없음",
        "domains": ["bad-audit.example.com"],
        "category": CAT_GENERIC,
        "login_policy": LOGIN_WAITING_AUTH,
        "supported_capabilities": ["READONLY_EXPLORE"],
        "delegated_actions": [],
        "direct_required_actions": [],
        "blocked_actions": list(_COMMON_BLOCKED),
        "max_default_executions": 1,
        "requires_audit_log": False,
        "notes": "",
    }
    result = validate_profile(bad_profile)
    assert result["ok"] is False


def test_validate_all_registered_no_failures():
    results = validate_all_registered()
    failed = [r for r in results if not r["ok"]]
    assert failed == [], f"검사 실패 profile: {[r['site_id'] for r in failed]}\n오류: {[r['errors'] for r in failed]}"
