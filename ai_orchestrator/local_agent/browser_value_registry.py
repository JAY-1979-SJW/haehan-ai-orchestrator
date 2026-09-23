"""Browser Value Registry — value_key 기반 입력값 정책 (raw text 입력 차단).

LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1 STEP 5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

VTYPE_SAMPLE_TEXT = "sample_text"
VTYPE_SAMPLE_NUMBER = "sample_number"
VTYPE_SAMPLE_DATE = "sample_date"
VTYPE_SAMPLE_EMAIL = "sample_email"
VTYPE_SAFE_MASKED = "safe_masked"
VTYPE_USER_APPROVED_NONSENSITIVE = "user_approved_nonsensitive"

REDACT_NONE = "NONE"
REDACT_MASK_MIDDLE = "MASK_MIDDLE"
REDACT_LENGTH_ONLY = "LENGTH_ONLY"

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

_FORBIDDEN_VALUE_KEYWORDS = (
    "password",
    "비밀번호",
    "otp",
    "cert_password",
    "private_key",
    "cookie",
    "session",
    "storage_state",
    "localStorage",
    "sessionStorage",
    "access_token",
    "refresh_token",
    "npki",
)

# 패턴 차단 — 주민번호/계좌번호 원문
_RRN_PATTERN = re.compile(r"\b\d{6}-\d{7}\b")
_ACCOUNT_PATTERN = re.compile(r"\b\d{3,6}-\d{2,6}-\d{4,8}\b")


@dataclass(frozen=True)
class ValuePolicy:
    value_key: str
    label: str
    value_type: str
    sample_safe_value: str
    allowed_profiles: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] = ()
    risk_level: str = RISK_LOW
    source: str = "internal_sample"
    redaction_policy: str = REDACT_NONE


_REGISTRY: dict[str, ValuePolicy] = {}


def is_forbidden_value(raw: str, key: str = "") -> tuple[bool, str]:
    """raw 입력값이 금지 패턴/키워드에 해당하는지."""
    if not isinstance(raw, str):
        return False, ""
    kl = (key or "").lower()
    for kw in _FORBIDDEN_VALUE_KEYWORDS:
        if kw in kl:
            return True, f"금지 키 ({kw})"
    if _RRN_PATTERN.search(raw):
        return True, "주민번호 패턴"
    if _ACCOUNT_PATTERN.search(raw):
        return True, "계좌번호 패턴"
    low = raw.lower()
    for kw in _FORBIDDEN_VALUE_KEYWORDS:
        if kw in low:
            return True, f"금지 키워드 ({kw})"
    return False, ""


def register_value(policy: ValuePolicy) -> dict[str, Any]:
    if not policy.value_key:
        return {"ok": False, "verdict": "MISSING_VALUE_KEY"}
    forbidden, reason = is_forbidden_value(policy.sample_safe_value, policy.value_key)
    if forbidden:
        return {"ok": False, "verdict": "VALUE_BLOCKED", "blocked_reason": reason}
    if policy.value_type not in (
        VTYPE_SAMPLE_TEXT,
        VTYPE_SAMPLE_NUMBER,
        VTYPE_SAMPLE_DATE,
        VTYPE_SAMPLE_EMAIL,
        VTYPE_SAFE_MASKED,
        VTYPE_USER_APPROVED_NONSENSITIVE,
    ):
        return {"ok": False, "verdict": "UNSUPPORTED_VALUE_TYPE"}
    _REGISTRY[policy.value_key] = policy
    return {"ok": True, "verdict": "REGISTERED", "value_key": policy.value_key}


def get_value(value_key: str) -> ValuePolicy | None:
    return _REGISTRY.get(value_key)


def resolve_value_for_field(value_key: str, field_id: str, profile: str = "") -> dict[str, Any]:
    """value_key로만 값 조회 — raw text 직접 입력 차단."""
    policy = get_value(value_key)
    if policy is None:
        return {"ok": False, "verdict": "UNKNOWN_VALUE_KEY"}
    if policy.allowed_fields and field_id not in policy.allowed_fields:
        return {"ok": False, "verdict": "FIELD_NOT_ALLOWED"}
    if policy.allowed_profiles and profile and profile not in policy.allowed_profiles:
        return {"ok": False, "verdict": "PROFILE_NOT_ALLOWED"}
    return {
        "ok": True,
        "verdict": "VALUE_RESOLVED",
        "value_key": value_key,
        "value_type": policy.value_type,
        "sample_safe_value": policy.sample_safe_value,
        "risk_level": policy.risk_level,
    }


def validate_raw_input(raw: str, key: str = "") -> dict[str, Any]:
    """raw text 직접 입력 시도 차단."""
    forbidden, reason = is_forbidden_value(raw, key)
    if forbidden:
        return {"ok": False, "verdict": "RAW_INPUT_BLOCKED", "blocked_reason": reason}
    return {
        "ok": False,
        "verdict": "RAW_INPUT_NOT_PERMITTED",
        "blocked_reason": "raw text 입력 직접 실행 금지 — value_key 사용 필요",
    }


def list_values() -> list[str]:
    return sorted(_REGISTRY.keys())


def clear_all() -> None:
    _REGISTRY.clear()
