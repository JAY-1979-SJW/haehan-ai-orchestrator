"""Hiworks SiteProfile definition."""
from __future__ import annotations

from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import GateDecision, SiteCapability, SiteProfileStatus

HIWORKS_PROFILE = SiteProfile(
    key="hiworks",
    base_url="https://www.hiworks.com",
    display_name="Hiworks",
    login_domain_hints=["hiworks.com"],
    allowed_capabilities={
        SiteCapability.READ,
        SiteCapability.SEARCH,
        SiteCapability.FORM_FILL,
        SiteCapability.SUBMIT,
        SiteCapability.SEND,
    },
    blocked_capabilities=set(),
    action_policies={
        SiteCapability.SUBMIT: SiteActionPolicy(
            capability=SiteCapability.SUBMIT,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
        SiteCapability.SEND: SiteActionPolicy(
            capability=SiteCapability.SEND,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
    },
    status=SiteProfileStatus.ACTIVE,
)
