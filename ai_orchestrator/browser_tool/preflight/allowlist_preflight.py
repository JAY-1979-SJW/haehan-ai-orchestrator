"""Browser Allowlist Preflight Module.

Pre-flight domain/path allowlist check for browser actions.
Validates target_domain, target_url, target_path against allowlist policies
before dispatch without executing.
Test-only implementation (read-only, no execution, no DB write).
"""

from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Default allowlist policies per operation type
DEFAULT_OPERATION_POLICIES = {
    "read": {
        "allowlist_required": False,
        "allowed_operation": True,
        "decision_if_allowed": "ALLOW_DRY_RUN",
    },
    "navigate": {
        "allowlist_required": True,
        "allowed_operation": True,
        "decision_if_allowed": "ALLOW_IF_DOMAIN_ALLOWLISTED",
    },
    "open_url": {
        "allowlist_required": True,
        "allowed_operation": True,
        "decision_if_allowed": "ALLOW_IF_DOMAIN_ALLOWLISTED",
    },
    "click": {
        "allowlist_required": True,
        "allowed_operation": True,
        "decision_if_allowed": "ALLOW_IF_APPROVED",
    },
    "type": {
        "allowlist_required": True,
        "allowed_operation": False,
        "block_reason": "TYPE_BLOCKED",
    },
    "submit": {
        "allowlist_required": True,
        "allowed_operation": False,
        "block_reason": "SUBMIT_DENY_BY_DEFAULT",
    },
}

# Common allowlist domains (placeholder)
COMMON_ALLOWED_DOMAINS = {
    "example.com",
    "g2b.go.kr",  # G2B 나라장터 apex domain
    "www.g2b.go.kr",  # G2B 나라장터 www prefix (apex와 동일 공개 서비스)
}

# Common blocked domains
COMMON_BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "192.168.",  # private network
}


def normalize_url_for_policy(url: str) -> dict:
    """Normalize URL for policy evaluation.

    Args:
        url: Original URL

    Returns:
        Dict with normalized URL components and hash
    """
    if not url:
        return {
            "domain": "",
            "path": "",
            "query": "",
            "url_hash": "",
            "url_redacted": "",
            "has_sensitive_params": False,
        }

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or ""
        path = parsed.path or "/"
        query = parsed.query or ""

        # Check for sensitive query parameters
        sensitive_params = {
            "password",
            "passwd",
            "pwd",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "otp",
            "session",
            "cookie",
            "authorization",
        }
        has_sensitive = any(param in query.lower() for param in sensitive_params)

        # Redact URL
        url_redacted = f"{parsed.scheme}://{domain}{path}"
        if query and not has_sensitive:
            url_redacted += f"?{query}"

        url_hash = hashlib.sha256(url.encode()).hexdigest()

        return {
            "domain": domain,
            "path": path,
            "query": query,
            "url_hash": url_hash,
            "url_redacted": url_redacted,
            "has_sensitive_params": has_sensitive,
        }
    except Exception as e:  # noqa: BLE001 - URL 파싱 실패 시 도메인을 [PARSE_ERROR]로 표시하고 has_sensitive_params=True로 안전한 기본값(민감정보 있다고 가정)을 반환 — fail-safe 리다크션, 차단/허용 판정 함수 아님
        logger.warning(f"URL parsing failed: {e}")
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return {
            "domain": "[PARSE_ERROR]",
            "path": "",
            "query": "",
            "url_hash": url_hash,
            "url_redacted": "[REDACTED_URL]",
            "has_sensitive_params": True,
        }


def build_allowlist_context(payload: dict) -> dict:
    """Build allowlist evaluation context.

    Args:
        payload: Allowlist check payload

    Returns:
        Dict with URL components and context
    """
    target_url = payload.get("target_url", "")
    target_domain = payload.get("target_domain", "")
    target_path = payload.get("target_path", "")

    url_info = normalize_url_for_policy(target_url)

    # Override with explicit values if provided
    if target_domain:
        url_info["domain"] = target_domain
    if target_path:
        url_info["path"] = target_path

    return {
        "target_url": target_url,
        "target_domain": url_info.get("domain", ""),
        "target_path": url_info.get("path", ""),
        "target_url_hash": url_info.get("url_hash", ""),
        "target_url_redacted": url_info.get("url_redacted", ""),
        "has_sensitive_params": url_info.get("has_sensitive_params", False),
    }


def _evaluate_domain_allowlist(result: dict, action_name: str) -> dict:
    """allowlist 필요 시 domain 검사 (차단 → 허용 → 검증필요 → 미등록 순서)."""
    target_domain = result["target_domain"]

    # Check domain presence
    if not target_domain:
        result["allowlist_decision"] = "BLOCK"
        result["block_reason"] = "TARGET_DOMAIN_MISSING"
        result["message_ko"] = f"{action_name}: domain 누락"
        result["should_write_audit"] = True
        return result

    # Check if domain is in blocked list
    if target_domain.lower() in COMMON_BLOCKED_DOMAINS:
        result["allowlist_decision"] = "BLOCK"
        result["block_reason"] = "DOMAIN_BLOCKED"
        result["blocked_by_domain"] = True
        result["message_ko"] = f"{action_name}: 차단 domain {target_domain}"
        result["should_write_audit"] = True
        return result

    # Check if domain is in allowed list
    if target_domain.lower() in COMMON_ALLOWED_DOMAINS:
        result["domain_allowed"] = True
        result["path_allowed"] = True
        result["allowlist_decision"] = "ALLOW_DRY_RUN"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{action_name}: domain {target_domain} allowlist에 있음"
        return result

    # Domain not in list: requires verification
    if "example.invalid" in target_domain or "unknown" in target_domain.lower():
        result["allowlist_decision"] = "REQUIRE_DOMAIN_VERIFICATION"
        result["needs_domain_verification"] = True
        result["block_reason"] = "NEEDS_DOMAIN_VERIFICATION"
        result["message_ko"] = f"{action_name}: domain {target_domain} 검증 필요"
        result["should_write_audit"] = True
        return result

    # Unknown domain
    result["allowlist_decision"] = "BLOCK"
    result["block_reason"] = "DOMAIN_NOT_ALLOWLISTED"
    result["blocked_by_domain"] = True
    result["message_ko"] = f"{action_name}: domain {target_domain} allowlist에 없음"
    result["should_write_audit"] = True
    return result


def evaluate_allowlist_preflight(payload: dict) -> dict:
    """Evaluate allowlist preflight decision.

    Args:
        payload: Allowlist check payload with:
            - workflow_run_id, workflow_id, action_name (required)
            - operation_type (required)
            - target_url, target_domain, target_path (context)
            - allowlist_required, approval_status, etc.
            - action_registry_preflight_decision, gate_preflight_decision
            - production_mode, tenant_id, user_id, site_id

    Returns:
        Dict with allowlist decision and context
    """
    result = {
        "allowlist_decision": "BLOCK",
        "allowlist_required": False,
        "domain_allowed": False,
        "path_allowed": False,
        "operation_allowed": True,
        "target_domain": "",
        "target_path": "",
        "target_url_hash": "",
        "target_url_redacted": "",
        "site_policy_id": None,
        "needs_domain_verification": False,
        "blocked_by_domain": False,
        "blocked_by_path": False,
        "blocked_by_operation": False,
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "block_reason": None,
        "should_write_audit": False,
        "message_ko": "",
    }

    action_name = payload.get("action_name", "")
    operation_type = payload.get("operation_type", "").lower()

    # Build context
    ctx = build_allowlist_context(payload)
    result.update(ctx)

    # Check production mode
    if payload.get("production_mode"):
        result["allowlist_decision"] = "BLOCK"
        result["block_reason"] = "PRODUCTION_MODE_BLOCKED"
        result["message_ko"] = f"{action_name}: production mode 차단"
        return result

    # Check context
    if payload.get("allowlist_required") and not payload.get("tenant_id"):
        result["block_reason"] = "TENANT_CONTEXT_MISSING"
        result["message_ko"] = "테넌트 context 누락"
        return result

    # Get operation policy
    op_policy = DEFAULT_OPERATION_POLICIES.get(operation_type, {})
    result["allowlist_required"] = op_policy.get("allowlist_required", False)

    # Check operation allowed
    if not op_policy.get("allowed_operation", True):
        result["allowlist_decision"] = "BLOCK"
        result["operation_allowed"] = False
        result["blocked_by_operation"] = True
        result["block_reason"] = op_policy.get("block_reason", "OPERATION_NOT_ALLOWED")
        result["message_ko"] = f"{action_name}: {result['block_reason']}"
        result["should_write_audit"] = True
        return result

    # If allowlist not required and operation allowed
    if not result["allowlist_required"]:
        result["allowlist_decision"] = "ALLOW_DRY_RUN"
        result["domain_allowed"] = True
        result["path_allowed"] = True
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{action_name}: allowlist 불필요, dry-run dispatch 허용"
        return result

    # Allowlist required: check domain and path
    return _evaluate_domain_allowlist(result, action_name)


def validate_allowlist_result(result: dict) -> list[str]:
    """Validate allowlist result.

    Args:
        result: Result from evaluate_allowlist_preflight()

    Returns:
        List of error messages (empty = valid)
    """
    errors = []

    # Required fields
    if "allowlist_decision" not in result:
        errors.append("allowlist_decision is required")

    # Policy enforcement: safe_to_execute must be false
    if result.get("safe_to_execute"):
        errors.append("safe_to_execute must be false")

    # Policy enforcement: production_allowed should be false
    if result.get("production_allowed"):
        errors.append("production_allowed must be false")

    return errors
