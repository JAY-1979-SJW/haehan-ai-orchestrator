"""Browser Submit Policy Validator.

Pure policy validation module (no browser execution, no network calls, no DB).
Validates submit requests against policy fixture allowlist.

This module contains ONLY policy judgment logic.
No side effects, stateless, pure functions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SubmitValidationRequest:
    """Submit policy validation request."""

    # Site & URL Info
    site_id: str
    url: str

    # Form Info
    form_id: str
    submit_button_id: str
    submit_button_text: str = ""

    # User Action Intent
    intent: str = ""

    # Form Fields
    fields: list[dict] = field(default_factory=list)
    hidden_fields: list[dict] = field(default_factory=list)

    # Prompt & User Interaction
    prompt_text: str = ""
    preview_shown: bool = False
    user_confirmed: bool = False


@dataclass
class SubmitPolicyResult:
    """Submit policy validation result."""

    # Final Verdict
    verdict: str  # "ALLOW" or "DENY"

    # Risk Assessment
    risk_level: str = "high"
    requires_approval: bool = True

    # Detailed Reasoning
    reasons: list[str] = field(default_factory=list)

    # Policy Matching
    matched_case_id: str = ""
    matched_policy_entry: dict = field(default_factory=dict)

    # Validation Results
    allowlist_verdict: str = ""
    origin_verdict: str = ""
    form_verdict: str = ""
    intent_verdict: str = ""
    field_verdict: str = ""
    prompt_injection_verdict: str = ""
    preview_verdict: str = ""
    user_confirm_verdict: str = ""

    # Requirement Status
    preview_required: bool = False
    user_confirm_required: bool = False
    audit_required: bool = True

    # Audit Info
    validation_id: str = ""


# Prompt Injection Patterns
_PROMPT_INJECTION_PATTERNS = [
    # 지시 무시
    r"ignore.*previous.*instruction",
    r"무시하고.*제출",
    r"지시를.*무시",
    # 승인 우회
    r"without.*approval",
    r"승인.*없이.*제출",
    r"확인.*생략",
    # 정책 우회
    r"bypass.*policy",
    r"정책.*무시",
    r"제한.*해제",
    # 자동 완료
    r"auto.*submit",
    r"자동.*제출",
]

# Denied Field Keywords
_DENIED_FIELD_KEYWORDS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "session_token",
    "secret",
    "api_secret",
    "client_secret",
    "key",
    "api_key",
    "cookie",
    "authorization",
}


def extract_origin(url: str) -> str:
    """Extract scheme + netloc from URL.

    Example:
      "https://internal.mock/form/submit" → "https://internal.mock"
    """
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"
    except Exception as exc:  # noqa: BLE001 - 폼 제출 정책 allowlist 검사 -- origin/path 파싱 실패 시 매치 실패(False)로 처리되어 결과적으로 차단 방향(fail-closed)
        logger.warning("제출 정책 origin 추출 실패: %s", type(exc).__name__)
        return ""


def path_matches_allowlist(actual_path: str, allowed_paths: list[str]) -> bool:
    """Check if actual_path starts with any allowed_path.

    Example:
      actual_path="/form/contact/submit", allowed_paths=["/form", "/contact"]
      → True (matches "/form")
    """
    if not allowed_paths:
        return False
    for allowed_path in allowed_paths:
        if actual_path.startswith(allowed_path):
            return True
    return False


def detect_prompt_injection(prompt_text: str, field_values: dict | None = None) -> list[str]:
    """Detect prompt injection patterns.

    Returns list of matched patterns. Empty if none detected.
    """
    if not prompt_text:
        return []

    violations = []
    text_lower = prompt_text.lower()

    for pattern in _PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            violations.append(pattern)

    # Also check field values if provided
    if field_values:
        for field_name, field_value in field_values.items():
            if field_value and isinstance(field_value, str):
                value_lower = field_value.lower()
                for pattern in _PROMPT_INJECTION_PATTERNS:
                    if re.search(pattern, value_lower, re.IGNORECASE):
                        violations.append(f"{field_name}: {pattern}")

    return list(set(violations))  # deduplicate


def contains_denied_field(fields: list[dict], denied_field_names: list[str]) -> list[str]:
    """Check if any field name is in denied list.

    Returns list of denied field names found. Empty if none.
    """
    if not fields or not denied_field_names:
        return []

    denied_lower = {name.lower() for name in denied_field_names}
    found = []

    for field_item in fields:
        field_name = field_item.get("name", "").lower()
        if field_name in denied_lower:
            found.append(field_name)

    return list(set(found))  # deduplicate


def validate_hidden_fields(hidden_fields: list[dict]) -> tuple[bool, str]:
    """Validate hidden fields are inspectable.

    Returns (is_valid, reason).
    Current implementation: all hidden fields are considered inspectable.
    """
    if not hidden_fields:
        return True, "no hidden fields"

    # All hidden fields in our controlled environment are inspectable
    field_names = [f.get("name", "unknown") for f in hidden_fields]
    return True, f"hidden fields inspectable: {field_names}"


def validate_allowlist_exists(site_id: str, allowlist: dict) -> tuple[bool, dict | None]:
    """Check if site_id exists in allowlist and is active.

    Returns (exists, policy_entry).
    """
    if not allowlist or "submit_sites" not in allowlist:
        return False, None

    for site in allowlist.get("submit_sites", []):
        if site.get("site_id") == site_id and site.get("active") is True:
            return True, site

    return False, None


def validate_origin_match(url: str, allowed_origins: list[str]) -> bool:
    """Check if URL origin matches allowlist."""
    if not allowed_origins:
        return False

    actual_origin = extract_origin(url)
    return actual_origin in allowed_origins


def validate_path_match(url: str, allowed_paths: list[str]) -> bool:
    """Check if URL path matches allowlist (prefix match)."""
    if not allowed_paths:
        return False

    try:
        p = urlparse(url)
        actual_path = p.path or "/"
        return path_matches_allowlist(actual_path, allowed_paths)
    except Exception as exc:  # noqa: BLE001 - 폼 제출 정책 allowlist 검사 -- origin/path 파싱 실패 시 매치 실패(False)로 처리되어 결과적으로 차단 방향(fail-closed)
        logger.warning("제출 정책 path allowlist 검사 실패: %s", type(exc).__name__)
        return False


def validate_form_id(form_id: str, allowed_form_ids: list[str]) -> bool:
    """Check if form_id matches allowlist."""
    if not allowed_form_ids:
        return False
    return form_id in allowed_form_ids


def validate_submit_button_id(button_id: str, allowed_button_ids: list[str]) -> bool:
    """Check if submit_button_id matches allowlist."""
    if not allowed_button_ids:
        return False
    return button_id in allowed_button_ids


def validate_intent(intent: str, allowed_intents: list[str]) -> bool:
    """Check if intent is in allowlist."""
    if not allowed_intents:
        return False
    return intent in allowed_intents


def _validate_button_through_confirmation(
    request: SubmitValidationRequest,
    result: SubmitPolicyResult,
    policy_entry: dict | None,
) -> SubmitPolicyResult:
    """STEP 5~12 순차 검사 (첫 실패 시 DENY 반환, 모두 통과 시 ALLOW)."""
    # STEP 5: Check submit_button_id match
    allowed_button_ids = policy_entry.get("allowed_submit_button_ids", []) if policy_entry else []
    button_match = validate_submit_button_id(request.submit_button_id, allowed_button_ids)

    if not button_match:
        result.reasons.append(f"submit_button_id 불일치: '{request.submit_button_id}' not in {allowed_button_ids}")
        return result

    # STEP 6: Check intent match
    allowed_intents = policy_entry.get("allowed_intents", []) if policy_entry else []
    intent_match = validate_intent(request.intent, allowed_intents)
    result.intent_verdict = "ALLOWED" if intent_match else "NOT_ALLOWED"

    if not intent_match:
        result.reasons.append(f"intent 불일치: '{request.intent}' not in {allowed_intents}")
        return result

    # STEP 7: Check denied fields
    denied_field_names = policy_entry.get("denied_fields", []) if policy_entry else []
    found_denied = contains_denied_field(request.fields, denied_field_names)
    result.field_verdict = "SAFE" if not found_denied else "DENIED_FIELD_FOUND"

    if found_denied:
        result.reasons.append(f"denied field 포함: {found_denied}")
        return result

    # STEP 8: Check hidden fields
    hidden_valid, hidden_reason = validate_hidden_fields(request.hidden_fields)

    if not hidden_valid:
        result.reasons.append(f"hidden field 검증 불가: {hidden_reason}")
        return result

    # STEP 9: Check prompt injection
    injection_patterns = detect_prompt_injection(request.prompt_text, {"fields": str(request.fields)})
    result.prompt_injection_verdict = "PASS" if not injection_patterns else "FAIL"

    if injection_patterns:
        result.reasons.append(f"prompt injection 감지: {injection_patterns}")
        return result

    # STEP 10: Check preview shown
    if result.preview_required and not request.preview_shown:
        result.preview_verdict = "NOT_SHOWN"
        result.reasons.append("preview 표시 안 됨 (required=true)")
        return result

    result.preview_verdict = "SHOWN" if request.preview_shown else "NOT_SHOWN_OK"

    # STEP 11: Check user confirmed
    if result.user_confirm_required and not request.user_confirmed:
        result.user_confirm_verdict = "NOT_CONFIRMED"
        result.reasons.append("사용자 확인 없음 (required=true)")
        return result

    result.user_confirm_verdict = "CONFIRMED" if request.user_confirmed else "CONFIRMED_OK"

    # STEP 12: All conditions met → ALLOW
    result.verdict = "ALLOW"
    result.reasons = ["모든 조건 충족"]

    return result


def validate_submit_policy(request: SubmitValidationRequest, allowlist: dict) -> SubmitPolicyResult:
    """Validate submit request against policy fixture.

    Main validator function. Checks all conditions sequentially.
    Returns DENY on first failure (AND logic).
    """
    result = SubmitPolicyResult(
        verdict="DENY",  # Default to deny
        risk_level="high",
        requires_approval=True,
        audit_required=True,
    )

    # STEP 1: Check if allowlist has site_id
    allowlist_exists, policy_entry = validate_allowlist_exists(request.site_id, allowlist)
    result.allowlist_verdict = "FOUND" if allowlist_exists else "NOT_FOUND"

    if not allowlist_exists:
        result.reasons.append(f"allowlist에 site_id '{request.site_id}' 없음")
        return result

    # Now we have a policy entry
    result.matched_case_id = request.site_id
    result.matched_policy_entry = policy_entry or {}
    result.preview_required = policy_entry.get("requires_preview", False) if policy_entry else False
    result.user_confirm_required = policy_entry.get("requires_user_confirm", False) if policy_entry else False

    # STEP 2: Check origin match
    allowed_origins = policy_entry.get("allowed_origins", []) if policy_entry else []
    origin_match = validate_origin_match(request.url, allowed_origins)
    result.origin_verdict = "MATCH" if origin_match else "MISMATCH"

    if not origin_match:
        actual_origin = extract_origin(request.url)
        result.reasons.append(f"origin 불일치: {actual_origin} not in {allowed_origins}")
        return result

    # STEP 3: Check path match (if specified)
    allowed_paths = policy_entry.get("allowed_paths", []) if policy_entry else []
    if allowed_paths:  # Only check if paths are defined
        path_match = validate_path_match(request.url, allowed_paths)
        if not path_match:
            from urllib.parse import urlparse

            actual_path = urlparse(request.url).path or "/"
            result.reasons.append(f"path 불일치: {actual_path} not in {allowed_paths}")
            return result

    # STEP 4: Check form_id match
    allowed_form_ids = policy_entry.get("allowed_form_ids", []) if policy_entry else []
    form_match = validate_form_id(request.form_id, allowed_form_ids)
    result.form_verdict = "FOUND" if form_match else "NOT_FOUND"

    if not form_match:
        result.reasons.append(f"form_id 불일치: '{request.form_id}' not in {allowed_form_ids}")
        return result

    # STEP 5~12: button / intent / field / injection / preview / confirm
    return _validate_button_through_confirmation(request, result, policy_entry)


