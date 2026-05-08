"""
사용자 주의 알림 모듈

브라우저를 사용자 화면 앞으로 표시하고 안내 메시지를 생성한다.

이번 구현 범위:
- notifier contract 및 safe message 정의
- OS 트레이/토스트 실제 구현은 다음 단계에서 진행

금지:
- 자동 입력 안내 또는 자동입력 실행
- 민감정보 포함 메시지 출력
"""
from __future__ import annotations

from typing import Any

# ── 안내 메시지 템플릿 ────────────────────────────────────────────────────────

_AUTH_NOTICE_TEMPLATE = (
    "인증이 필요합니다.\n"
    "브라우저에서 직접 로그인 또는 인증을 진행해 주세요.\n"
    "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하거나 입력하지 않습니다.\n"
    "인증이 완료되면 작업은 자동으로 계속 진행됩니다."
)

_TIMEOUT_NOTICE_TEMPLATE = (
    "인증 대기 중입니다. {remaining_sec}초 후 자동 취소됩니다.\n"
    "브라우저에서 직접 인증을 완료해 주세요."
)

_CANCEL_NOTICE = "인증이 취소되었습니다. 작업이 종료됩니다."

_NO_AUTO_INPUT_NOTICE = (
    "이 단계에서는 비밀번호, OTP, 인증서 비밀번호를 앱이 자동으로 입력하지 않습니다.\n"
    "사용자가 직접 입력해 주세요."
)


def build_auth_attention_notice(
    auth_signal: str = "",
    timeout_sec: int = 300,
) -> dict[str, Any]:
    """
    인증 대기 중 사용자에게 표시할 안내를 생성한다.
    민감정보는 포함하지 않는다.
    """
    return {
        "notice_type": "auth_required",
        "message_ko": _AUTH_NOTICE_TEMPLATE,
        "no_auto_input_notice": _NO_AUTO_INPUT_NOTICE,
        "auth_signal": auth_signal,
        "timeout_sec": timeout_sec,
        "headed_mode_required": True,
        "browser_foreground_required": True,
        "sensitive_data_included": False,
        "password_auto_input": False,
        "otp_auto_input": False,
        "cert_password_auto_input": False,
    }


def build_timeout_notice(remaining_sec: int) -> dict[str, Any]:
    """timeout 임박 안내를 생성한다."""
    return {
        "notice_type": "auth_timeout_warning",
        "message_ko": _TIMEOUT_NOTICE_TEMPLATE.format(remaining_sec=remaining_sec),
        "sensitive_data_included": False,
    }


def build_cancel_notice() -> dict[str, Any]:
    """취소 안내를 생성한다."""
    return {
        "notice_type": "auth_cancelled",
        "message_ko": _CANCEL_NOTICE,
        "sensitive_data_included": False,
    }


def request_browser_foreground() -> dict[str, Any]:
    """
    브라우저를 사용자 화면 앞으로 표시 요청 contract를 반환한다.
    실제 OS 레벨 표시는 다음 단계에서 구현한다.
    """
    return {
        "action": "bring_browser_to_foreground",
        "headed_mode_required": True,
        "implemented": False,
        "note": "OS 트레이/토스트 실제 구현은 다음 단계에서 진행",
    }


def get_notifier_status() -> dict[str, Any]:
    """현재 notifier 구현 상태를 반환한다."""
    return {
        "contract_defined": True,
        "safe_message_implemented": True,
        "os_tray_implemented": False,
        "os_toast_implemented": False,
        "browser_foreground_implemented": False,
        "next_step": "OS 트레이/토스트 알림 실제 구현",
    }
