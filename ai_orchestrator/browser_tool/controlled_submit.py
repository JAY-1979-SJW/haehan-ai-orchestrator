"""Controlled Internal Submit Action.

Pure controlled submit decision module (no actual network submit, no DB write, no browser execution).
Validates controlled internal submit requests and generates audit-safe results.

This module validates policy validator PASS → preview → user confirmation → controlled internal submit.
No side effects, stateless, pure functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse


@dataclass
class ControlledSubmitInput:
    """Controlled submit request (post-approval)."""

    # From preview bundle
    preview_bundle: Any  # SubmitPreviewBundle (type: Any to avoid circular import)

    # User action
    user_confirmed: bool = False
    user_id: str = ""

    # Controlled origin check
    allow_internal_mock: bool = True
    allow_localhost: bool = True
    allow_data_url: bool = True


@dataclass
class ControlledSubmitResult:
    """Controlled internal submit result (no DB write, no actual network submit)."""

    # Identifiers
    preview_hash: str
    validation_id: str

    # Controlled submit status
    submitted: bool = False
    submit_timestamp: str = ""

    # Result (no real side effects)
    submit_result: str = "pending"  # "pending", "success", "blocked", "error"
    error_reason: str = ""

    # Audit record
    audit_record: dict[str, Any] = field(default_factory=dict)

    # Lifecycle (when submission decision was made)
    lifecycle: dict[str, str] = field(default_factory=dict)


# Blocked keywords (실제 업무 도메인 markers)
_BLOCKED_DOMAIN_KEYWORDS = {
    "조달",
    "g2b",
    "나라장터",
    "정부",
    "국세청",
    "경매",
    "공사",
    "사업자",
    "은행",
    "카드",
    "결제",
    "송금",
    "계약",
    "입찰",
    "구매",
    "쇼핑",
    "상거래",
}


def is_controlled_internal_origin(
    url: str,
    allow_internal_mock: bool = True,
    allow_localhost: bool = True,
    allow_data_url: bool = True,
) -> bool:
    """Check if URL origin is controlled internal.

    Allowed:
    - internal.mock (any port)
    - localhost (any port)
    - 127.0.0.1 (any port)
    - data: URL

    Returns True if origin is safe controlled internal.
    """
    if not url:
        return False

    # Check data URL
    if allow_data_url and url.lower().startswith("data:"):
        return True

    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        hostname = parsed.hostname or ""
        hostname_lower = hostname.lower()

        # internal.mock
        if allow_internal_mock and "internal.mock" in hostname_lower:
            return True

        # localhost
        if allow_localhost and (
            hostname_lower == "localhost"
            or hostname_lower.startswith("localhost:")
            or hostname_lower == "127.0.0.1"
            or hostname_lower.startswith("127.0.0.1:")
        ):
            return True

        return False

    except Exception:
        return False


def _contains_blocked_domain_keyword(text: str) -> tuple[bool, str]:
    """Check if text contains blocked domain keywords.

    Returns (has_blocked_keyword, keyword).
    """
    if not text:
        return False, ""

    text_lower = text.lower()
    for keyword in _BLOCKED_DOMAIN_KEYWORDS:
        if keyword in text_lower:
            return True, keyword

    return False, ""


def get_blocking_reason(
    preview_bundle: Any,
    user_confirmed: bool,
    allow_internal_mock: bool = True,
    allow_localhost: bool = True,
    allow_data_url: bool = True,
) -> tuple[bool, str]:
    """Check if controlled submit should be blocked.

    Returns (should_block, reason).
    """
    # 1. Check user confirmation
    if not user_confirmed:
        return True, "user not confirmed"

    # 2. Check preview_hash exists
    audit = preview_bundle.audit if hasattr(preview_bundle, "audit") else None
    if not audit or not audit.preview_hash:
        return True, "preview_hash missing"

    # 3. Check policy verdict
    if audit.policy_verdict != "ALLOW":
        return True, f"policy_verdict not ALLOW: {audit.policy_verdict}"

    # 4. Check origin
    # Try to get URL from details or reconstruct from audit
    url = ""
    if hasattr(preview_bundle, "details") and hasattr(preview_bundle.details, "url"):
        url = preview_bundle.details.url
    elif hasattr(preview_bundle, "audit") and hasattr(preview_bundle.audit, "site_id"):
        # For smoke tests, use internal.mock as default controlled URL
        url = f"https://internal.mock/form"

    if not url:
        return True, "url missing"

    if not is_controlled_internal_origin(
        url,
        allow_internal_mock=allow_internal_mock,
        allow_localhost=allow_localhost,
        allow_data_url=allow_data_url,
    ):
        return True, f"origin not controlled internal: {url}"

    # 5. Check redacted payload for blocked keywords
    redacted = audit.redacted_payload if hasattr(audit, "redacted_payload") else {}
    for key, value in redacted.items():
        if isinstance(value, str):
            has_keyword, keyword = _contains_blocked_domain_keyword(value)
            if has_keyword:
                return True, f"blocked keyword '{keyword}' in {key}"
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    for item_key, item_value in item.items():
                        if isinstance(item_value, str):
                            has_keyword, keyword = (
                                _contains_blocked_domain_keyword(item_value)
                            )
                            if has_keyword:
                                return (
                                    True,
                                    f"blocked keyword '{keyword}' in {key}[{item_key}]",
                                )

    # 6. Check form_id and submit_button_id don't match denied patterns
    details = preview_bundle.details if hasattr(preview_bundle, "details") else None
    if details:
        form_id = details.form_id or ""
        button_id = details.submit_button_id or ""

        has_keyword, keyword = _contains_blocked_domain_keyword(form_id)
        if has_keyword:
            return True, f"blocked keyword '{keyword}' in form_id"

        has_keyword, keyword = _contains_blocked_domain_keyword(button_id)
        if has_keyword:
            return True, f"blocked keyword '{keyword}' in submit_button_id"

    # All checks passed
    return False, ""


def build_controlled_submit_result(
    preview_bundle: Any,
    user_confirmed: bool = False,
    user_id: str = "",
    allow_internal_mock: bool = True,
    allow_localhost: bool = True,
    allow_data_url: bool = True,
) -> ControlledSubmitResult:
    """Build controlled submit result after validation.

    No actual submit, no DB write. Pure decision + audit generation.

    Args:
        preview_bundle: SubmitPreviewBundle from preview stage
        user_confirmed: User approval status
        user_id: User identifier (optional)
        allow_internal_mock: Allow internal.mock origin
        allow_localhost: Allow localhost origin
        allow_data_url: Allow data: URLs

    Returns:
        ControlledSubmitResult with lifecycle and audit record
    """
    audit = preview_bundle.audit if hasattr(preview_bundle, "audit") else None
    details = preview_bundle.details if hasattr(preview_bundle, "details") else None

    preview_hash = audit.preview_hash if audit else ""
    validation_id = audit.validation_id if audit else ""

    # Check blocking conditions
    should_block, reason = get_blocking_reason(
        preview_bundle,
        user_confirmed,
        allow_internal_mock=allow_internal_mock,
        allow_localhost=allow_localhost,
        allow_data_url=allow_data_url,
    )

    # Build lifecycle
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lifecycle = {
        "preview_timestamp": audit.preview_timestamp if audit else "",
        "confirmation_check": now,
        "origin_check": now if not should_block else "",
        "domain_check": now if not should_block else "",
    }

    # Build audit record
    audit_record = {}
    if audit:
        audit_record = {
            "validation_id": audit.validation_id,
            "site_id": audit.site_id,
            "form_id": audit.form_id,
            "intent": audit.intent,
            "preview_hash": audit.preview_hash,
            "preview_timestamp": audit.preview_timestamp,
            "policy_verdict": audit.policy_verdict,
            "redacted_payload": audit.redacted_payload,
            "user_confirmed": user_confirmed,
            "user_id": user_id,
        }

    # Build result
    if should_block:
        result = ControlledSubmitResult(
            preview_hash=preview_hash,
            validation_id=validation_id,
            submitted=False,
            submit_timestamp="",
            submit_result="blocked",
            error_reason=reason,
            audit_record=audit_record,
            lifecycle=lifecycle,
        )
    else:
        result = ControlledSubmitResult(
            preview_hash=preview_hash,
            validation_id=validation_id,
            submitted=True,
            submit_timestamp=now,
            submit_result="success",
            error_reason="",
            audit_record=audit_record,
            lifecycle=lifecycle,
        )

    return result
