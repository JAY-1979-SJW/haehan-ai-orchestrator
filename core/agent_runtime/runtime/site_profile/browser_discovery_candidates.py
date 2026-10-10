"""Browser Discovery Candidates — 화면 탐색 결과 후보 구조 (즉시 실행 금지).

LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1 STEP 3.

raw HTML/screenshot/HAR/cookie 저장 절대 금지.
visible_label, role, normalized_text 등 안전 필드만.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

CANDIDATE_MENU = "menu_candidate"
CANDIDATE_PAGE_TITLE = "page_title_candidate"
CANDIDATE_FIELD = "field_candidate"
CANDIDATE_TABLE_HEADER = "table_header_candidate"
CANDIDATE_BUTTON = "button_candidate"
CANDIDATE_FILE_INPUT = "file_input_candidate"
CANDIDATE_DOWNLOAD_LINK = "download_link_candidate"
CANDIDATE_SUBMIT_BUTTON = "submit_button_candidate"
CANDIDATE_DESTRUCTIVE_BUTTON = "destructive_button_candidate"

ALL_CANDIDATE_TYPES = (
    CANDIDATE_MENU,
    CANDIDATE_PAGE_TITLE,
    CANDIDATE_FIELD,
    CANDIDATE_TABLE_HEADER,
    CANDIDATE_BUTTON,
    CANDIDATE_FILE_INPUT,
    CANDIDATE_DOWNLOAD_LINK,
    CANDIDATE_SUBMIT_BUTTON,
    CANDIDATE_DESTRUCTIVE_BUTTON,
)

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 위험 키워드 (label/text에 포함되면 HIGH로 분류)
_DESTRUCTIVE_KEYWORDS = (
    "삭제",
    "delete",
    "remove",
    "drop",
    "결제",
    "payment",
    "송금",
    "transfer",
    "이체",
    "투찰",
    "bid",
    "전자서명",
    "sign",
    "서명",
    "상신",
    "approve",
    "결재",
    "제출",
    "submit",
    "저장",
    "save",
    "출금",
    "withdraw",
    "확정",
    "confirm",
)

_FORBIDDEN_LABEL_KEYWORDS = (
    "password",
    "비밀번호",
    "otp",
    "인증번호",
    "주민번호",
    "주민등록번호",
    "계좌번호",
    "cert_password",
    "private_key",
)


@dataclass(frozen=True)
class DiscoveryCandidate:
    candidate_type: str
    visible_label: str
    role: str
    normalized_text: str
    selector_fingerprint: str
    confidence: str
    risk_hint: str
    source_site_id: str
    source_path_key: str


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:120]


def fingerprint_selector(role: str, label: str, position_hint: str = "") -> str:
    """raw selector 저장 금지 — 의미 기반 fingerprint만 저장."""
    payload = f"{role}|{label}|{position_hint}".lower()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def classify_risk(candidate_type: str, visible_label: str) -> str:
    label_low = (visible_label or "").lower()
    if candidate_type == CANDIDATE_DESTRUCTIVE_BUTTON:
        return RISK_HIGH
    if candidate_type in (CANDIDATE_SUBMIT_BUTTON,):
        return RISK_HIGH
    for kw in _DESTRUCTIVE_KEYWORDS:
        if kw in label_low or kw in (visible_label or ""):
            return RISK_HIGH
    if candidate_type in (CANDIDATE_FIELD, CANDIDATE_FILE_INPUT):
        return RISK_MEDIUM
    if candidate_type in (
        CANDIDATE_MENU,
        CANDIDATE_PAGE_TITLE,
        CANDIDATE_TABLE_HEADER,
        CANDIDATE_DOWNLOAD_LINK,
        CANDIDATE_BUTTON,
    ):
        return RISK_LOW
    return RISK_MEDIUM


def is_forbidden_label(visible_label: str) -> bool:
    if not visible_label:
        return False
    low = visible_label.lower()
    for kw in _FORBIDDEN_LABEL_KEYWORDS:
        if kw in low:
            return True
    return False


def build_candidate(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    candidate_type: str,
    visible_label: str,
    role: str,
    source_site_id: str,
    source_path_key: str,
    raw_text: str = "",
    position_hint: str = "",
    confidence: str = "MEDIUM",
) -> dict[str, Any]:
    """후보 dict 생성. raw HTML/selector/screenshot 저장 금지."""
    if candidate_type not in ALL_CANDIDATE_TYPES:
        return {"ok": False, "verdict": "UNKNOWN_CANDIDATE_TYPE"}
    if is_forbidden_label(visible_label):
        return {
            "ok": False,
            "verdict": "FORBIDDEN_LABEL_BLOCKED",
            "blocked_reason": "민감 라벨 — credential 후보 차단",
        }
    candidate = DiscoveryCandidate(
        candidate_type=candidate_type,
        visible_label=normalize_text(visible_label)[:60],
        role=role[:32],
        normalized_text=normalize_text(raw_text),
        selector_fingerprint=fingerprint_selector(role, visible_label, position_hint),
        confidence=confidence,
        risk_hint=classify_risk(candidate_type, visible_label),
        source_site_id=source_site_id,
        source_path_key=source_path_key,
    )
    return {
        "ok": True,
        "verdict": "CANDIDATE_BUILT",
        "candidate": {
            "candidate_type": candidate.candidate_type,
            "visible_label": candidate.visible_label,
            "role": candidate.role,
            "normalized_text": candidate.normalized_text,
            "selector_fingerprint": candidate.selector_fingerprint,
            "confidence": candidate.confidence,
            "risk_hint": candidate.risk_hint,
            "source_site_id": candidate.source_site_id,
            "source_path_key": candidate.source_path_key,
        },
    }


def validate_candidate_safety(candidate: dict[str, Any]) -> dict[str, Any]:
    """후보 dict의 보안 정책 위반 여부 검증."""
    forbidden_keys = {
        "raw_html",
        "raw_selector",
        "screenshot",
        "har",
        "cookie",
        "session",
        "storage_state",
        "localStorage",
        "password",
        "otp",
        "private_key",
        "cert_password",
        "outer_html",
        "inner_html",
    }
    for key in candidate:
        kl = key.lower()
        for fk in forbidden_keys:
            if fk in kl:
                return {"safe": False, "blocked_reason": f"금지 필드 포함: {key}"}
    return {"safe": True}
