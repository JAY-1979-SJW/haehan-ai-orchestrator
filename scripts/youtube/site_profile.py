"""YouTube SiteProfile definition."""
from __future__ import annotations

from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import GateDecision, SiteCapability, SiteProfileStatus

YOUTUBE_PROFILE = SiteProfile(
    key="youtube",
    base_url="https://www.youtube.com",
    display_name="YouTube",
    login_domain_hints=["youtube.com", "accounts.google.com"],
    allowed_capabilities={
        SiteCapability.READ,
        SiteCapability.SEARCH,
        SiteCapability.UPLOAD,
        SiteCapability.PUBLISH,
    },
    blocked_capabilities=set(),
    action_policies={
        SiteCapability.UPLOAD: SiteActionPolicy(
            capability=SiteCapability.UPLOAD,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
        SiteCapability.PUBLISH: SiteActionPolicy(
            capability=SiteCapability.PUBLISH,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
    },
    status=SiteProfileStatus.ACTIVE,
)
