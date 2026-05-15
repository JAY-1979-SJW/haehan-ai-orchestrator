"""site_engine form resolver — 폼 필드 후보 분류 foundation.

label/name/id/placeholder 기반 의미 분류만 수행한다.
실제 입력 실행 금지. 값 저장 금지.
기존 scripts/form/discovery.py를 대체하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FormFieldKind(str, Enum):
    ID = "ID"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    PASSWORD = "PASSWORD"
    PASSWORD_CONFIRM = "PASSWORD_CONFIRM"
    OTP = "OTP"
    NAME = "NAME"
    BIRTH = "BIRTH"
    ADDRESS = "ADDRESS"
    AGREE = "AGREE"
    SEARCH = "SEARCH"
    SUBMIT = "SUBMIT"
    FILE = "FILE"
    TEXT = "TEXT"
    SELECT = "SELECT"
    OTHER = "OTHER"


class FormFieldSensitivity(str, Enum):
    SAFE = "SAFE"
    RESTRICTED = "RESTRICTED"  # 사용자 직접 입력만
    FORBIDDEN = "FORBIDDEN"    # 값 추출/저장 불가


_SENSITIVE_KINDS = frozenset({
    FormFieldKind.PASSWORD,
    FormFieldKind.PASSWORD_CONFIRM,
    FormFieldKind.OTP,
})

_FORBIDDEN_KINDS = frozenset({
    FormFieldKind.PASSWORD,
    FormFieldKind.PASSWORD_CONFIRM,
    FormFieldKind.OTP,
})

_KIND_KEYWORDS: dict[FormFieldKind, list[str]] = {
    FormFieldKind.ID: ["userid", "user_id", "loginid", "login_id", "username", "아이디"],
    FormFieldKind.EMAIL: ["email", "mail", "이메일"],
    FormFieldKind.PHONE: ["phone", "mobile", "tel", "hp", "휴대폰", "전화"],
    FormFieldKind.PASSWORD: ["password", "passwd", "pw", "pwd", "비밀번호"],
    FormFieldKind.PASSWORD_CONFIRM: ["password_confirm", "pw_confirm", "password2",
                                      "비밀번호확인", "confirm_password"],
    FormFieldKind.OTP: ["otp", "인증번호", "sms_code", "email_code", "auth_code"],
    FormFieldKind.NAME: ["name", "fullname", "성명", "이름"],
    FormFieldKind.BIRTH: ["birth", "dob", "생년월일"],
    FormFieldKind.ADDRESS: ["address", "addr", "zipcode", "postcode", "주소", "우편번호"],
    FormFieldKind.AGREE: ["agree", "terms", "privacy", "이용약관", "개인정보"],
    FormFieldKind.SEARCH: ["search", "query", "keyword", "검색"],
    FormFieldKind.FILE: ["file", "attach", "upload", "파일", "첨부"],
}

_MASK = "***REDACTED***"


@dataclass
class FormFieldCandidate:
    selector: str
    kind: FormFieldKind
    sensitivity: FormFieldSensitivity
    label: str = ""
    name: str = ""
    field_id: str = ""
    placeholder: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    # value 필드 없음 — 민감값 저장 금지


@dataclass
class FormResolutionInput:
    page_url: str
    fields_raw: list[dict[str, Any]]  # {selector, name, id, type, placeholder, label}


@dataclass
class FormResolutionResult:
    candidates: list[FormFieldCandidate]
    has_sensitive_fields: bool
    sensitive_field_count: int


def classify_field_sensitivity(kind: FormFieldKind) -> FormFieldSensitivity:
    if kind in _FORBIDDEN_KINDS:
        return FormFieldSensitivity.FORBIDDEN
    if kind in _SENSITIVE_KINDS:
        return FormFieldSensitivity.RESTRICTED
    return FormFieldSensitivity.SAFE


def _detect_kind(raw: dict[str, Any]) -> tuple[FormFieldKind, float]:
    combined = " ".join(filter(None, [
        raw.get("name", ""),
        raw.get("id", ""),
        raw.get("placeholder", ""),
        raw.get("label", ""),
        raw.get("type", ""),
    ])).lower()

    # type=password 직접 매칭 (가장 신뢰도 높음)
    if raw.get("type") == "password":
        confirm_hints = ["confirm", "2", "_re", "check", "확인"]
        if any(h in combined for h in confirm_hints):
            return FormFieldKind.PASSWORD_CONFIRM, 1.0
        return FormFieldKind.PASSWORD, 1.0

    # type=file
    if raw.get("type") == "file":
        return FormFieldKind.FILE, 1.0

    best_kind = FormFieldKind.OTHER
    best_score = 0.0
    for kind, keywords in _KIND_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                score = len(kw) / max(len(combined), 1)
                if score > best_score:
                    best_score = score
                    best_kind = kind

    return best_kind, min(best_score * 10, 1.0)


def mask_field_value(value: str, kind: FormFieldKind) -> str:
    if kind in _FORBIDDEN_KINDS:
        return _MASK
    return value


def resolve_form_fields(resolution_input: FormResolutionInput) -> FormResolutionResult:
    candidates: list[FormFieldCandidate] = []
    for raw in resolution_input.fields_raw:
        kind, score = _detect_kind(raw)
        sensitivity = classify_field_sensitivity(kind)
        candidates.append(FormFieldCandidate(
            selector=raw.get("selector", ""),
            kind=kind,
            sensitivity=sensitivity,
            label=raw.get("label", ""),
            name=raw.get("name", ""),
            field_id=raw.get("id", ""),
            placeholder=raw.get("placeholder", ""),
            score=score,
        ))

    sensitive_count = sum(
        1 for c in candidates
        if c.sensitivity in (FormFieldSensitivity.FORBIDDEN, FormFieldSensitivity.RESTRICTED)
    )
    return FormResolutionResult(
        candidates=candidates,
        has_sensitive_fields=sensitive_count > 0,
        sensitive_field_count=sensitive_count,
    )
