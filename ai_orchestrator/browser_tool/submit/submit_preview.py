"""Browser Submit Preview Schema.

Pure preview generation module (no browser execution, no network calls, no DB).
Generates preview data for user approval before submit execution.

This module contains ONLY preview schema and generation logic.
No side effects, stateless, pure functions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubmitPreviewInput:
    """Input for preview generation."""

    # From validation request
    site_id: str
    form_id: str
    submit_button_id: str
    intent: str
    fields: list[dict] = field(default_factory=list)
    hidden_fields: list[dict] = field(default_factory=list)

    # From validation result
    policy_verdict: str = "DENY"
    validation_id: str = ""
    risk_level: str = "high"


@dataclass
class UserPreviewSummary:
    """User-facing approval summary."""

    # Basic info
    site_id: str
    form_title: str

    # Target description
    target_description: str

    # Fields (masked)
    field_summary: dict[str, str]

    # Risk level
    risk_level: str
    risk_description: str

    # Destructive warning
    is_destructive: bool = False
    destructive_warning: str = ""

    # Confirmation required
    requires_confirmation: bool = True
    confirmation_question: str = "정말 제출하시겠습니까?"


@dataclass
class UserPreviewDetails:
    """User-facing detailed verification info."""

    # Policy verdict
    policy_verdict: str
    policy_reasons: list[str]

    # Form info
    form_id: str
    submit_button_id: str
    intent: str

    # Fields display (masked)
    fields_display: list[dict]
    hidden_fields_count: int

    # Validation checks
    validation_checks: dict[str, str]


@dataclass
class AuditPreviewRecord:
    """Audit and tracking record."""

    # Identifiers
    validation_id: str

    # Submit basic info
    site_id: str
    form_id: str
    intent: str

    # Redacted payload
    redacted_payload: dict[str, Any]

    # Preview hash
    preview_hash: str
    preview_timestamp: str

    # Policy result
    policy_verdict: str
    risk_level: str

    # Submit status
    submitted: bool = False
    submit_timestamp: str = ""
    submit_result: str | None = None

    # Approval info
    approved_by: str | None = None
    approved_at: str | None = None
    approval_notes: str = ""


@dataclass
class SubmitPreviewBundle:
    """Complete preview package (summary + details + audit)."""

    summary: UserPreviewSummary
    details: UserPreviewDetails
    audit: AuditPreviewRecord


# Denied Field Keywords (for masking check)
_DENIED_FIELD_KEYWORDS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "session_token",
    "jwt",
    "secret",
    "api_secret",
    "client_secret",
    "key",
    "api_key",
    "private_key",
    "cookie",
    "session_id",
    "authorization",
    "bearer",
    "otp",
    "2fa",
    "pin",
    "cvv",
    "security_code",
}

# Masking patterns
_MASK_PATTERNS = {
    "phone": r"^(\+?\d{1,3}[-.]?)?\d{3,4}[-.]?\d{3,4}[-.]?\d{4}",
    "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "url": r"^https?://",
}


def mask_field_value(name: str, value: str) -> str:
    """Mask field value based on field name and content.

    Returns masked value (or original if no masking rule applies).
    """
    if not value or not isinstance(value, str):
        return "[값 없음]"

    name_lower = name.lower()

    # Check denied keywords (priority 1: highest secrecy)
    if any(keyword in name_lower for keyword in _DENIED_FIELD_KEYWORDS):
        return "****"

    # Check masking patterns (priority 2: sensitive PII)
    if re.search(_MASK_PATTERNS.get("phone", ""), value):
        if len(value) > 10:
            return f"{value[:3]}****{value[-4:]}"
        return "****"

    if re.search(_MASK_PATTERNS.get("email", ""), value):
        parts = value.split("@")
        if len(parts) == 2:
            domain = parts[1]
            return f"***@{domain}"
        return "****"

    if re.search(_MASK_PATTERNS.get("url", ""), value):
        return "[URL 입력]"

    # Long text masking
    if len(value) > 100:
        lines = value.count("\n") + 1
        return f"[텍스트 입력 {lines}줄]" if lines > 1 else "[텍스트 입력]"

    # No masking needed
    return value


def redact_fields(fields: list[dict]) -> list[dict]:
    """Redact field values for audit storage.

    Returns list of fields with redacted values (no original values).
    """
    if not fields:
        return []

    redacted = []
    for field in fields:
        field_name = field.get("name", "unknown")
        field_value = field.get("value", "")

        masked_value = mask_field_value(field_name, field_value)

        redacted.append(
            {
                "name": field_name,
                "value": masked_value,
                "masked": masked_value != field_value,
            }
        )

    return redacted


def canonical_preview_payload(payload: dict) -> str:
    """Convert payload to canonical JSON (sorted keys, no extra fields).

    Returns canonical JSON string for deterministic hashing.
    Sorts list items by field name for consistent ordering.
    """
    canonical_dict = {}
    for key, value in sorted(payload.items()):
        if isinstance(value, list) and value and isinstance(value[0], dict):
            canonical_dict[key] = sorted(value, key=lambda x: x.get("name", ""))
        else:
            canonical_dict[key] = value
    return json.dumps(canonical_dict, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_preview_hash(payload: dict) -> str:
    """Compute SHA256 hash of preview payload.

    Returns hex digest (deterministic for same input).
    """
    canonical = canonical_preview_payload(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_field_summary(fields: list[dict]) -> dict[str, str]:
    """Build user-friendly field summary (masked)."""
    summary = {}
    for field in fields:
        name = field.get("name", "unknown")
        value = field.get("value", "")
        summary[name] = mask_field_value(name, value)
    return summary


def _build_fields_display(fields: list[dict]) -> list[dict]:
    """Build detailed field display with masking indicators."""
    display = []
    for field in fields:
        name = field.get("name", "unknown")
        value = field.get("value", "")
        masked_value = mask_field_value(name, value)

        display.append(
            {
                "name": name,
                "display": masked_value,
                "masked": masked_value != value,
                "masked_type": _get_mask_type(name),
            }
        )

    return display


def _get_mask_type(field_name: str) -> str:
    """Determine masking type for field."""
    name_lower = field_name.lower()

    if any(keyword in name_lower for keyword in _DENIED_FIELD_KEYWORDS):
        return "denied"

    if any(keyword in name_lower for keyword in ["email"]):
        return "email"

    if any(keyword in name_lower for keyword in ["phone", "tel", "mobile"]):
        return "phone"

    if any(keyword in name_lower for keyword in ["url", "link", "website"]):
        return "url"

    if any(keyword in name_lower for keyword in ["text", "memo", "note", "content"]):
        return "long_text"

    return "none"


def _build_validation_checks(policy_result: dict) -> dict[str, str]:
    """Extract validation check results from policy result."""
    return {
        "allowlist_verdict": policy_result.get("allowlist_verdict", "UNKNOWN"),
        "origin_verdict": policy_result.get("origin_verdict", "UNKNOWN"),
        "form_verdict": policy_result.get("form_verdict", "UNKNOWN"),
        "intent_verdict": policy_result.get("intent_verdict", "UNKNOWN"),
        "field_verdict": policy_result.get("field_verdict", "UNKNOWN"),
        "prompt_injection_verdict": policy_result.get("prompt_injection_verdict", "UNKNOWN"),
        "preview_verdict": policy_result.get("preview_verdict", "UNKNOWN"),
        "user_confirm_verdict": policy_result.get("user_confirm_verdict", "UNKNOWN"),
    }


def build_submit_preview(
    request: SubmitPreviewInput,
    policy_result: dict,
    preview_timestamp: str,
) -> SubmitPreviewBundle:
    """Build complete preview bundle from validation request and result.

    Args:
        request: SubmitPreviewInput with form and field info
        policy_result: dict with policy validation results
        preview_timestamp: ISO8601 timestamp

    Returns:
        SubmitPreviewBundle with summary, details, and audit records
    """
    # Prepare redacted payload for audit
    redacted_fields = redact_fields(request.fields)
    audit_payload = {
        "site_id": request.site_id,
        "form_id": request.form_id,
        "intent": request.intent,
        "fields": redacted_fields,
        "hidden_fields_count": len(request.hidden_fields),
    }

    # Compute preview hash
    preview_hash = compute_preview_hash(audit_payload)

    # Build summary (user-facing)
    field_summary = _build_field_summary(request.fields)
    summary = UserPreviewSummary(
        site_id=request.site_id,
        form_title=f"{request.site_id.replace('_', ' ').title()} 제출",
        target_description=f"제목: {request.form_id} | 의도: {request.intent}",
        field_summary=field_summary,
        risk_level=request.risk_level,
        risk_description="제출된 데이터는 복구할 수 없습니다",
        is_destructive=False,
        requires_confirmation=True,
        confirmation_question="정말 제출하시겠습니까?",
    )

    # Build details (detailed verification)
    fields_display = _build_fields_display(request.fields)
    validation_checks = _build_validation_checks(policy_result)
    details = UserPreviewDetails(
        policy_verdict=request.policy_verdict,
        policy_reasons=policy_result.get("reasons", []),
        form_id=request.form_id,
        submit_button_id=request.submit_button_id,
        intent=request.intent,
        fields_display=fields_display,
        hidden_fields_count=len(request.hidden_fields),
        validation_checks=validation_checks,
    )

    # Build audit record
    audit = AuditPreviewRecord(
        validation_id=request.validation_id,
        site_id=request.site_id,
        form_id=request.form_id,
        intent=request.intent,
        redacted_payload=audit_payload,
        preview_hash=preview_hash,
        preview_timestamp=preview_timestamp,
        policy_verdict=request.policy_verdict,
        risk_level=request.risk_level,
        submitted=False,
    )

    return SubmitPreviewBundle(summary=summary, details=details, audit=audit)
