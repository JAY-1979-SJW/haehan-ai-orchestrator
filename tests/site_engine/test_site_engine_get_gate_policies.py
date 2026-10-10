"""SiteProfile.get_gate — action_policies 의 dict·tuple 양쪽 지원 시험 (순수 데이터)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from scripts.gabia.site_profile import GABIA_PROFILE
from scripts.google.site_profile import GOOGLE_PROFILE
from scripts.hiworks.site_profile import HIWORKS_PROFILE
from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import GateDecision, SiteCapability
from scripts.youtube.site_profile import YOUTUBE_PROFILE

_CAPS = list(SiteCapability)
_READ = _CAPS[0]
_SUBMIT = _CAPS[1]
_OTHER = _CAPS[2]
_BLOCKED = _CAPS[3]


def _policies() -> list[SiteActionPolicy]:
    return [SiteActionPolicy(capability=_SUBMIT, gate=GateDecision.APPROVAL_REQUIRED)]


def _make(policies: Mapping[SiteCapability, SiteActionPolicy] | Sequence[SiteActionPolicy]) -> SiteProfile:
    return SiteProfile(
        key="t",
        base_url="https://example.com",
        display_name="T",
        login_domain_hints=("example.com",),
        allowed_capabilities=(_READ, _SUBMIT, _OTHER),
        blocked_capabilities=(_BLOCKED,),
        action_policies=policies,
    )


def _as_dict() -> SiteProfile:
    return _make({p.capability: p for p in _policies()})


def _as_tuple() -> SiteProfile:
    return _make(tuple(_policies()))


def test_dict_policies_return_gate() -> None:
    assert _as_dict().get_gate(_SUBMIT) == GateDecision.APPROVAL_REQUIRED


def test_dict_and_tuple_equivalent() -> None:
    d, t = _as_dict(), _as_tuple()
    for cap in _CAPS:
        assert d.get_gate(cap) == t.get_gate(cap)


@pytest.mark.parametrize("factory", [_as_dict, _as_tuple])
def test_no_policy_falls_back(factory) -> None:
    p = factory()
    assert p.get_gate(_BLOCKED) == GateDecision.BLOCKED
    assert p.get_gate(_OTHER) == GateDecision.READ_ONLY_ALLOWED


@pytest.mark.parametrize("empty", [{}, ()])
def test_empty_policies(empty) -> None:
    p = _make(empty)
    assert p.get_gate(_BLOCKED) == GateDecision.BLOCKED
    assert p.get_gate(_READ) == GateDecision.READ_ONLY_ALLOWED


@pytest.mark.parametrize("profile", [YOUTUBE_PROFILE, HIWORKS_PROFILE, GOOGLE_PROFILE, GABIA_PROFILE])
def test_real_profiles(profile: SiteProfile) -> None:
    for cap in list(profile.allowed_capabilities) + list(profile.blocked_capabilities):
        assert isinstance(profile.get_gate(cap), GateDecision)
    policies = profile.action_policies
    values = policies.values() if isinstance(policies, Mapping) else policies
    for pol in values:
        assert profile.get_gate(pol.capability) == pol.gate


def test_gabia_submit_requires_approval() -> None:
    assert GABIA_PROFILE.get_gate(SiteCapability.SUBMIT) == GateDecision.APPROVAL_REQUIRED
