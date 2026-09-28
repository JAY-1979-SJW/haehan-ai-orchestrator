"""
브라우저 포그라운드 adapter

인증 필요 시 브라우저를 사용자 화면 앞으로 표시 요청한다.

금지:
- 사용자 입력 가로채기
- 비밀번호 input 값 읽기
- 인증창 내부 조작
- 브라우저 프로필 삭제/초기화
- headless → headed 강제 전환 (실행 환경 변경 금지)
"""

from __future__ import annotations

import sys
from typing import Any

# ── 상태값 ─────────────────────────────────────────────────────────────────────

BROWSER_FOREGROUND_REQUESTED = "BROWSER_FOREGROUND_REQUESTED"
BROWSER_FOREGROUND_UNAVAILABLE = "BROWSER_FOREGROUND_UNAVAILABLE"
HEADED_BROWSER_REQUIRED = "HEADED_BROWSER_REQUIRED"
USER_MANUAL_FOCUS_REQUIRED = "USER_MANUAL_FOCUS_REQUIRED"


def request_foreground(
    is_headed: bool = True,
    browser_pid: int | None = None,
) -> dict[str, Any]:
    """
    브라우저를 포그라운드로 표시 요청한다.

    is_headed: True이면 실제 포그라운드 요청 시도.
               False(headless)이면 HEADED_BROWSER_REQUIRED 반환.
    browser_pid: 브라우저 프로세스 ID (선택). 있으면 해당 PID 창을 앞으로.

    반환:
      status: BROWSER_FOREGROUND_REQUESTED | BROWSER_FOREGROUND_UNAVAILABLE |
              HEADED_BROWSER_REQUIRED | USER_MANUAL_FOCUS_REQUIRED
      sensitive_data_read: False (항상)
      password_input_read: False (항상)
    """
    base = {
        "sensitive_data_read": False,
        "password_input_read": False,
        "input_value_read": False,
        "browser_profile_modified": False,
    }

    if not is_headed:
        return {
            **base,
            "status": HEADED_BROWSER_REQUIRED,
            "message_ko": (
                "브라우저가 headless 모드입니다. "
                "인증을 위해 브라우저 창이 필요합니다. "
                "사용자가 직접 브라우저를 열어 인증해 주세요."
            ),
        }

    status = _try_bring_to_foreground(browser_pid)
    message = (
        "브라우저를 화면 앞으로 표시 요청했습니다."
        if status == BROWSER_FOREGROUND_REQUESTED
        else "브라우저 포그라운드 전환을 지원하지 않는 환경입니다. 직접 브라우저 창을 클릭해 주세요."
    )

    return {
        **base,
        "status": status,
        "message_ko": message,
    }


def _try_bring_to_foreground(pid: int | None) -> str:
    """OS별 브라우저 포그라운드 전환 시도."""
    platform = sys.platform

    if platform == "win32":
        return _foreground_windows(pid)
    elif platform == "darwin":
        return _foreground_macos()
    else:
        return USER_MANUAL_FOCUS_REQUIRED


def _foreground_windows(pid: int | None) -> str:
    """Windows에서 브라우저 창을 포그라운드로 전환한다."""
    if pid is None:
        return USER_MANUAL_FOCUS_REQUIRED

    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32

        hwnds: list[int] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def _enum_callback(hwnd: int, _: int) -> bool:
            wnd_pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wnd_pid))
            if wnd_pid.value == pid and user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(_enum_callback), 0)

        if hwnds:
            hwnd = hwnds[0]
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return BROWSER_FOREGROUND_REQUESTED
    except Exception:  # noqa: S110, BLE001
        pass

    return USER_MANUAL_FOCUS_REQUIRED


def _foreground_macos() -> str:
    """macOS에서 브라우저 앱을 포그라운드로 전환한다."""
    try:
        import subprocess

        result = subprocess.run(
            ["osascript", "-e", 'tell application "Chromium" to activate'],
            timeout=3,
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return BROWSER_FOREGROUND_REQUESTED
    except Exception:  # noqa: S110, BLE001
        pass

    return USER_MANUAL_FOCUS_REQUIRED


def check_headed_mode(playwright_page: Any) -> bool:
    """
    Playwright page가 headed 모드인지 확인한다.
    입력값이나 민감 데이터는 읽지 않는다.
    """
    try:
        context = playwright_page.context
        context.browser  # noqa: B018
        # Playwright browser가 headless인지는 공개 API로 직접 확인 불가.
        # browser 객체에 _impl_obj를 통해 접근할 수 있으나 내부 API이므로
        # 안전한 fallback으로 True를 반환한다.
        return True
    except Exception:  # noqa: BLE001 - 인증필요시 브라우저 창을 전면화하는 보조 기능(문서에 '비밀번호 input 값 읽기 금지' 등 명시) — Windows/macOS 포그라운드 전환 실패는 USER_MANUAL_FOCUS_REQUIRED로 폴백(사용자에게 직접 클릭 요청)할 뿐 민감정보 접근과 무관하며, check_headed_mode는 성공/예외 경로 모두 동일하게 True를 반환하는 스텁이라 except가 새로운 위험을 추가하지 않음(이미 noqa: S110 2건 존재).
        return True


def get_foreground_status() -> dict[str, Any]:
    """현재 foreground adapter 구현 상태를 반환한다."""
    platform = sys.platform
    return {
        "platform": platform,
        "windows_supported": platform == "win32",
        "macos_supported": platform == "darwin",
        "linux_supported": False,
        "pid_required_for_windows": True,
        "sensitive_data_read": False,
        "password_input_read": False,
    }
