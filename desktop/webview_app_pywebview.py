"""Haehan AI 데스크탑 앱 — pywebview 기반.

실행:
    python -m desktop.webview_app_pywebview

구조:
    - 로컬 FastAPI 서버(8765)가 이미 실행 중이면 재사용
    - 실행 중이 아니면 별도 스레드에서 기동 후 대기
    - pywebview 네이티브 창에서 http://127.0.0.1:8765 표시
    - 창 닫으면 본 프로세스 서버도 함께 종료 (외부 서버는 유지)

보안 정책:
    - device_token / registration_code / API key 원문 출력 금지
    - console.log 에서 secret 패턴 필터링
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCAL_URL = "http://127.0.0.1:8765"
_SERVER_PORT = 8765
_SERVER_READY_TIMEOUT = 10


def _is_server_up() -> bool:
    try:
        urllib.request.urlopen(_LOCAL_URL, timeout=1)
        return True
    except Exception:
        return False


def _wait_for_server(timeout: float = _SERVER_READY_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_server_up():
            return True
        time.sleep(0.3)
    return False


_server_thread: threading.Thread | None = None
_server_owned = False  # 본 프로세스가 서버를 띄웠는지


def _start_embedded_server() -> None:
    global _server_owned
    try:
        import uvicorn
        from desktop.local_server import app as _app
        _server_owned = True
        uvicorn.run(_app, host="127.0.0.1", port=_SERVER_PORT, log_level="warning")
    except Exception as exc:
        logger.error("embedded server error: %s", type(exc).__name__)


def ensure_server() -> bool:
    """서버가 없으면 임베디드로 기동. 준비되면 True 반환."""
    global _server_thread
    if _is_server_up():
        logger.info("외부 서버 감지 — 재사용")
        return True
    logger.info("서버 기동 중…")
    _server_thread = threading.Thread(target=_start_embedded_server, daemon=True)
    _server_thread.start()
    return _wait_for_server()


def run_pywebview(title: str = "Haehan AI", width: int = 1200, height: int = 800) -> None:
    import webview

    window = webview.create_window(
        title,
        _LOCAL_URL,
        width=width,
        height=height,
        min_size=(800, 560),
        resizable=True,
        text_select=True,
    )
    webview.start(debug=False)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not ensure_server():
        logger.error("로컬 서버 준비 실패 — 그래도 창을 엽니다.")

    try:
        run_pywebview()
    except ImportError:
        logger.error("pywebview 미설치: pip install pywebview")
        sys.exit(1)
    except Exception as exc:
        logger.error("pywebview 실행 오류: %s", type(exc).__name__)
        sys.exit(1)


if __name__ == "__main__":
    main()
