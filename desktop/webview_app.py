"""Haehan AI 데스크탑 앱 — PyQt6 WebEngine 기반.

실행:
    python -m desktop.webview_app

구조:
    - 로컬 FastAPI 서버(8765)를 별도 스레드에서 기동
    - PyQt6 QWebEngineView로 http://127.0.0.1:8765 표시
    - 창 닫으면 서버도 종료
"""
from __future__ import annotations

import sys
import threading
import time
import logging
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtGui import QIcon

logger = logging.getLogger(__name__)

from desktop.app_config import LOCAL_URL as _LOCAL_URL  # noqa: E402
_SERVER_READY_TIMEOUT = 8  # 초


def _start_local_server() -> None:
    """로컬 FastAPI 서버를 별도 스레드에서 기동."""
    from desktop.local_server import run
    run()


def _wait_for_server(timeout: float = _SERVER_READY_TIMEOUT) -> bool:
    """서버 준비 대기."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(_LOCAL_URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


class DesktopWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Haehan AI")
        self.resize(1000, 720)
        self.setMinimumSize(720, 520)

        # 아이콘
        icon_path = Path(__file__).parent.parent / "admin-web" / "public" / "icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # WebEngineView
        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        # 설정
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # 서버 준비 후 로드
        QTimer.singleShot(500, self._load_app)

    def _load_app(self) -> None:
        self._view.setUrl(QUrl(_LOCAL_URL))

    def closeEvent(self, event) -> None:
        event.accept()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 로컬 서버 백그라운드 기동
    t = threading.Thread(target=_start_local_server, daemon=True)
    t.start()

    # 서버 준비 대기
    logger.info("로컬 서버 준비 대기 중…")
    if not _wait_for_server():
        logger.warning("서버 준비 타임아웃 — 그래도 창을 열겠습니다.")

    # Qt 앱 실행
    app = QApplication(sys.argv)
    app.setApplicationName("Haehan AI")
    app.setOrganizationName("Haehan")

    window = DesktopWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
