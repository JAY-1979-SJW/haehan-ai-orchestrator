"""Site Access Compatibility Auditor Module.

Read-only auditing of site access policies, authentication methods,
remote access restrictions, and automation capability.
No execution, no credential input, no data modification.
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)


# Automation capability enum
AutomationCapability = Literal[
    "API_ONLY",
    "OAUTH_API_ONLY",
    "SERVER_BROWSER_READONLY_ALLOWED",
    "LOCAL_AGENT_READONLY_ALLOWED",
    "LOCAL_AGENT_USER_APPROVED_CLICK_ALLOWED",
    "USER_PRESENT_LOCAL_ONLY",
    "CONTRACT_ALLOWLIST_REQUIRED",
    "AUTOMATION_BLOCKED",
    "NEEDS_MANUAL_REVIEW",
]

# Final verdict enum
FinalVerdict = Literal[
    "SERVER_READONLY_OK",
    "LOCAL_AGENT_REQUIRED",
    "USER_PRESENT_REQUIRED",
    "API_REQUIRED",
    "OFFICIAL_REMOTE_SUPPORT_REQUIRED",
    "CONTRACT_APPROVAL_REQUIRED",
    "AUTOMATION_BLOCKED",
    "NEEDS_URL_VERIFICATION",
    "NEEDS_MANUAL_SITE_TEST",
]


def build_site_access_audit_target(payload: dict) -> dict:
    """Build site access audit target from payload."""
    return {
        "site_id": payload.get("site_id", ""),
        "site_name": payload.get("site_name", ""),
        "base_domain": payload.get("base_domain", ""),
        "category": payload.get("category", ""),
        "priority": payload.get("priority", 999),
    }


def classify_auth_methods(page_text: str, url: str | None = None) -> dict:
    """Classify authentication methods from page content.

    Read-only detection of auth keywords (no login attempt).
    """
    if not page_text:
        return {
            "detected_methods": [],
            "requires_certificate": False,
            "requires_financial_certificate": False,
            "requires_simple_auth": False,
            "requires_otp": False,
            "requires_captcha": False,
            "requires_security_plugin": False,
        }

    text_lower = page_text.lower()
    methods = []

    # Detection keywords
    if "공동인증서" in text_lower or "공인인증서" in text_lower:
        methods.append("공동인증서")
    if "금융인증서" in text_lower or "금융공동인증서" in text_lower:
        methods.append("금융인증서")
    if "pass" in text_lower or "간편인증" in text_lower:
        methods.append("간편인증")
    if "카카오" in text_lower:
        methods.append("카카오인증")
    if "네이버" in text_lower:
        methods.append("네이버인증")
    if "아이디" in text_lower or "id" in text_lower or "username" in text_lower:
        methods.append("아이디로그인")
    if "oauth" in text_lower:
        methods.append("OAuth")

    # Constraint detection
    has_otp = "otp" in text_lower or "일회용비밀번호" in text_lower or "보안카드" in text_lower
    has_captcha = "captcha" in text_lower or "인증문자" in text_lower
    has_security = "보안프로그램" in text_lower or "키보드보안" in text_lower
    has_2fa = "2fa" in text_lower or "이중인증" in text_lower

    return {
        "detected_methods": methods,
        "requires_certificate": "공동인증서" in methods or "금융인증서" in methods,
        "requires_financial_certificate": "금융인증서" in methods,
        "requires_simple_auth": "간편인증" in methods or "PASS" in methods,
        "requires_otp": has_otp,
        "requires_captcha": has_captcha,
        "requires_security_plugin": has_security,
        "requires_2fa": has_2fa,
    }


def classify_remote_access_restriction(page_text: str) -> dict:
    """Classify remote access restrictions from page content."""
    if not page_text:
        return {
            "blocks_remote_access": False,
            "requires_local_pc": False,
            "requires_security_plugin": False,
            "detected_restrictions": [],
        }

    text_lower = page_text.lower()
    restrictions = []

    blocks_remote = False
    if "원격접속" in text_lower and "차단" in text_lower:
        restrictions.append("원격접속차단")
        blocks_remote = True
    elif "remote access blocked" in text_lower or ("remote access" in text_lower and "blocked" in text_lower):
        restrictions.append("원격접속차단")
        blocks_remote = True

    requires_local = False
    if "로컬" in text_lower or "local pc" in text_lower:
        restrictions.append("로컬PC필수")
        requires_local = True

    return {
        "blocks_remote_access": blocks_remote,
        "requires_local_pc": requires_local,
        "requires_security_plugin": "보안프로그램" in text_lower,
        "detected_restrictions": restrictions,
    }


def evaluate_site_access_policy(payload: dict) -> dict:
    """Evaluate site access and automation policy.

    Args:
        payload: Audit target with site info and optional content

    Returns:
        Audit result dict
    """
    result = {
        "site_id": payload.get("site_id", ""),
        "site_name": payload.get("site_name", ""),
        "base_domain": payload.get("base_domain", ""),
        "category": payload.get("category", ""),
        "requires_login": payload.get("requires_login", True),
        "auth_methods": [],
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_simple_auth": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "blocks_remote_access": False,
        "server_browser_allowed": False,
        "local_agent_required": False,
        "user_present_required": False,
        "automation_capability": "AUTOMATION_BLOCKED",
        "allowed_operations": [],
        "blocked_operations": ["type", "submit", "click"],
        "recommended_route": "USER_DIRECT",
        "final_verdict": "NEEDS_MANUAL_SITE_TEST",
        "audit_status": "PENDING_MANUAL_TEST",
        "safe_to_execute": False,
        "notes": "",
    }

    category = payload.get("category", "").lower()

    # Category-based policy assignment
    if "google" in category:
        result["automation_capability"] = "OAUTH_API_ONLY"
        result["final_verdict"] = "API_REQUIRED"
        result["allowed_operations"] = []
        result["notes"] = "구글 서비스는 OAuth/API 필수"
        return result

    if "certificate" in category or ("auth" in category and "인증서" in payload.get("site_name", "")):
        result["requires_certificate"] = True
        result["automation_capability"] = "USER_PRESENT_LOCAL_ONLY"
        result["final_verdict"] = "USER_PRESENT_REQUIRED"
        result["user_present_required"] = True
        result["allowed_operations"] = []
        result["notes"] = "공동인증서/금융인증서 기반 사이트"
        return result

    if "bank" in category:
        result["requires_certificate"] = True
        result["requires_security_plugin"] = True
        result["blocks_remote_access"] = True
        result["automation_capability"] = "USER_PRESENT_LOCAL_ONLY"
        result["final_verdict"] = "USER_PRESENT_REQUIRED"
        result["user_present_required"] = True
        result["local_agent_required"] = True
        result["allowed_operations"] = []
        result["notes"] = "은행 서비스: 인증서 + 보안프로그램 필수"
        return result

    if "procurement" in category or "g2b" in category or "나라장터" in payload.get("site_name", ""):
        result["requires_login"] = False
        result["automation_capability"] = "SERVER_BROWSER_READONLY_ALLOWED"
        result["final_verdict"] = "SERVER_READONLY_OK"
        result["server_browser_allowed"] = True
        result["allowed_operations"] = ["read", "navigate", "open_url"]
        result["blocked_operations"] = ["type", "submit", "click"]
        result["notes"] = "공개 공고는 read-only 가능, API 지원"
        return result

    if "insurance" in category or "tax" in category or "government" in category:
        result["requires_certificate"] = True
        result["requires_security_plugin"] = True
        result["automation_capability"] = "LOCAL_AGENT_READONLY_ALLOWED"
        result["final_verdict"] = "LOCAL_AGENT_REQUIRED"
        result["local_agent_required"] = True
        result["user_present_required"] = True
        result["allowed_operations"] = ["read", "navigate"]
        result["notes"] = "공공 서비스: 공동인증서 + 로컬 agent 필요"
        return result

    if "card" in category or "payment" in category:
        result["automation_capability"] = "NEEDS_MANUAL_REVIEW"
        result["final_verdict"] = "NEEDS_MANUAL_SITE_TEST"
        result["audit_status"] = "PENDING_MANUAL_TEST"
        result["notes"] = "카드사별 인증 방식 상이, 개별 확인 필요"
        return result

    # Default
    result["audit_status"] = "PENDING_MANUAL_TEST"
    result["notes"] = "자동 분류 불가, 수동 테스트 필요"
    return result


def build_site_access_audit_result(payload: dict) -> dict:
    """Build complete audit result."""
    policy = evaluate_site_access_policy(payload)
    return policy


def validate_site_access_audit_result(result: dict) -> list[str]:
    """Validate audit result."""
    errors = []

    # Required fields
    if "site_id" not in result or not result["site_id"]:
        errors.append("site_id is required")

    if "final_verdict" not in result:
        errors.append("final_verdict is required")

    # Policy enforcement: safe_to_execute must be false
    if result.get("safe_to_execute"):
        errors.append("safe_to_execute must be false")

    # Valid verdicts
    valid_verdicts = {
        "SERVER_READONLY_OK",
        "LOCAL_AGENT_REQUIRED",
        "USER_PRESENT_REQUIRED",
        "API_REQUIRED",
        "OFFICIAL_REMOTE_SUPPORT_REQUIRED",
        "CONTRACT_APPROVAL_REQUIRED",
        "AUTOMATION_BLOCKED",
        "NEEDS_URL_VERIFICATION",
        "NEEDS_MANUAL_SITE_TEST",
    }
    if result.get("final_verdict") not in valid_verdicts:
        errors.append(f"final_verdict must be one of {valid_verdicts}")

    # Capability must be valid
    valid_capabilities = {
        "API_ONLY",
        "OAUTH_API_ONLY",
        "SERVER_BROWSER_READONLY_ALLOWED",
        "LOCAL_AGENT_READONLY_ALLOWED",
        "LOCAL_AGENT_USER_APPROVED_CLICK_ALLOWED",
        "USER_PRESENT_LOCAL_ONLY",
        "CONTRACT_ALLOWLIST_REQUIRED",
        "AUTOMATION_BLOCKED",
        "NEEDS_MANUAL_REVIEW",
    }
    if result.get("automation_capability") not in valid_capabilities:
        errors.append("automation_capability must be valid")

    return errors
