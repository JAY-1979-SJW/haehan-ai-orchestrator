"""Windows 인증 팝업 감지 모듈.

Chrome 비밀번호 관리자가 비밀번호 열람 시 띄우는
Windows PIN/비밀번호 확인 팝업을 감지하고, 사용자에게
반복 알림을 보내며 대기한다.
"""

from __future__ import annotations

import ctypes
import threading
import time

user32 = ctypes.windll.user32

# Windows 인증 팝업 제목 패턴 (한/영 혼용)
_AUTH_TITLES = (
    "Windows Security",
    "Windows 보안",
    "사용자 본인인지 확인",  # ← 실제 확인된 제목
    "신원 확인",
    "Verify your identity",
    "User Account Control",
    "사용자 계정 컨트롤",
    "Credential Required",
    "자격 증명 필요",
    "PIN을 입력하세요",
)


# ---------------------------------------------------------------------------
# 창 제목 조회
# ---------------------------------------------------------------------------


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _enum_all_titles() -> list[str]:
    """현재 열린 모든 최상위 창 제목 목록 반환."""
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    def _cb(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            t = _get_window_title(hwnd)
            if t:
                titles.append(t)
        return True

    user32.EnumWindows(_cb, 0)
    return titles


def _is_auth_popup(title: str) -> bool:
    tl = title.lower()
    return any(pat.lower() in tl for pat in _AUTH_TITLES)


def _any_auth_popup_visible() -> str | None:
    """열린 창 중 인증 팝업이 있으면 그 제목 반환, 없으면 None."""
    for t in _enum_all_titles():
        if _is_auth_popup(t):
            return t
    return None


# ---------------------------------------------------------------------------
# 대기 함수
# ---------------------------------------------------------------------------


def wait_for_popup(timeout: float = 60.0, poll: float = 0.25) -> bool:
    """인증 팝업이 뜰 때까지 대기. 감지되면 True 반환.

    포그라운드 창뿐 아니라 열린 모든 창을 폴링하므로
    팝업이 뒤에 가려진 경우도 감지한다.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = _any_auth_popup_visible()
        if found:
            return True
        time.sleep(poll)
    return False


def wait_for_popup_close(timeout: float = 180.0, poll: float = 0.4) -> bool:
    """팝업이 닫힐 때까지 대기. 닫히면 True 반환."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _any_auth_popup_visible():
            # 닫힌 것 같으면 한 번 더 확인 (깜빡임 방지)
            time.sleep(0.5)
            if not _any_auth_popup_visible():
                return True
        time.sleep(poll)
    return False


# ---------------------------------------------------------------------------
# 사용자 알림
# ---------------------------------------------------------------------------


def _beep_loop(stop_evt: threading.Event, count: int = 5, interval: float = 1.5) -> None:
    """stop_evt가 설정되거나 count 회 반복될 때까지 알림음 재생."""
    try:
        import winsound

        for _ in range(count):
            if stop_evt.is_set():
                break
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            time.sleep(interval)
    except Exception:  # noqa: BLE001 - 알림음(MessageBeep)/토스트 알림 표시 실패 무시 — 사용자 알림 실패일 뿐 Windows 인증 팝업 감지/대기 로직 자체에는 영향 없음
        pass


def _toast(title: str, msg: str) -> None:
    """Windows 토스트 알림 (win10toast 또는 winrt 사용)."""
    try:
        from win10toast import ToastNotifier  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)

        ToastNotifier().show_toast(title, msg, duration=8, threaded=True)
        return
    except ImportError:
        pass
    try:
        import winrt.windows.data.xml.dom as wxml  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)
        import winrt.windows.ui.notifications as wun  # type: ignore[import-not-found]

        mgr = wun.ToastNotificationManager
        notifier = mgr.create_toast_notifier("Chrome")
        xml_str = f"""<toast><visual><binding template='ToastText02'>
            <text id='1'>{title}</text>
            <text id='2'>{msg}</text>
        </binding></visual></toast>"""
        doc = wxml.XmlDocument()
        doc.load_xml(xml_str)
        notifier.show(wun.ToastNotification(doc))
    except Exception:  # noqa: BLE001 - 알림음(MessageBeep)/토스트 알림 표시 실패 무시 — 사용자 알림 실패일 뿐 Windows 인증 팝업 감지/대기 로직 자체에는 영향 없음
        pass


def notify_user(site: str) -> threading.Event:
    """콘솔 출력 + 알림음 + Windows 토스트로 사용자에게 PIN 입력 안내."""
    banner = "=" * 62
    msg = (
        f"\n{banner}\n"
        f"  🔐  Windows PIN 입력 요청\n"
        f"  사이트  : {site}\n"
        f"  행동    : 화면 팝업에 Windows PIN을 입력하고 확인을 누르세요\n"
        f"  (닫지 말고 PIN 입력 후 확인)\n"
        f"{banner}\n"
    )
    print(msg, flush=True)

    # 토스트 알림
    _toast(
        f"[{site}] Windows PIN 입력 필요",
        "화면의 'Windows 보안' 팝업에 PIN을 입력하세요.",
    )

    # 알림음 — 백그라운드에서 반복 재생 (stop_evt로 중단 가능)
    stop_evt = threading.Event()
    t = threading.Thread(target=_beep_loop, args=(stop_evt, 6, 2.0), daemon=True)
    t.start()
    return stop_evt  # 호출자가 stop_evt.set()으로 중단 가능


def notify_popup_gone(site: str) -> None:
    """팝업이 닫혔음을 콘솔에 출력."""
    print(f"[{site}] Windows 인증 팝업 닫힘 감지 — 비밀번호 읽는 중...", flush=True)
