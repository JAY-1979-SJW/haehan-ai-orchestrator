"""
사용자 주의 알림 모듈

브라우저를 사용자 화면 앞으로 표시하고 OS 알림을 발송한다.
알림은 "사용자 직접 입력 필요"를 알려주는 역할만 한다.

금지:
- 자동 입력 안내 또는 자동입력 실행
- 민감정보 포함 메시지 출력
- 알림 클릭으로 submit/sign/payment/bid 실행
- OS 시작프로그램/서비스 자동 등록
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
    "인증 대기 중입니다. {remaining_sec}초 후 자동 취소됩니다.\n브라우저에서 직접 인증을 완료해 주세요."
)

_CANCEL_NOTICE = "인증이 취소되었습니다. 작업이 종료됩니다."

_NO_AUTO_INPUT_NOTICE = (
    "이 단계에서는 비밀번호, OTP, 인증서 비밀번호를 앱이 자동으로 입력하지 않습니다.\n사용자가 직접 입력해 주세요."
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


def request_browser_foreground(
    is_headed: bool = True,
    browser_pid: int | None = None,
) -> dict[str, Any]:
    """
    브라우저를 사용자 화면 앞으로 표시 요청한다.
    browser_foreground_adapter를 통해 실제 OS 레벨 전환을 시도한다.
    실패해도 WARN 처리하며 작업은 계속된다.
    """
    try:
        from core.agent_runtime.runtime.playwright.browser_foreground_adapter import (
            request_foreground,
        )

        result = request_foreground(is_headed=is_headed, browser_pid=browser_pid)
    except Exception as exc:  # noqa: BLE001 - 사용자 개입 필요 알림 -- 브라우저 포그라운드 전환 실패는 UNAVAILABLE 상태로 보고, 알림 발송 실패는 NOTIFICATION_FAILED로 기록 후 계속 진행(알림은 부가 기능)
        result = {
            "status": "BROWSER_FOREGROUND_UNAVAILABLE",
            "message_ko": f"foreground 전환 오류: {type(exc).__name__}",
            "sensitive_data_read": False,
            "password_input_read": False,
            "input_value_read": False,
            "browser_profile_modified": False,
        }

    result["action"] = "bring_browser_to_foreground"
    result["headed_mode_required"] = True
    result["sensitive_data_read"] = False
    result["password_input_read"] = False
    return result


def notify_auth_required(
    auth_signal: str = "",
    is_headed: bool = True,
    browser_pid: int | None = None,
) -> dict[str, Any]:
    """
    인증 필요 알림을 발송하고 브라우저를 포그라운드로 표시 요청한다.

    반환:
      status: WAITING_USER_AUTH
      notification_status: NOTIFICATION_SENT | FALLBACK_MESSAGE_ONLY | ...
      foreground_status: BROWSER_FOREGROUND_REQUESTED | ...
      message_ko: str
      password_collected: False
      otp_collected: False
      certificate_password_collected: False
      cookie_exported: False
      session_exported: False
    """
    # OS 알림 발송
    try:
        from core.agent_runtime.runtime.notify.user_notification_adapter import (
            notify_auth_required as _notify,
        )

        notification_result = _notify(auth_signal=auth_signal)
        notification_status = notification_result["status"]
    except Exception:  # noqa: BLE001 - 사용자 개입 필요 알림 -- 브라우저 포그라운드 전환 실패는 UNAVAILABLE 상태로 보고, 알림 발송 실패는 NOTIFICATION_FAILED로 기록 후 계속 진행(알림은 부가 기능)
        notification_status = "NOTIFICATION_FAILED"

    # 브라우저 포그라운드 요청
    foreground_result = request_browser_foreground(
        is_headed=is_headed,
        browser_pid=browser_pid,
    )
    foreground_status = foreground_result.get("status", "BROWSER_FOREGROUND_UNAVAILABLE")

    return {
        "status": "WAITING_USER_AUTH",
        "notification_status": notification_status,
        "foreground_status": foreground_status,
        "message_ko": _AUTH_NOTICE_TEMPLATE,
        "auth_signal": auth_signal,
        "password_collected": False,
        "otp_collected": False,
        "certificate_password_collected": False,
        "cookie_exported": False,
        "session_exported": False,
        "storage_state_exported": False,
        "sensitive_data_included": False,
        "password_auto_input": False,
        "otp_auto_input": False,
        "cert_password_auto_input": False,
        "submit_action_triggered": False,
        "sign_action_triggered": False,
        "payment_action_triggered": False,
        "bid_action_triggered": False,
    }


def get_notifier_status() -> dict[str, Any]:
    """현재 notifier 구현 상태를 반환한다."""
    return {
        "contract_defined": True,
        "safe_message_implemented": True,
        "os_notification_implemented": True,
        "browser_foreground_implemented": True,
        "os_tray_resident_implemented": False,
        "os_autostart_implemented": False,
        "next_step": "OS 트레이 상주/자동시작은 별도 승인 후 진행",
    }
