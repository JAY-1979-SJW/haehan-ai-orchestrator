"""
로컬 에이전트 보안 guard

위험 작업 실행 전 차단.
위험 신호 감지 시 USER_DIRECT_REQUIRED 반환.
민감값 수집 없음.

차단 대상:
- collect_password, collect_otp, collect_cookie, collect_session
- read_certificate_file, auto_bid_submit, auto_sign, auto_payment
- auto_final_submit, transfer_money, contract_submit
"""
from __future__ import annotations

from typing import Any

# ── 절대 차단 action ────────────────────────────────────────────────────────────

_ABSOLUTE_BLOCK_ACTIONS: frozenset[str] = frozenset({
    "collect_password", "collect_otp", "collect_cookie", "collect_session",
    "read_certificate_file", "auto_bid_submit", "auto_sign", "auto_payment",
    "auto_final_submit", "transfer_money", "contract_submit",
    "cookie_export", "session_export", "cookie_dump", "session_dump",
    "localStorage_dump", "sessionStorage_dump", "password_save",
    "cert_file_access", "npki_access", "auto_transfer",
    "auto_contract_submit", "token_export", "auth_header_export",
})

# ── 사용자 직접 수행 action ────────────────────────────────────────────────────

_USER_DIRECT_ACTIONS: frozenset[str] = frozenset({
    "cert_password_input", "otp_input", "final_submit",
    "confirm_payment", "confirm_transfer", "sign_document",
    "e_sign", "bid_final_submit", "contract_confirm",
})

# ── page 신호 → 사용자 직접 수행 필요 ─────────────────────────────────────────

_USER_DIRECT_PAGE_SIGNALS: frozenset[str] = frozenset({
    "otp", "otp_detected", "e_signature_detected",
    "bid_submit_detected", "payment_or_transfer_detected",
    "contract_submit_detected",
})

# ── 민감 필드 차단 ─────────────────────────────────────────────────────────────

_FORBIDDEN_TASK_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "Authorization", "password", "otp",
    "certificate_password", "certificate_file_path", "localStorage",
    "sessionStorage", "token", "access_token", "refresh_token",
    "npki", "private_key", "auth_header",
})


def validate_task_before_run(task: dict[str, Any]) -> dict[str, Any]:
    """
    task 실행 전 보안 검증.

    반환:
      allowed: bool
      user_direct_required: bool
      reason: str
    """
    action = (task.get("action") or "").lower()

    # 절대 차단
    if action in _ABSOLUTE_BLOCK_ACTIONS:
        return _guard(allowed=False, reason=f"차단 action: {action!r}")

    # 사용자 직접 수행 action
    if action in _USER_DIRECT_ACTIONS:
        return _guard(allowed=False, user_direct=True, reason=f"사용자 직접 수행 action: {action!r}")

    # 민감 필드 포함 여부
    for field in _FORBIDDEN_TASK_FIELDS:
        if field in task:
            return _guard(allowed=False, reason=f"민감 필드 포함: {field!r}")

    return _guard(allowed=True, reason="")


def detect_user_direct_required(
    task: dict[str, Any],
    page_signal: str | None,
) -> dict[str, Any]:
    """
    page 신호를 분석하여 사용자 직접 수행이 필요한지 판정한다.
    신호 값(OTP 번호 등)은 수집하지 않는다.

    page_signal: security_signal_detector가 반환한 신호 문자열 (없으면 None)
    """
    if page_signal in _USER_DIRECT_PAGE_SIGNALS:
        return _guard(
            allowed=False,
            user_direct=True,
            reason=f"페이지 신호 감지: {page_signal!r}. 사용자 직접 처리 필요.",
        )
    return _guard(allowed=True, reason="")


def block_forbidden_action(task: dict[str, Any]) -> dict[str, Any]:
    """
    task의 action이 절대 차단 목록에 있으면 BLOCK 결과를 반환한다.
    """
    action = (task.get("action") or "").lower()
    if action in _ABSOLUTE_BLOCK_ACTIONS:
        return {"blocked": True, "reason": f"차단 action: {action!r}"}
    return {"blocked": False, "reason": ""}


def sanitize_runtime_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    런타임 결과에서 민감 필드를 제거한다.
    result_sanitizer.sanitize_result와 동일한 역할 (guard 레이어에서도 호출 가능).
    """
    from core.agent_runtime.runtime.result_sanitizer import sanitize_result
    return sanitize_result(result)


def _guard(
    allowed: bool,
    reason: str,
    user_direct: bool = False,
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "user_direct_required": user_direct,
        "reason": reason,
    }
