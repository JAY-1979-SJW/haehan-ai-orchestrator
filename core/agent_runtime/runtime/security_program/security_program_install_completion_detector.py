"""Security Program Install Completion Detector — 설치 전후 페이지 비교로 완료 감지."""
from __future__ import annotations

from typing import Any

from core.agent_runtime.runtime.security_program.security_program_detector import detect_security_signals

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)

# 결과 상태
DETECTION_INSTALL_COMPLETED = "INSTALL_COMPLETED_DETECTED"
DETECTION_INSTALL_NOT_DETECTED = "INSTALL_NOT_DETECTED"
DETECTION_PARTIAL_RESOLVED = "PARTIAL_RESOLVED"
DETECTION_HEADLESS_REQUIRES_HEADED = "HEADLESS_REQUIRES_HEADED"


def detect_install_completion(
    before_page_data: dict[str, Any],
    after_page_data: dict[str, Any],
    headed: bool = True,
) -> dict[str, Any]:
    """
    설치 전 page_data와 설치 후 page_data를 비교해 완료 여부를 판단한다.

    headless 환경에서는 로컬 브릿지 기반 설치 감지가 불가능하므로
    HEADLESS_REQUIRES_HEADED 반환.
    """
    if not headed:
        return _result(
            status=DETECTION_HEADLESS_REQUIRES_HEADED,
            install_detected=False,
            message="headless 환경에서는 로컬 설치 브릿지 감지 불가. headed 브라우저로 재접속 필요.",
            signals_before=[],
            signals_after=[],
            signals_resolved=[],
        )

    before = detect_security_signals(before_page_data)
    after = detect_security_signals(after_page_data)

    before_signals = set(before["signals"])
    after_signals = set(after["signals"])
    resolved = before_signals - after_signals

    # 전부 해소
    if before_signals and not after_signals:
        return _result(
            status=DETECTION_INSTALL_COMPLETED,
            install_detected=True,
            message="모든 보안프로그램 신호가 해소되었습니다.",
            signals_before=sorted(before_signals),
            signals_after=[],
            signals_resolved=sorted(resolved),
        )

    # 일부 해소
    if resolved:
        return _result(
            status=DETECTION_PARTIAL_RESOLVED,
            install_detected=False,
            message=f"일부 보안프로그램 신호 해소: {sorted(resolved)}. 남은 신호: {sorted(after_signals)}",
            signals_before=sorted(before_signals),
            signals_after=sorted(after_signals),
            signals_resolved=sorted(resolved),
        )

    # 미해소
    return _result(
        status=DETECTION_INSTALL_NOT_DETECTED,
        install_detected=False,
        message="설치가 감지되지 않았습니다. 설치 마법사가 완료되었는지 확인해 주세요.",
        signals_before=sorted(before_signals),
        signals_after=sorted(after_signals),
        signals_resolved=[],
    )


def is_retry_ready(detection_result: dict[str, Any]) -> bool:
    """원래 작업 재시도 준비 여부."""
    return detection_result.get("status") == DETECTION_INSTALL_COMPLETED


def _result(**fields) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in fields.items():
        if k.lower() in ("local_path", "full_path", "installer_path"):
            continue
        if v is not None:
            result[k] = v
    for f in _SAFE_FIELDS:
        result[f] = False
    return result
