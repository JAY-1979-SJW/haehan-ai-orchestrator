"""SiteProfile — 사이트별 정책·메타데이터 정의.

기존 scripts/site_registry.py의 SiteSpec을 대체하지 않는다.
이 모듈은 신규 site_engine 구조를 위한 profile 기반만 제공한다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from scripts.site_engine.site_types import (
    ExecutionLocation,
    GateDecision,
    SiteCapability,
    SiteProfileStatus,
)


@dataclass
class SiteActionPolicy:
    capability: SiteCapability
    gate: GateDecision
    required_execution_location: ExecutionLocation = ExecutionLocation.SERVER
    requires_approval: bool = False
    is_irreversible: bool = False


@dataclass
class SiteProfile:
    key: str
    base_url: str
    display_name: str
    login_domain_hints: Collection[str]
    allowed_capabilities: Collection[SiteCapability]
    blocked_capabilities: Collection[SiteCapability] = field(default_factory=tuple)
    action_policies: Mapping[SiteCapability, SiteActionPolicy] | Sequence[SiteActionPolicy] = field(
        default_factory=tuple
    )
    default_execution_location: ExecutionLocation = ExecutionLocation.SERVER
    login_strategy: str = "registered_only"
    status: SiteProfileStatus = SiteProfileStatus.ACTIVE
    description: str = ""

    def __post_init__(self) -> None:
        _validate_profile(self)

    def get_gate(self, capability: SiteCapability) -> GateDecision:
        policies = self.action_policies.values() if isinstance(self.action_policies, Mapping) else self.action_policies
        for policy in policies:
            if policy.capability == capability:
                return policy.gate
        if capability in self.blocked_capabilities:
            return GateDecision.BLOCKED
        return GateDecision.READ_ONLY_ALLOWED

    def is_capability_allowed(self, capability: SiteCapability) -> bool:
        return capability in self.allowed_capabilities and capability not in self.blocked_capabilities


def _validate_profile(profile: SiteProfile) -> None:
    if not profile.key or not profile.key.strip():
        raise ValueError("SiteProfile.key must not be empty")
    if not profile.base_url or not profile.base_url.startswith(("http://", "https://")):
        raise ValueError(f"SiteProfile.base_url must be a valid URL: {profile.base_url!r}")
    if not profile.display_name or not profile.display_name.strip():
        raise ValueError("SiteProfile.display_name must not be empty")
    if not profile.allowed_capabilities:
        raise ValueError("SiteProfile.allowed_capabilities must not be empty")
    for cap in profile.blocked_capabilities:
        if cap in profile.allowed_capabilities:
            raise ValueError(f"Capability {cap} appears in both allowed and blocked for profile {profile.key!r}")
