"""Unknown Site Fallback Policy — 처음 보는 사이트도 기본 처리 가능하게 한다."""

from __future__ import annotations

from typing import Any

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)

# action → grade 매핑 (unknown site 기준)
_UNKNOWN_SITE_ACTION_GRADE: dict[str, str] = {
    # AUTO_ALLOWED
    "read_page": GRADE_AUTO_ALLOWED,
    "readonly_explore": GRADE_AUTO_ALLOWED,
    "search_content": GRADE_AUTO_ALLOWED,
    "find_notice": GRADE_AUTO_ALLOWED,
    "extract_text": GRADE_AUTO_ALLOWED,
    "extract_table": GRADE_AUTO_ALLOWED,
    "summarize": GRADE_AUTO_ALLOWED,
    "generate_draft": GRADE_AUTO_ALLOWED,
    "capture_screenshot": GRADE_AUTO_ALLOWED,
    "open_url": GRADE_AUTO_ALLOWED,
    "download_document": GRADE_AUTO_ALLOWED,
    "save_draft": GRADE_AUTO_ALLOWED,
    "preview": GRADE_AUTO_ALLOWED,
    "fill_non_sensitive_form": GRADE_AUTO_ALLOWED,
    # USER_DELEGATED_PERMISSION_REQUIRED
    "write_post": GRADE_USER_DELEGATED,
    "publish_post": GRADE_USER_DELEGATED,
    "write_comment": GRADE_USER_DELEGATED,
    "update_post": GRADE_USER_DELEGATED,
    "delete_post": GRADE_USER_DELEGATED,
    "send_message": GRADE_USER_DELEGATED,
    "upload_file": GRADE_USER_DELEGATED,
    "submit_non_legal_form": GRADE_USER_DELEGATED,
    "change_visibility": GRADE_USER_DELEGATED,
    "schedule_publish": GRADE_USER_DELEGATED,
    # USER_DIRECT_REQUIRED
    "login_password_input": GRADE_USER_DIRECT,
    "otp_input": GRADE_USER_DIRECT,
    "cert_password_input": GRADE_USER_DIRECT,
    "e_sign": GRADE_USER_DIRECT,
    "bid_final_submit": GRADE_USER_DIRECT,
    "payment": GRADE_USER_DIRECT,
    "transfer": GRADE_USER_DIRECT,
    "contract_submit": GRADE_USER_DIRECT,
    "identity_verification": GRADE_USER_DIRECT,
    # BLOCKED
    "password_save": GRADE_BLOCKED,
    "otp_save": GRADE_BLOCKED,
    "cert_password_save": GRADE_BLOCKED,
    "cookie_export": GRADE_BLOCKED,
    "session_export": GRADE_BLOCKED,
    "token_export": GRADE_BLOCKED,
    "storage_state_export": GRADE_BLOCKED,
    "cert_file_access": GRADE_BLOCKED,
    "npki_access": GRADE_BLOCKED,
    "captcha_bypass": GRADE_BLOCKED,
    "account_bypass": GRADE_BLOCKED,
    "stealth_evasion": GRADE_BLOCKED,
    "bulk_spam_post": GRADE_BLOCKED,
    "bulk_spam_comment": GRADE_BLOCKED,
    "auto_payment": GRADE_BLOCKED,
    "auto_transfer": GRADE_BLOCKED,
    "auto_bid_submit": GRADE_BLOCKED,
    "auto_esign": GRADE_BLOCKED,
    "unauthorized_publish": GRADE_BLOCKED,
    "unauthorized_delete": GRADE_BLOCKED,
}

# risk signal → USER_DIRECT_REQUIRED로 격상하는 키워드
_RISK_SIGNAL_DIRECT = frozenset(["payment", "sign", "bid", "transfer", "legal"])


def get_action_grade_for_unknown_site(action: str, risk_signals: list[str] | None = None) -> str:
    """
    알 수 없는 사이트에서 action의 실행 등급을 반환한다.
    risk_signals가 있으면 일부 action을 USER_DIRECT로 격상.
    """
    grade = _UNKNOWN_SITE_ACTION_GRADE.get(action, GRADE_USER_DELEGATED)

    # risk signal 있으면 DELEGATED → DIRECT 격상
    if grade == GRADE_USER_DELEGATED and risk_signals and any(r in _RISK_SIGNAL_DIRECT for r in risk_signals):
        return GRADE_USER_DIRECT

    return grade


def is_allowed_on_unknown_site(action: str, risk_signals: list[str] | None = None) -> bool:
    grade = get_action_grade_for_unknown_site(action, risk_signals)
    return grade in (GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED)


def is_blocked_on_unknown_site(action: str) -> bool:
    return _UNKNOWN_SITE_ACTION_GRADE.get(action) == GRADE_BLOCKED


def evaluate_unknown_site(
    action: str,
    risk_signals: list[str] | None = None,
    has_permission: bool = False,
) -> dict[str, Any]:
    """
    unknown site에서 action 실행 가능 여부를 평가한다.
    반환: {grade, executable, reason}
    """
    grade = get_action_grade_for_unknown_site(action, risk_signals)

    if grade == GRADE_BLOCKED:
        return {"grade": grade, "executable": False, "reason": "BLOCKED action"}

    if grade == GRADE_AUTO_ALLOWED:
        return {"grade": grade, "executable": True, "reason": "AUTO_ALLOWED on unknown site"}

    if grade == GRADE_USER_DIRECT:
        return {"grade": grade, "executable": False, "reason": "USER_DIRECT_REQUIRED — 사용자 직접 조작 필요"}

    # GRADE_USER_DELEGATED
    if has_permission:
        return {"grade": grade, "executable": True, "reason": "USER_DELEGATED — permission 확인됨"}

    return {"grade": grade, "executable": False, "reason": "USER_DELEGATED_PERMISSION_REQUIRED"}
