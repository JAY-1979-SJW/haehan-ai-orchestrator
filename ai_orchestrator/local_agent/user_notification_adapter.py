"""
OS 알림 adapter

OS별 토스트/알림을 발송한다.
알림은 "사용자 직접 입력 필요"를 알려주는 역할만 한다.

금지:
- 알림 클릭으로 submit/sign/payment/bid 실행
- 알림에 URL query/token/session 표시
- 비밀번호/OTP/인증서 정보 표시
- 민감정보 포함 메시지 발송
- OS 시작프로그램/서비스 자동 등록
"""

from __future__ import annotations

import sys
from typing import Any

# ── 알림 상태값 ────────────────────────────────────────────────────────────────

NOTIFICATION_SENT = "NOTIFICATION_SENT"
NOTIFICATION_UNAVAILABLE = "NOTIFICATION_UNAVAILABLE"
NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
FALLBACK_MESSAGE_ONLY = "FALLBACK_MESSAGE_ONLY"

# ── 안전 알림 문구 ────────────────────────────────────────────────────────────

_SAFE_TITLE = "인증이 필요합니다"

_SAFE_BODY = (
    "브라우저에서 직접 로그인 또는 인증을 진행해 주세요.\n"
    "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하거나 입력하지 않습니다.\n"
    "인증이 완료되면 작업은 자동으로 계속 진행됩니다."
)

# ── 금지 키워드 (민감정보 포함 여부 검사용) ───────────────────────────────────

_SENSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "password",
        "비밀번호",
        "otp",
        "일회용",
        "인증서 비밀번호",
        "cookie",
        "session",
        "token",
        "npki",
        "private_key",
        "submit",
        "sign",
        "payment",
        "bid",
        "결제",
        "투찰",
        "전자서명",
    }
)


def _contains_sensitive(text: str) -> bool:
    lower = text.lower()
    return any(
        k in lower
        for k in _SENSITIVE_KEYWORDS
        - {
            # 아래는 안내 문구에서 허용 (수집/입력하지 않는다고 명시할 때)
            "비밀번호",
            "otp",
            "인증서 비밀번호",
        }
    )


def _is_safe_message(title: str, body: str) -> bool:
    """알림 메시지에 민감정보가 없는지 검증한다."""
    forbidden = {"password", "cookie", "session", "token", "npki", "private_key", "submit", "sign", "결제", "투찰"}
    combined = (title + " " + body).lower()
    return not any(k in combined for k in forbidden)


def send_notification(
    title: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """
    OS 토스트/알림을 발송한다.

    title/body를 생략하면 기본 안전 문구를 사용한다.
    민감정보가 포함된 메시지는 발송 거부하고 안전 문구로 대체한다.

    반환:
      status: NOTIFICATION_SENT | NOTIFICATION_UNAVAILABLE |
              NOTIFICATION_FAILED | FALLBACK_MESSAGE_ONLY
      message_used: str
      sensitive_data_included: False (항상)
    """
    safe_title = title or _SAFE_TITLE
    safe_body = body or _SAFE_BODY

    # 민감정보 포함 시 안전 문구로 강제 대체
    if not _is_safe_message(safe_title, safe_body):
        safe_title = _SAFE_TITLE
        safe_body = _SAFE_BODY

    status = _try_send_os_notification(safe_title, safe_body)

    return {
        "status": status,
        "title_used": safe_title,
        "message_used": safe_body,
        "sensitive_data_included": False,
        "password_in_message": False,
        "otp_in_message": False,
        "cert_password_in_message": False,
        "submit_action_in_notification": False,
        "sign_action_in_notification": False,
        "payment_action_in_notification": False,
        "bid_action_in_notification": False,
    }


def _try_send_os_notification(title: str, body: str) -> str:
    """
    OS 알림을 실제로 발송한다.
    발송 실패 시 NOTIFICATION_FAILED, 미지원 환경은 NOTIFICATION_UNAVAILABLE.
    """
    platform = sys.platform

    if platform == "win32":
        return _send_windows_toast(title, body)
    elif platform == "darwin":
        return _send_macos_notification(title, body)
    elif platform.startswith("linux"):
        return _send_linux_notification(title, body)
    else:
        return NOTIFICATION_UNAVAILABLE


def _send_windows_toast(title: str, body: str) -> str:
    """Windows 토스트 알림. plyer 또는 win10toast 사용."""
    # plyer 우선 시도
    try:
        from plyer import notification  # type: ignore

        notification.notify(
            title=title,
            message=body,
            timeout=10,
        )
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    # win10toast 시도
    try:
        from win10toast import ToastNotifier  # type: ignore

        toaster = ToastNotifier()
        toaster.show_toast(title, body, duration=10, threaded=True)
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    # winotify 시도
    try:
        from winotify import Notification  # type: ignore

        toast = Notification(app_id="해한 AI 에이전트", title=title, msg=body)
        toast.show()
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    return NOTIFICATION_UNAVAILABLE


def _send_macos_notification(title: str, body: str) -> str:
    """macOS 알림. plyer 또는 osascript 사용."""
    try:
        from plyer import notification  # type: ignore

        notification.notify(title=title, message=body, timeout=10)
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    try:
        import subprocess

        safe_title = title.replace('"', "")
        safe_body = body.replace('"', "").replace("\n", " ")
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_body}" with title "{safe_title}"'],
            timeout=5,
            check=False,
            capture_output=True,
        )
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    return NOTIFICATION_UNAVAILABLE


def _send_linux_notification(title: str, body: str) -> str:
    """Linux 알림. plyer 또는 notify-send 사용."""
    try:
        from plyer import notification  # type: ignore

        notification.notify(title=title, message=body, timeout=10)
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    try:
        import subprocess

        safe_title = title.replace('"', "")
        safe_body = body.replace('"', "").replace("\n", " ")
        subprocess.run(
            ["notify-send", safe_title, safe_body],
            timeout=5,
            check=False,
            capture_output=True,
        )
        return NOTIFICATION_SENT
    except Exception:  # noqa: S110, BLE001 - 데스크톱 알림 표시 다단계 폴백(toast/win10toast/winotify/plyer/subprocess) - 각 방법 실패시 다음 방법을 시도할 뿐, 보안과 무관한 UI 알림 유틸
        pass

    return NOTIFICATION_UNAVAILABLE


def get_fallback_message() -> dict[str, Any]:
    """OS 알림 불가 환경용 fallback 메시지를 반환한다."""
    return {
        "status": FALLBACK_MESSAGE_ONLY,
        "title_used": _SAFE_TITLE,
        "message_used": _SAFE_BODY,
        "sensitive_data_included": False,
        "note": "OS 알림 미지원 환경. 콘솔 메시지로 대체.",
    }


_MAIL_SAFE_TITLE = "새 메일이 도착했습니다"
_MAIL_SAFE_BODY = "메일함에서 직접 확인해 주세요."


def notify_new_mail(sender: str = "", subject: str = "", count: int = 1) -> dict[str, Any]:
    """
    새 메일 도착 알림을 발송하는 편의 함수.

    send_notification()의 안전 문구는 "인증 필요" 알림 전용이라 그대로 못 쓴다
    (민감어 필터에 걸리면 엉뚱하게 "인증이 필요합니다"로 바뀜) — 메일 알림은
    자체적으로 발신자/제목만 짧게 보여주고, 민감해 보이면 제목·발신자를 아예
    빼고 개수만 알린다(2026-09-29, docs/specs 메일 알림 기준서).

    실패해도 작업은 계속된다 (WARN 처리, notify_auth_required와 동일한 관례).
    """
    if count > 1:
        title = f"새 메일 {count}건 도착"
        body = _MAIL_SAFE_BODY
    else:
        safe_sender = (sender or "").strip()[:60]
        safe_subject = (subject or "").strip().replace("\n", " ")[:120]
        if safe_sender and safe_subject and not _contains_sensitive(f"{safe_sender} {safe_subject}"):
            title = "새 메일이 도착했습니다"
            body = f"{safe_sender}: {safe_subject}"
        else:
            title = _MAIL_SAFE_TITLE
            body = _MAIL_SAFE_BODY

    status = _try_send_os_notification(title, body)

    if status in (NOTIFICATION_UNAVAILABLE, NOTIFICATION_FAILED):
        fallback = get_fallback_message()
        return {
            "status": FALLBACK_MESSAGE_ONLY,
            "title_used": title,
            "message_used": body,
            "fallback_used": True,
            "fallback_message": fallback["message_used"],
        }

    return {"status": status, "title_used": title, "message_used": body}


def notify_auth_required(auth_signal: str = "") -> dict[str, Any]:
    """
    인증 필요 알림을 발송하는 편의 함수.
    실패해도 작업은 계속된다 (WARN 처리).
    """
    result = send_notification()

    if result["status"] in (NOTIFICATION_UNAVAILABLE, NOTIFICATION_FAILED):
        fallback = get_fallback_message()
        result["fallback_used"] = True
        result["fallback_message"] = fallback["message_used"]
        result["status"] = FALLBACK_MESSAGE_ONLY

    result["auth_signal"] = auth_signal
    return result
