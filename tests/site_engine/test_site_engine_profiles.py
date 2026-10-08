"""Unit tests for scripts.site_engine.profiles."""

from typing import Any

import pytest

from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import (
    ExecutionLocation,
    GateDecision,
    SiteCapability,
    SiteProfileStatus,
)


def _minimal_profile(**overrides) -> SiteProfile:
    defaults: dict[str, Any] = {
        "key": "test_site",
        "base_url": "https://test.example.com",
        "display_name": "Test Site",
        "login_domain_hints": ("test.example.com",),
        "allowed_capabilities": (SiteCapability.READ,),
    }
    defaults.update(overrides)
    return SiteProfile(**defaults)


def test_minimal_profile_creation():
    p = _minimal_profile()
    assert p.key == "test_site"
    assert p.status == SiteProfileStatus.ACTIVE


def test_profile_with_all_fields():
    policy = SiteActionPolicy(
        capability=SiteCapability.SUBMIT,
        gate=GateDecision.APPROVAL_REQUIRED,
        required_execution_location=ExecutionLocation.LOCAL_AGENT,
        requires_approval=True,
        is_irreversible=True,
    )
    p = _minimal_profile(
        allowed_capabilities=(SiteCapability.READ, SiteCapability.SUBMIT),
        action_policies=(policy,),
    )
    assert p.get_gate(SiteCapability.SUBMIT) == GateDecision.APPROVAL_REQUIRED


def test_get_gate_defaults_to_read_only_allowed():
    p = _minimal_profile()
    assert p.get_gate(SiteCapability.SEARCH) == GateDecision.READ_ONLY_ALLOWED


def test_get_gate_blocked_capability():
    p = _minimal_profile(
        allowed_capabilities=(SiteCapability.READ,),
        blocked_capabilities=(SiteCapability.DELETE,),
    )
    assert p.get_gate(SiteCapability.DELETE) == GateDecision.BLOCKED


def test_is_capability_allowed_true():
    p = _minimal_profile(allowed_capabilities=(SiteCapability.READ, SiteCapability.SEARCH))
    assert p.is_capability_allowed(SiteCapability.READ)


def test_is_capability_allowed_false_not_in_list():
    p = _minimal_profile(allowed_capabilities=(SiteCapability.READ,))
    assert not p.is_capability_allowed(SiteCapability.DELETE)


def test_is_capability_allowed_false_in_blocked():
    # allowed에 없고 blocked에 있는 경우 → blocked gate 반환, allowed 판정 False
    p = _minimal_profile(
        allowed_capabilities=(SiteCapability.READ,),
        blocked_capabilities=(SiteCapability.DELETE,),
    )
    assert not p.is_capability_allowed(SiteCapability.DELETE)


def test_validate_empty_key_raises():
    with pytest.raises(ValueError, match="key"):
        _minimal_profile(key="")


def test_validate_invalid_url_raises():
    with pytest.raises(ValueError, match="base_url"):
        _minimal_profile(base_url="not_a_url")


def test_validate_empty_display_name_raises():
    with pytest.raises(ValueError, match="display_name"):
        _minimal_profile(display_name="")


def test_validate_empty_capabilities_raises():
    with pytest.raises(ValueError, match="allowed_capabilities"):
        _minimal_profile(allowed_capabilities=())


def test_validate_overlap_allowed_blocked_raises():
    with pytest.raises(ValueError, match="both allowed and blocked"):
        _minimal_profile(
            allowed_capabilities=(SiteCapability.READ, SiteCapability.DELETE),
            blocked_capabilities=(SiteCapability.DELETE,),
        )
