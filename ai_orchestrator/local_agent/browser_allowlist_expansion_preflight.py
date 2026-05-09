"""Browser Allowlist Expansion Preflight — 후보를 바로 실행하지 않고 정책 통과 여부만 판정.

LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1 STEP 6.

verdict:
- ALLOW_REGISTER : 자동 등록 가능 (read-only, low risk)
- REVIEW_REQUIRED : 사용자 검토/승인 필요
- BLOCKED       : 정책 위반으로 영구 차단
"""
from __future__ import annotations

from typing import Any

from ai_orchestrator.local_agent.browser_site_registry import (
    get_site, validate_raw_url,
    EXECUTION_LOCAL_AGENT_REQUIRED,
    LOGIN_PUBLIC_READONLY, LOGIN_USER_PRESENT_AFTER_LOGIN,
)
from ai_orchestrator.local_agent.browser_discovery_candidates import (
    validate_candidate_safety, RISK_LOW, RISK_MEDIUM, RISK_HIGH,
    CANDIDATE_SUBMIT_BUTTON, CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_MENU, CANDIDATE_PAGE_TITLE, CANDIDATE_TABLE_HEADER,
    CANDIDATE_DOWNLOAD_LINK, CANDIDATE_BUTTON,
    is_forbidden_label,
)
from ai_orchestrator.local_agent.browser_value_registry import (
    is_forbidden_value,
)

VERDICT_ALLOW = "ALLOW_REGISTER"
VERDICT_REVIEW = "REVIEW_REQUIRED"
VERDICT_BLOCKED = "BLOCKED"

_AUTO_REGISTERABLE_TYPES = frozenset((
    CANDIDATE_MENU, CANDIDATE_PAGE_TITLE, CANDIDATE_TABLE_HEADER,
    CANDIDATE_DOWNLOAD_LINK,
))

_DESTRUCTIVE_ACTIONS = frozenset((
    "submit", "save", "sign", "delete", "payment", "bid", "transfer",
    "withdraw", "approve", "confirm", "제출", "저장", "삭제",
    "전자서명", "투찰", "결제", "송금", "이체", "출금", "확정", "상신",
))

_FORBIDDEN_PURPOSE_KEYWORDS = frozenset((
    "credential", "login_automation", "cookie", "session",
    "storage_state", "screenshot", "har", "certificate",
    "password", "otp",
))


def _block(reason: str, **extra) -> dict[str, Any]:
    return {
        "verdict": VERDICT_BLOCKED,
        "reason": reason,
        "blocked_reason": reason,
        "risk_level": RISK_HIGH,
        "required_approval": True,
        "registry_patch": None,
        "warnings": [reason],
        **extra,
    }


def _review(reason: str, risk: str = RISK_MEDIUM, patch: dict | None = None,
            warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "verdict": VERDICT_REVIEW,
        "reason": reason,
        "blocked_reason": None,
        "risk_level": risk,
        "required_approval": True,
        "registry_patch": patch,
        "warnings": warnings or [],
    }


def _allow(reason: str, patch: dict, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "verdict": VERDICT_ALLOW,
        "reason": reason,
        "blocked_reason": None,
        "risk_level": RISK_LOW,
        "required_approval": False,
        "registry_patch": patch,
        "warnings": warnings or [],
    }


def preflight_expansion(
    site_candidate: dict[str, Any] | None = None,
    selector_candidate: dict[str, Any] | None = None,
    value_candidate: dict[str, Any] | None = None,
    action_candidate: str | None = None,
    business_profile: str = "",
    intended_purpose: str = "",
    raw_url_attempt: str | None = None,
    raw_selector_attempt: str | None = None,
    server_external_browser_attempt: bool = False,
) -> dict[str, Any]:
    """후보들을 정책 검증하여 verdict를 반환."""
    # 1. 가장 강한 차단 조건 먼저
    if server_external_browser_attempt:
        return _block("서버에서 외부 브라우저 실행 시도 — 차단")

    if raw_url_attempt:
        url_check = validate_raw_url(raw_url_attempt)
        if not url_check.get("ok"):
            return _block(f"raw URL 직접 실행 차단: {url_check.get('error', '미등록')}")

    if raw_selector_attempt:
        return _block("raw selector 직접 실행 차단 — selector_key 사용 필요")

    purpose_low = (intended_purpose or "").lower()
    for kw in _FORBIDDEN_PURPOSE_KEYWORDS:
        if kw in purpose_low:
            return _block(f"금지 목적: {kw}")

    if action_candidate:
        act_low = action_candidate.lower()
        for kw in _DESTRUCTIVE_ACTIONS:
            if kw in act_low:
                # destructive action은 자동 승인 불가, 검토 필요
                return _review(f"파괴/제출 action 후보: {action_candidate}",
                               risk=RISK_HIGH,
                               patch=None,
                               warnings=[f"{action_candidate} 자동 실행 불가"])

    # 2. value 후보 검증
    if value_candidate:
        raw = value_candidate.get("raw_value") or value_candidate.get("sample_safe_value", "")
        key = value_candidate.get("value_key", "")
        forbidden, reason = is_forbidden_value(str(raw), key)
        if forbidden:
            return _block(f"value 후보 차단: {reason}")

    # 3. selector 후보 안전성
    if selector_candidate:
        safety = validate_candidate_safety(selector_candidate)
        if not safety.get("safe"):
            return _block(f"selector candidate 차단: {safety.get('blocked_reason')}")
        # destructive/submit 후보는 review
        ctype = selector_candidate.get("candidate_type", "")
        if ctype in (CANDIDATE_SUBMIT_BUTTON, CANDIDATE_DESTRUCTIVE_BUTTON):
            return _review(f"{ctype} — HIGH risk, 자동 등록 불가",
                           risk=RISK_HIGH,
                           patch={"selector_candidate": selector_candidate},
                           warnings=["destructive/submit 후보"])
        risk_hint = selector_candidate.get("risk_hint", RISK_MEDIUM)
        if risk_hint == RISK_HIGH:
            return _review("HIGH risk hint", risk=RISK_HIGH,
                           patch={"selector_candidate": selector_candidate})
        label = selector_candidate.get("visible_label", "")
        if is_forbidden_label(label):
            return _block(f"민감 라벨: {label}")
        confidence = selector_candidate.get("confidence", "MEDIUM")
        if confidence == "LOW":
            return _review("confidence 낮음 — 검토 필요", risk=RISK_MEDIUM,
                           patch={"selector_candidate": selector_candidate})

    # 4. site 후보 검증
    if site_candidate:
        site_id = site_candidate.get("site_id", "")
        if not site_id:
            return _block("site_candidate에 site_id 없음")
        existing = get_site(site_id)
        if existing:
            if existing.execution_location != EXECUTION_LOCAL_AGENT_REQUIRED:
                return _block("execution_location이 LOCAL_AGENT_REQUIRED 아님")

    # 5. 자동 등록 가능 조건
    if selector_candidate:
        ctype = selector_candidate.get("candidate_type", "")
        risk_hint = selector_candidate.get("risk_hint", RISK_MEDIUM)
        if ctype in _AUTO_REGISTERABLE_TYPES and risk_hint == RISK_LOW:
            return _allow(
                "read-only 후보 자동 등록 가능",
                patch={"selector_candidate": selector_candidate,
                       "register_as": "selector_key_low_risk"},
            )

    # 6. 기본값 — 명시적 후보 없으면 review
    if not any([site_candidate, selector_candidate, value_candidate, action_candidate]):
        return _block("후보 없음 — preflight 입력 부족")

    return _review("기본 정책 — 사용자 검토 권장", risk=RISK_MEDIUM,
                   patch={"site_candidate": site_candidate,
                          "selector_candidate": selector_candidate,
                          "value_candidate": value_candidate})


def can_auto_approve(verdict_result: dict[str, Any]) -> bool:
    """자동 승인 가능 여부 — STEP 7 정책."""
    if verdict_result.get("verdict") != VERDICT_ALLOW:
        return False
    if verdict_result.get("required_approval"):
        return False
    if verdict_result.get("risk_level") != RISK_LOW:
        return False
    return True
