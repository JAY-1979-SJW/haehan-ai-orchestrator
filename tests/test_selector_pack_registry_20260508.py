"""tests/test_selector_pack_registry_20260508.py - selector_pack_registry 단위 테스트"""
import pytest

from core.agent_runtime.runtime.site_profile.selector_pack_registry import (
    _FORBIDDEN_SELECTOR_KEYS,
    _PACKS,
    generate_skeleton_pack,
    get_selector_pack,
    get_selectors,
    register_selector_pack,
    validate_selector_pack,
)

_BUILTIN_PACKS = ["naver_blog", "naver_cafe", "g2b_public", "generic_content_site"]


def test_builtin_packs_registered():
    for site_id in _BUILTIN_PACKS:
        assert site_id in _PACKS, f"팩 미등록: {site_id}"


def test_get_selector_pack_returns_dict():
    pack = get_selector_pack("naver_blog")
    assert isinstance(pack, dict)
    assert "site_id" in pack
    assert "selectors" in pack


def test_get_selectors_returns_selector_dict():
    sels = get_selectors("naver_blog")
    assert isinstance(sels, dict)
    assert len(sels) > 0


def test_get_selector_pack_unknown_returns_none():
    pack = get_selector_pack("nonexistent_site_xyz")
    assert pack is None


def test_no_forbidden_selectors_in_builtin_packs():
    for site_id in _BUILTIN_PACKS:
        pack = get_selector_pack(site_id)
        selectors = pack.get("selectors", {}) if pack else {}
        for key in _FORBIDDEN_SELECTOR_KEYS:
            assert key not in selectors, f"{site_id}: 금지 selector 포함 - {key}"


def test_register_pack_with_forbidden_key_raises():
    with pytest.raises(ValueError):
        register_selector_pack("test_forbidden_pack2", {
            "password_input": ["#pw"],
            "post_title_input": ["#title"],
        })


def test_generate_skeleton_pack():
    skeleton = generate_skeleton_pack("test_skeleton_site2")
    assert "site_id" in skeleton
    assert "selectors" in skeleton
    selectors = skeleton["selectors"]
    for key in _FORBIDDEN_SELECTOR_KEYS:
        assert key not in selectors


def test_validate_selector_pack_clean():
    errors = validate_selector_pack({"post_title_input": ["#title"], "submit_button": ["#submit"]})
    assert errors == []


def test_validate_selector_pack_with_forbidden():
    errors = validate_selector_pack({"otp_input": ["#otp"], "post_title_input": ["#title"]})
    assert len(errors) > 0
    assert any("otp_input" in e for e in errors)


def test_register_custom_pack():
    register_selector_pack("test_custom_pack_selector2", {"submit_button": ["#btn"]})
    pack = get_selector_pack("test_custom_pack_selector2")
    assert pack is not None
    assert pack["selectors"]["submit_button"] == ["#btn"]


def test_register_pack_overwrites_existing():
    register_selector_pack("test_dup_pack_sel2", {"submit_button": ["#btn"]})
    register_selector_pack("test_dup_pack_sel2", {"submit_button": ["#btn2"]})
    pack = get_selector_pack("test_dup_pack_sel2")
    assert pack["selectors"]["submit_button"] == ["#btn2"]
