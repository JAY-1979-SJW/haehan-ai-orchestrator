"""
Fallback 판정 엔진

서버 실패 시 로컬 전환 여부를 통합 판정한다.

원칙:
- fallback과 block을 명확히 분리
- 위험 작업(자동 투찰/서명/결제)은 fallback으로 자동화하지 않음
- cookie/session/password/OTP/인증서 전달 없음
"""
from __future__ import annotations

from typing import Any

# ── 판정 결과 상수 ─────────────────────────────────────────────────────────────

COMPLETE_ON_SERVER = "COMPLETE_ON_SERVER"
RETRY_ON_SERVER = "RETRY_ON_SERVER"
HANDOFF_TO_LOCAL_AGENT = "HANDOFF_TO_LOCAL_AGENT"
REQUIRE_USER_DIRECT_ACTION = "REQUIRE_USER_DIRECT_ACTION"
BLOCK = "BLOCK"

# ── fallback 유발 신호 ─────────────────────────────────────────────────────────

_FALLBACK_SIGNALS: frozenset[str] = frozenset({
    "http_401", "http_403",
    "login_required", "redirected_to_login",
    "cert_auth_detected", "captcha_detected",
    "security_program_required", "browser_unsupported",
    "blocked_by_site", "server_browser_not_allowed",
    "password_input_detected",
})

# ── 사용자 직접 수행 신호 ─────────────────────────────────────────────────────

_USER_DIRECT_SIGNALS: frozenset[str] = frozenset({
    "otp_detected",
    "e_signature_detected",
    "payment_or_transfer_detected",
    "bid_submit_detected",
    "contract_submit_detected",
})

# ── 절대 차단 신호 ─────────────────────────────────────────────────────────────

_BLOCK_SIGNALS: frozenset[str] = frozenset({
    "cookie_export", "session_export", "password_save",
    "cert_file_access", "npki_access",
    "auto_sign", "auto_bid_submit", "auto_payment",
    "auto_transfer", "auto_contract_submit",
    "token_export", "auth_header_export",
})

# ── HTTP 상태 → 판정 ──────────────────────────────────────────────────────────

_HTTP_STATUS_MAP: dict[int, str] = {
    401: HANDOFF_TO_LOCAL_AGENT,
    403: HANDOFF_TO_LOCAL_AGENT,
    429: RETRY_ON_SERVER,
    500: RETRY_ON_SERVER,
    502: RETRY_ON_SERVER,
    503: RETRY_ON_SERVER,
}


def _decide_blocking_or_user_direct(
    security_signals: list[str], action: str
) -> dict[str, Any] | None:
    """1. 절대 차단 신호 → 2. 사용자 직접 수행 신호 (순서 유지). 해당 없으면 None."""
    # 1. 절대 차단 신호
    for sig in security_signals:
        if sig in _BLOCK_SIGNALS:
            return _result(BLOCK, f"차단 신호: {sig!r}", sensitive_transfer_blocked=True)
    if action in _BLOCK_SIGNALS:
        return _result(BLOCK, f"차단 action: {action!r}", sensitive_transfer_blocked=True)

    # 2. 사용자 직접 수행 신호
    for sig in security_signals:
        if sig in _USER_DIRECT_SIGNALS:
            return _result(REQUIRE_USER_DIRECT_ACTION, f"사용자 직접 수행 신호: {sig!r}")
    return None


def _decide_signal_fallback(
    security_signals: list[str], action: str, domain_profile: dict[str, Any]
) -> dict[str, Any] | None:
    """5. 보안 신호 기반 fallback → 6. login LOCAL_REQUIRED. 해당 없으면 None."""
    # 5. 보안 신호 기반 fallback
    for sig in security_signals:
        if sig in _FALLBACK_SIGNALS:
            if domain_profile.get("server_to_local_fallback", True):
                return _result(HANDOFF_TO_LOCAL_AGENT, f"보안 신호 fallback: {sig!r}")
            else:
                return _result(REQUIRE_USER_DIRECT_ACTION, f"fallback 불가 도메인, 사용자 직접: {sig!r}")

    # 6. login_execution=LOCAL_REQUIRED 도메인에서 login action
    if "login" in action and domain_profile.get("login_execution") == "LOCAL_REQUIRED":
        return _result(HANDOFF_TO_LOCAL_AGENT, "login_execution=LOCAL_REQUIRED")
    return None


def decide_fallback(  # noqa: PLR0913 - 폴백 판정 공개 함수, 입력 시그니처 유지
    task: dict[str, Any],
    domain_profile: dict[str, Any],
    server_result: dict[str, Any],
    security_signals: list[str],
    error_type: str = "",
    http_status: int = 200,
    current_url_host: str = "",
) -> dict[str, Any]:
    """
    서버 실행 결과를 분석하여 다음 실행 위치를 결정한다.

    반환:
      decision, reason, fallback_to, user_message_ko,
      sensitive_transfer_blocked
    """
    action: str = (task.get("action") or "").lower()

    # 1~2. 절대 차단 신호 / 사용자 직접 수행 신호
    early = _decide_blocking_or_user_direct(security_signals, action)
    if early is not None:
        return early

    # 3. 서버 성공
    server_verdict = server_result.get("verdict") or server_result.get("status") or ""
    if http_status == 200 and server_verdict in ("LIVE_PASS", "SUCCESS", "OK"):
        if not any(sig in _FALLBACK_SIGNALS for sig in security_signals):
            return _result(COMPLETE_ON_SERVER, "서버 성공")

    # 4. HTTP 상태 기반 판정
    if http_status in _HTTP_STATUS_MAP:
        decision = _HTTP_STATUS_MAP[http_status]
        return _result(decision, f"HTTP {http_status} 감지")

    # 5~6. 보안 신호 기반 fallback / login LOCAL_REQUIRED
    signal_fallback = _decide_signal_fallback(security_signals, action, domain_profile)
    if signal_fallback is not None:
        return signal_fallback

    # 7. error_type 기반
    if error_type in ("timeout", "network_error", "connection_refused"):
        return _result(RETRY_ON_SERVER, f"재시도 가능 오류: {error_type!r}")

    # 8. 서버 verdict FAIL
    if server_verdict in ("LIVE_FAIL", "FAIL", "ERROR"):
        if domain_profile.get("server_to_local_fallback", True):
            return _result(HANDOFF_TO_LOCAL_AGENT, "서버 실패, 로컬 fallback")
        return _result(BLOCK, "서버 실패, fallback 불가", sensitive_transfer_blocked=False)

    # 9. 기본: 서버 완료
    return _result(COMPLETE_ON_SERVER, "기본: 서버 완료로 처리")


def _result(
    decision: str,
    reason: str,
    fallback_to: str = "LOCAL_AGENT",
    sensitive_transfer_blocked: bool = True,
) -> dict[str, Any]:
    _MSG = {
        COMPLETE_ON_SERVER: "서버에서 처리되었습니다.",
        RETRY_ON_SERVER: "서버에서 재시도합니다.",
        HANDOFF_TO_LOCAL_AGENT: "이 작업은 사용자 PC에서 계속 진행됩니다.",
        REQUIRE_USER_DIRECT_ACTION: "이 작업은 사용자가 직접 수행해야 합니다.",
        BLOCK: "이 작업은 자동화가 금지되어 있습니다.",
    }
    return {
        "decision": decision,
        "reason": reason,
        "fallback_to": fallback_to if decision == HANDOFF_TO_LOCAL_AGENT else None,
        "sensitive_transfer_blocked": sensitive_transfer_blocked,
        "user_message_ko": _MSG.get(decision, ""),
    }
