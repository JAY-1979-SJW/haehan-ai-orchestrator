"""Unit tests for scripts.site_engine.registry."""
import pytest

from scripts.site_engine.profiles import SiteProfile
from scripts.site_engine.registry import SiteProfileRegistry
from scripts.site_engine.site_types import SiteCapability


def _make_profile(key: str) -> SiteProfile:
    return SiteProfile(
        key=key,
        base_url=f"https://{key}.example.com",
        display_name=key.capitalize(),
        login_domain_hints=(f"{key}.example.com",),
        allowed_capabilities=(SiteCapability.READ,),
    )


def test_register_and_get():
    reg = SiteProfileRegistry()
    p = _make_profile("alpha")
    reg.register(p)
    assert reg.get("alpha") is p


def test_get_nonexistent_returns_none():
    reg = SiteProfileRegistry()
    assert reg.get("nonexistent") is None


def test_get_or_raise_raises_on_missing():
    reg = SiteProfileRegistry()
    with pytest.raises(KeyError):
        reg.get_or_raise("missing")


def test_has_returns_true_after_register():
    reg = SiteProfileRegistry()
    reg.register(_make_profile("beta"))
    assert reg.has("beta")


def test_has_returns_false_before_register():
    reg = SiteProfileRegistry()
    assert not reg.has("gamma")


def test_duplicate_registration_raises():
    reg = SiteProfileRegistry()
    p = _make_profile("delta")
    reg.register(p)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(p)


def test_list_profiles_returns_all():
    reg = SiteProfileRegistry()
    for k in ("a", "b", "c"):
        reg.register(_make_profile(k))
    keys = {p.key for p in reg.list_profiles()}
    assert keys == {"a", "b", "c"}


def test_list_keys():
    reg = SiteProfileRegistry()
    reg.register(_make_profile("x"))
    reg.register(_make_profile("y"))
    assert set(reg.list_keys()) == {"x", "y"}


def test_len():
    reg = SiteProfileRegistry()
    assert len(reg) == 0
    reg.register(_make_profile("one"))
    assert len(reg) == 1


def test_register_non_profile_raises():
    reg = SiteProfileRegistry()
    with pytest.raises(TypeError):
        reg.register("not_a_profile")  # type: ignore
