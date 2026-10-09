"""
인증 대기 컨트롤러

로컬 Playwright 에이전트가 로그인/인증 필요 상태를 감지했을 때
사용자에게 직접 인증을 요청하고 완료를 기다린다.

금지:
- 비밀번호 자동 입력
- OTP 자동 입력
- 인증서 비밀번호 자동 입력
- cookie/session/token 수집
- 인증서/NPKI 파일 접근
"""
from __future__ import annotations

import time
from typing import Any

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_AUTH_CANCELLED,
    STATUS_AUTH_COMPLETED,
    STATUS_AUTH_TIMEOUT,
    STATUS_AUTO_RESUME_READY,
    STATUS_USER_ACTION_REQUIRED,
    STATUS_WAITING_USER_AUTH,
    build_result,
)

# ── 사용자 안내 문구 ─────────────────────────────────────────────────────────

AUTH_GUIDE_MESSAGE = (
    "인증이 필요합니다.\n"
    "브라우저에서 직접 로그인 또는 인증을 진행해 주세요.\n"
    "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하거나 입력하지 않습니다.\n"
    "인증이 완료되면 작업은 자동으로 계속 진행됩니다."
)

# ── 인증 신호 종류 ───────────────────────────────────────────────────────────

AUTH_SIGNAL_LOGIN = "login_required"
AUTH_SIGNAL_CERT = "cert_auth_required"
AUTH_SIGNAL_OTP = "otp_required"

# ── 기본 timeout ─────────────────────────────────────────────────────────────

DEFAULT_AUTH_TIMEOUT_SEC = 300  # 5분


class AuthWaitState:
    """인증 대기 상태를 보관한다. 입력값은 읽지 않는다."""

    def __init__(
        self,
        task_id: str,
        auth_signal: str,
        url_host: str = "",
        timeout_sec: int = DEFAULT_AUTH_TIMEOUT_SEC,
    ) -> None:
        self.task_id = task_id
        self.auth_signal = auth_signal
        self.url_host = url_host
        self.timeout_sec = timeout_sec
        self._cancelled = False
        self._started_at = time.monotonic()

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def is_timed_out(self) -> bool:
        return (time.monotonic() - self._started_at) >= self.timeout_sec

    def elapsed_sec(self) -> float:
        return time.monotonic() - self._started_at


def enter_auth_wait(
    task_id: str,
    auth_signal: str,
    url_host: str = "",
    timeout_sec: int = DEFAULT_AUTH_TIMEOUT_SEC,
) -> dict[str, Any]:
    """
    인증 대기 상태에 진입하고 사용자 안내 결과를 반환한다.
    입력값(password/OTP/cert)은 읽지 않는다.
    """
    if auth_signal == AUTH_SIGNAL_OTP:
        status = STATUS_USER_ACTION_REQUIRED
    else:
        status = STATUS_WAITING_USER_AUTH

    return build_result(
        task_id=task_id,
        ok=False,
        status=status,
        current_url_host=url_host,
        message_ko=AUTH_GUIDE_MESSAGE,
        extra={
            "auth_signal": auth_signal,
            "auth_wait_active": True,
            "sensitive_data_collected": False,
            "password_auto_input": False,
            "otp_auto_input": False,
            "cert_password_auto_input": False,
        },
    )


def build_timeout_result(task_id: str, url_host: str = "") -> dict[str, Any]:
    """인증 timeout 결과를 반환한다."""
    return build_result(
        task_id=task_id,
        ok=False,
        status=STATUS_AUTH_TIMEOUT,
        current_url_host=url_host,
        message_ko="인증 대기 시간이 초과되었습니다. 작업이 취소됩니다.",
        extra={"auth_wait_active": False},
    )


def build_cancel_result(task_id: str, url_host: str = "") -> dict[str, Any]:
    """인증 취소 결과를 반환한다."""
    return build_result(
        task_id=task_id,
        ok=False,
        status=STATUS_AUTH_CANCELLED,
        current_url_host=url_host,
        message_ko="인증이 취소되었습니다.",
        extra={"auth_wait_active": False},
    )


def build_auth_completed_result(
    task_id: str,
    url_host: str = "",
    signals_cleared: list[str] | None = None,
) -> dict[str, Any]:
    """인증 완료 결과를 반환한다."""
    return build_result(
        task_id=task_id,
        ok=True,
        status=STATUS_AUTH_COMPLETED,
        current_url_host=url_host,
        message_ko="인증 완료. 작업을 자동으로 재개합니다.",
        extra={
            "auth_completed": True,
            "safe_to_resume": True,
            "signals_cleared": signals_cleared or [],
            "sensitive_data_collected": False,
            "auth_wait_active": False,
        },
    )


def build_auto_resume_ready_result(
    task_id: str,
    url_host: str = "",
    resumable_action: str = "",
) -> dict[str, Any]:
    """자동 재개 준비 완료 결과를 반환한다."""
    return build_result(
        task_id=task_id,
        ok=True,
        status=STATUS_AUTO_RESUME_READY,
        current_url_host=url_host,
        message_ko=f"자동 재개 준비 완료. action={resumable_action!r}",
        extra={
            "resumable_action": resumable_action,
            "sensitive_data_collected": False,
        },
    )


def wait_for_completion(
    state: AuthWaitState,
    detector_fn: Any,
    poll_interval_sec: float = 2.0,
) -> dict[str, Any]:
    """
    인증 완료를 polling으로 기다린다.

    detector_fn: auth_completion_detector.check_auth_completed(page) -> dict
                 호출자가 page 객체를 binding한 callable을 전달한다.

    반환: AUTH_COMPLETED / AUTH_TIMEOUT / AUTH_CANCELLED 결과 dict
    """
    while True:
        if state.is_cancelled():
            return build_cancel_result(state.task_id, state.url_host)

        if state.is_timed_out():
            return build_timeout_result(state.task_id, state.url_host)

        detection = detector_fn()
        if detection.get("auth_completed"):
            return build_auth_completed_result(
                task_id=state.task_id,
                url_host=state.url_host,
                signals_cleared=detection.get("signals_cleared", []),
            )

        time.sleep(poll_interval_sec)
