"""Browser Site Compliance Policy Module.

Pre-flight site compliance check for browser automation requests.
Evaluates target domain/site against remote access and automation policies
before dispatch without executing.
Read-only, no execution, no DB write.
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)


# Site automation capability enum
SiteCapability = Literal[
    "API_ONLY",
    "OAUTH_API_ONLY",
    "WORKSPACE_ADMIN_DELEGATED_API",
    "USER_PRESENT_LOCAL_ONLY",
    "OFFICIAL_REMOTE_SUPPORT_ONLY",
    "BROWSER_READONLY_ALLOWED",
    "CDP_READ_ONLY",
    "BROWSER_CONTROLLED_CLICK_ALLOWED",
    "CONTRACT_ALLOWLIST_REQUIRED",
    "AUTOMATION_BLOCKED",
    "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
]

# Compliance decision enum
ComplianceDecision = Literal[
    "ALLOW_BROWSER_READONLY",
    "REQUIRE_API_CONNECTOR",
    "REQUIRE_USER_PRESENT_LOCAL",
    "REQUIRE_OFFICIAL_REMOTE_SUPPORT",
    "REQUIRE_SITE_OWNER_APPROVAL",
    "BLOCK",
]

# Google domain patterns and policies
GOOGLE_SERVICE_POLICIES = {
    "accounts.google.com": {
        "capability": "AUTOMATION_BLOCKED",
        "site_type": "google_authentication",
        "browser_automation_allowed": False,
        "api_connector_required": False,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": "GOOGLE_LOGIN_AUTOMATION_BLOCKED",
        "message_ko": "Google 로그인: 자동화 금지, OAuth consent 필요",
    },
    "mail.google.com": {
        "capability": "CDP_READ_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": True,
        "api_connector_required": False,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": None,
        "message_ko": "Gmail: CDP 세션 로그인 상태에서 읽기 허용",
    },
    "drive.google.com": {
        "capability": "OAUTH_API_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": False,
        "api_connector_required": True,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": "OAUTH_API_REQUIRED",
        "message_ko": "Google Drive: OAuth API 필수, 브라우저 자동화 차단",
    },
    "calendar.google.com": {
        "capability": "OAUTH_API_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": False,
        "api_connector_required": True,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": "OAUTH_API_REQUIRED",
        "message_ko": "Google Calendar: OAuth API 필수, 브라우저 자동화 차단",
    },
    "docs.google.com": {
        "capability": "OAUTH_API_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": False,
        "api_connector_required": True,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": "OAUTH_API_REQUIRED",
        "message_ko": "Google Docs: OAuth API 필수, 브라우저 자동화 차단",
    },
    "sheets.google.com": {
        "capability": "OAUTH_API_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": False,
        "api_connector_required": True,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": "OAUTH_API_REQUIRED",
        "message_ko": "Google Sheets: OAuth API 필수, 브라우저 자동화 차단",
    },
    "remotedesktop.google.com": {
        "capability": "OFFICIAL_REMOTE_SUPPORT_ONLY",
        "site_type": "google_service",
        "browser_automation_allowed": False,
        "api_connector_required": False,
        "user_present_required": True,
        "site_owner_approval_required": False,
        "official_remote_support_required": True,
        "block_reason": "OFFICIAL_REMOTE_SUPPORT_REQUIRED",
        "message_ko": "Chrome Remote Desktop: 공식 원격지원 도구만 허용",
    },
}

# Allowlist-safe sites (read-only browsing allowed)
ALLOWLIST_SAFE_SITES = {
    "example.com",
    "g2b.go.kr",  # G2B 나라장터 apex domain
    "www.g2b.go.kr",  # G2B 나라장터 www prefix (apex와 동일 공개 서비스)
}

# Default policy for unknown sites
DEFAULT_POLICY = {
    "capability": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
    "site_type": "unknown",
    "browser_automation_allowed": False,
    "api_connector_required": False,
    "user_present_required": False,
    "site_owner_approval_required": False,
    "official_remote_support_required": False,
    "block_reason": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
    "message_ko": "미지의 사이트: 법률검토 또는 사이트 소유자 승인 필요",
}

# Default policy for allowlist-safe sites
ALLOWLIST_SAFE_POLICY = {
    "capability": "BROWSER_READONLY_ALLOWED",
    "site_type": "allowlist_safe",
    "browser_automation_allowed": True,
    "api_connector_required": False,
    "user_present_required": False,
    "site_owner_approval_required": False,
    "official_remote_support_required": False,
    "block_reason": None,
    "message_ko": "허용 사이트: 읽기 전용 브라우저 자동화 허용",
}


def _normalize_domain(domain: str | None) -> str:
    """Normalize domain for policy lookup."""
    if not domain:
        return ""
    return domain.lower().strip()


def get_site_compliance_policy(
    target_domain: str | None,
    site_type: str | None = None,
) -> dict:
    """Get site compliance policy from domain or site type.

    Args:
        target_domain: Target domain (e.g., "mail.google.com")
        site_type: Site type hint (e.g., "google_service")

    Returns:
        Site compliance policy dict with capability, browser_automation_allowed, etc.
    """
    domain = _normalize_domain(target_domain)

    # Check Google service policies first
    if domain in GOOGLE_SERVICE_POLICIES:
        return GOOGLE_SERVICE_POLICIES[domain]

    # Check allowlist-safe sites
    if domain in ALLOWLIST_SAFE_SITES:
        return ALLOWLIST_SAFE_POLICY.copy()

    # Check Google domain by pattern
    if "google.com" in domain or (site_type and "google" in site_type.lower()):
        # Unknown Google domain → require approval
        return {
            "capability": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
            "site_type": "google_service_unknown",
            "browser_automation_allowed": False,
            "api_connector_required": False,
            "user_present_required": False,
            "site_owner_approval_required": False,
            "official_remote_support_required": False,
            "block_reason": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
            "message_ko": f"{domain}: Google 서비스 미확인, 법률검토 필요",
        }

    # Default policy for unknown sites
    return DEFAULT_POLICY.copy()


def _cap_automation_blocked(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    result["compliance_decision"] = "BLOCK"
    result["safe_to_dispatch"] = False


def _cap_api_connector(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    result["compliance_decision"] = "REQUIRE_API_CONNECTOR"
    result["safe_to_dispatch"] = False


def _cap_user_present_local(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    if user_present:
        result["compliance_decision"] = "ALLOW_BROWSER_READONLY"
        result["safe_to_dispatch"] = True
    else:
        result["compliance_decision"] = "REQUIRE_USER_PRESENT_LOCAL"
        result["block_reason"] = "USER_PRESENT_REQUIRED"
        result["safe_to_dispatch"] = False


def _cap_official_remote_support(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    if payload.get("remote_support_user_approved"):
        result["compliance_decision"] = "REQUIRE_OFFICIAL_REMOTE_SUPPORT"
        result["safe_to_dispatch"] = False
    else:
        result["compliance_decision"] = "REQUIRE_OFFICIAL_REMOTE_SUPPORT"
        result["block_reason"] = "OFFICIAL_REMOTE_SUPPORT_REQUIRED"
        result["safe_to_dispatch"] = False


def _cap_browser_readonly(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    # Only allow read and navigate operations
    if operation_type in {"read", "navigate", "open_url"}:
        result["compliance_decision"] = "ALLOW_BROWSER_READONLY"
        result["safe_to_dispatch"] = True
    else:
        result["compliance_decision"] = "BLOCK"
        result["block_reason"] = "OPERATION_NOT_ALLOWED_FOR_READONLY_SITE"
        result["safe_to_dispatch"] = False


def _cap_browser_controlled_click(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    if operation_type in {"read", "navigate", "open_url", "click"}:
        result["compliance_decision"] = "ALLOW_BROWSER_READONLY"
        result["safe_to_dispatch"] = True
    else:
        result["compliance_decision"] = "BLOCK"
        result["block_reason"] = "OPERATION_NOT_ALLOWED"
        result["safe_to_dispatch"] = False


def _cap_contract_allowlist(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    if payload.get("site_owner_approval_id"):
        result["compliance_decision"] = "REQUIRE_SITE_OWNER_APPROVAL"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{target_domain}: 사이트 소유자 승인 있음"
    else:
        result["compliance_decision"] = "REQUIRE_SITE_OWNER_APPROVAL"
        result["block_reason"] = "SITE_OWNER_APPROVAL_REQUIRED"
        result["safe_to_dispatch"] = False


def _cap_needs_legal_approval(result: dict, payload: dict, target_domain: str, operation_type: str, user_present: bool) -> None:
    result["compliance_decision"] = "BLOCK"
    result["block_reason"] = "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"
    result["safe_to_dispatch"] = False


# capability → 판정 핸들러 (정의되지 않은 capability 는 UNKNOWN_CAPABILITY BLOCK)
_CAPABILITY_HANDLERS = {
    "AUTOMATION_BLOCKED": _cap_automation_blocked,
    "OAUTH_API_ONLY": _cap_api_connector,
    "API_ONLY": _cap_api_connector,
    "WORKSPACE_ADMIN_DELEGATED_API": _cap_api_connector,
    "USER_PRESENT_LOCAL_ONLY": _cap_user_present_local,
    "OFFICIAL_REMOTE_SUPPORT_ONLY": _cap_official_remote_support,
    "BROWSER_READONLY_ALLOWED": _cap_browser_readonly,
    # CDP_READ_ONLY(Gmail): 읽기·이동만 허용, 그 외 작업은 fail-closed BLOCK (재사용)
    "CDP_READ_ONLY": _cap_browser_readonly,
    "BROWSER_CONTROLLED_CLICK_ALLOWED": _cap_browser_controlled_click,
    "CONTRACT_ALLOWLIST_REQUIRED": _cap_contract_allowlist,
    "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL": _cap_needs_legal_approval,
}


def evaluate_site_compliance(payload: dict) -> dict:
    """Evaluate site compliance preflight decision.

    Args:
        payload: Site compliance check payload with:
            - target_domain, target_url, target_path (context)
            - action_name, operation_type (request)
            - user_present, production_mode (execution context)
            - workflow_id, workflow_run_id (tracing)
            - user_id, site_id, tenant_id (identity)
            - official_api_available, oauth_available, workspace_admin_delegated (hints)
            - site_owner_approval_id, remote_support_user_approved (approvals)

    Returns:
        Dict with site compliance decision and context
    """
    result = {
        "target_domain": payload.get("target_domain", ""),
        "target_url": payload.get("target_url", ""),
        "site_type": "",
        "compliance_decision": "BLOCK",
        "site_capability": "AUTOMATION_BLOCKED",
        "browser_automation_allowed": False,
        "api_connector_required": False,
        "user_present_required": False,
        "site_owner_approval_required": False,
        "official_remote_support_required": False,
        "block_reason": None,
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "message_ko": "",
    }

    target_domain = _normalize_domain(payload.get("target_domain"))
    operation_type = payload.get("operation_type", "").lower()
    user_present = payload.get("user_present", False)
    production_mode = payload.get("production_mode", False)

    # Check production mode first
    if production_mode:
        result["compliance_decision"] = "BLOCK"
        result["block_reason"] = "PRODUCTION_MODE_BLOCKED"
        result["message_ko"] = f"{target_domain}: production mode 차단"
        return result

    # Get site compliance policy
    policy = get_site_compliance_policy(target_domain)
    result["site_type"] = policy.get("site_type", "")
    result["site_capability"] = policy.get("capability", "")
    result["browser_automation_allowed"] = policy.get("browser_automation_allowed", False)
    result["api_connector_required"] = policy.get("api_connector_required", False)
    result["user_present_required"] = policy.get("user_present_required", False)
    result["site_owner_approval_required"] = policy.get("site_owner_approval_required", False)
    result["official_remote_support_required"] = policy.get("official_remote_support_required", False)
    result["block_reason"] = policy.get("block_reason")
    result["message_ko"] = policy.get("message_ko", "")

    capability = policy.get("capability", "AUTOMATION_BLOCKED")

    # Route based on capability
    handler = _CAPABILITY_HANDLERS.get(capability)
    if handler is not None:
        handler(result, payload, target_domain, operation_type, user_present)
        return result

    # Fallback
    result["compliance_decision"] = "BLOCK"
    result["block_reason"] = "UNKNOWN_CAPABILITY"
    result["safe_to_dispatch"] = False
    return result


def validate_site_compliance_result(result: dict) -> list[str]:
    """Validate site compliance result.

    Args:
        result: Result from evaluate_site_compliance()

    Returns:
        List of error messages (empty = valid)
    """
    errors = []

    # Required fields
    if "compliance_decision" not in result:
        errors.append("compliance_decision is required")

    if "site_capability" not in result:
        errors.append("site_capability is required")

    # Policy enforcement: safe_to_execute must be false
    if result.get("safe_to_execute"):
        errors.append("safe_to_execute must be false")

    # Capability must be valid
    valid_capabilities = {
        "API_ONLY",
        "OAUTH_API_ONLY",
        "WORKSPACE_ADMIN_DELEGATED_API",
        "USER_PRESENT_LOCAL_ONLY",
        "OFFICIAL_REMOTE_SUPPORT_ONLY",
        "BROWSER_READONLY_ALLOWED",
        "CDP_READ_ONLY",
        "BROWSER_CONTROLLED_CLICK_ALLOWED",
        "CONTRACT_ALLOWLIST_REQUIRED",
        "AUTOMATION_BLOCKED",
        "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL",
    }
    if result.get("site_capability") not in valid_capabilities:
        errors.append(f"site_capability must be one of {valid_capabilities}")

    # Compliance decision must be valid
    valid_decisions = {
        "ALLOW_BROWSER_READONLY",
        "REQUIRE_API_CONNECTOR",
        "REQUIRE_USER_PRESENT_LOCAL",
        "REQUIRE_OFFICIAL_REMOTE_SUPPORT",
        "REQUIRE_SITE_OWNER_APPROVAL",
        "BLOCK",
    }
    if result.get("compliance_decision") not in valid_decisions:
        errors.append(f"compliance_decision must be one of {valid_decisions}")

    return errors
