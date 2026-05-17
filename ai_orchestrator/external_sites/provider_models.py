"""External Site Provider 데이터 모델.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

금지 필드:
    password, otp, token, cookie, session, credential, private_key
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 상태/위험/카테고리 상수
# ---------------------------------------------------------------------------

RISK_CRITICAL = "CRITICAL"
RISK_HIGH     = "HIGH"
RISK_MEDIUM   = "MEDIUM"
RISK_LOW      = "LOW"

STATUS_CURRENT            = "CURRENT"
STATUS_PLANNED            = "PLANNED"
STATUS_HOLD               = "HOLD"
STATUS_LEGACY             = "LEGACY"

CAT_DOMAIN_DNS            = "DOMAIN_DNS_PROVIDER"
CAT_SOCIAL_LOGIN          = "SOCIAL_LOGIN_PROVIDER"
CAT_PORTAL_LOGIN          = "PORTAL_LOGIN_PROVIDER"
CAT_COMMERCE              = "COMMERCE_WORK_SITE"
CAT_OFFICIAL_API          = "OFFICIAL_API_PROVIDER"
CAT_GROUPWARE             = "GROUPWARE_MAIL_SITE"
CAT_PUBLIC_BID            = "PUBLIC_BID_WORK_SITE"
CAT_PUBLIC_ADMIN          = "PUBLIC_ADMIN_SITE"
CAT_EMAIL                 = "EMAIL_GENERIC"
CAT_BANK                  = "BANK_GENERIC"

AUTOMATION_PLANNED            = "PLANNED"
AUTOMATION_PLANNED_USER       = "PLANNED_WITH_USER_PRESENT_LOGIN"
AUTOMATION_PLANNED_CERT       = "PLANNED_WITH_CERT_USER_PRESENT"
AUTOMATION_PLANNED_API        = "PLANNED_OFFICIAL_API_FIRST"
AUTOMATION_RECOVERED          = "RECOVERED"
AUTOMATION_LOGIN_ONLY         = "LOGIN_PROVIDER_ONLY"
AUTOMATION_LOGIN_GABIA        = "CURRENT_FOR_GABIA_LOGIN"


# ---------------------------------------------------------------------------
# SiteProviderEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SiteProviderEntry:
    provider_id: str
    display_name: str
    category: str
    primary_url: str
    login_url: str
    management_url: str
    official_navigation_required: bool
    guessed_url_allowed: bool
    user_present_login_required: bool
    desktop_app_required: bool
    server_remote_login_allowed: bool
    cookie_storage_allowed: bool
    token_storage_allowed: bool
    browser_profile_reuse_allowed: bool
    official_api_preferred: bool
    cdp_browser_allowed: bool
    headless_allowed: bool
    approval_gate_required: bool
    certificate_login_required: bool
    high_risk_actions: tuple[str, ...]
    allowed_automation_scope: tuple[str, ...]
    forbidden_automation_scope: tuple[str, ...]
    navigation_status: str
    automation_status: str
    risk_level: str
    current_status: str
    notes: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "category": self.category,
            "primary_url": self.primary_url,
            "login_url": self.login_url,
            "management_url": self.management_url,
            "official_navigation_required": self.official_navigation_required,
            "guessed_url_allowed": self.guessed_url_allowed,
            "user_present_login_required": self.user_present_login_required,
            "desktop_app_required": self.desktop_app_required,
            "server_remote_login_allowed": self.server_remote_login_allowed,
            "cookie_storage_allowed": self.cookie_storage_allowed,
            "token_storage_allowed": self.token_storage_allowed,
            "browser_profile_reuse_allowed": self.browser_profile_reuse_allowed,
            "official_api_preferred": self.official_api_preferred,
            "cdp_browser_allowed": self.cdp_browser_allowed,
            "headless_allowed": self.headless_allowed,
            "approval_gate_required": self.approval_gate_required,
            "certificate_login_required": self.certificate_login_required,
            "high_risk_actions": list(self.high_risk_actions),
            "allowed_automation_scope": list(self.allowed_automation_scope),
            "forbidden_automation_scope": list(self.forbidden_automation_scope),
            "navigation_status": self.navigation_status,
            "automation_status": self.automation_status,
            "risk_level": self.risk_level,
            "current_status": self.current_status,
            "notes": self.notes,
        }


__all__ = [
    "SiteProviderEntry",
    "RISK_CRITICAL", "RISK_HIGH", "RISK_MEDIUM", "RISK_LOW",
    "STATUS_CURRENT", "STATUS_PLANNED", "STATUS_HOLD", "STATUS_LEGACY",
    "CAT_DOMAIN_DNS", "CAT_SOCIAL_LOGIN", "CAT_PORTAL_LOGIN",
    "CAT_COMMERCE", "CAT_OFFICIAL_API", "CAT_GROUPWARE",
    "CAT_PUBLIC_BID", "CAT_PUBLIC_ADMIN", "CAT_EMAIL", "CAT_BANK",
    "AUTOMATION_PLANNED", "AUTOMATION_PLANNED_USER", "AUTOMATION_PLANNED_CERT",
    "AUTOMATION_PLANNED_API", "AUTOMATION_RECOVERED", "AUTOMATION_LOGIN_ONLY",
    "AUTOMATION_LOGIN_GABIA",
]
