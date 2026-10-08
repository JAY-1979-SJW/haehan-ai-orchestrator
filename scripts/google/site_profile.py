"""Google SiteProfile definition."""
from __future__ import annotations

from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import GateDecision, SiteCapability, SiteProfileStatus

GOOGLE_PROFILE = SiteProfile(
    key="google",
    base_url="https://www.google.com",
    display_name="Google",
    login_domain_hints=["google.com", "accounts.google.com", "gmail.com"],
    allowed_capabilities={
        SiteCapability.READ,
        SiteCapability.SEARCH,
        SiteCapability.SEND,
        SiteCapability.SUBMIT,
        SiteCapability.UPLOAD,
        SiteCapability.PUBLISH,
    },
    blocked_capabilities=set(),
    action_policies={
        SiteCapability.SEND: SiteActionPolicy(
            capability=SiteCapability.SEND,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
        SiteCapability.SUBMIT: SiteActionPolicy(
            capability=SiteCapability.SUBMIT,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
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
        # OAuth/credential 계열 — 사용자 직접 수행 필요 (SIGN capability 사용)
        SiteCapability.SIGN: SiteActionPolicy(
            capability=SiteCapability.SIGN,
            gate=GateDecision.USER_DIRECT_REQUIRED,
            requires_approval=False,
            is_irreversible=False,
        ),
    },
    status=SiteProfileStatus.ACTIVE,
)
