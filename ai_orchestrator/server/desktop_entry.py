"""데스크톱 앱 번들(PyInstaller haehan-server) 진입점.

PyInstaller 는 진입 파일을 패키지 밖의 단독 스크립트(__main__)로 실행한다. ai_orchestrator/asgi.py 를
그대로 진입점으로 쓰면 그 안의 상대 import(`from . import config`)가 "no known parent package" 로
실패해 서버가 시작되지 않는다(2026-10-08 첫 빌드 E2E 실측: fastapi.log ImportError). 이 파일은
상대 import 없이 패키지 경로로 asgi 를 불러 uvicorn 을 띄운다.

부모 감시: 앱(Electron)이 강제 종료·크래시해도 이 서버가 고아로 남아 포트 8401 과 userData 파일 핸들을
쥐지 않도록, 앱이 환경변수 HAEHAN_PARENT_PID 로 넘긴 부모 PID 가 사라지면 스스로 종료한다.
"""

import os
import sys
import threading
import time

import uvicorn

from ai_orchestrator import asgi


def _parent_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False  # 열 수 없다 = 이미 사라졌다
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def parent_pid_from_env() -> int | None:
    raw = os.environ.get("HAEHAN_PARENT_PID", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def start_parent_watchdog(poll_seconds: float = 2.0, on_gone=lambda: os._exit(0)) -> threading.Thread | None:
    """HAEHAN_PARENT_PID 가 있으면 부모가 사라질 때 on_gone() 을 부르는 감시 스레드를 시작한다(없으면 None)."""
    pid = parent_pid_from_env()
    if pid is None:
        return None

    def _watch() -> None:
        while _parent_alive(pid):
            time.sleep(poll_seconds)
        on_gone()

    t = threading.Thread(target=_watch, name="parent-watchdog", daemon=True)
    t.start()
    return t


def main() -> None:
    start_parent_watchdog()
    uvicorn.run(asgi.app, host=asgi.APP_HOST, port=asgi.APP_PORT, reload=False)


if __name__ == "__main__":
    main()
