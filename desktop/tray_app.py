"""Windows system tray app (DESK-3).

Provides system tray icon with:
- Start / Stop / Restart local browser task handler
- Status display (local only)
- Open admin mock UI link (localhost only)
- Open local logs directory
- Exit

SECURITY:
- NEVER shows: approval_token, final_approval_token, token_hash,
  typed_text, password, OTP, cookie, session, Authorization,
  localStorage, sessionStorage, raw screenshot/base64
- NEVER connects to production WebSocket or API
- NEVER starts production task runners
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image, ImageDraw

from .local_runner import LocalRunner
from .status_provider import LocalStatusProvider, ServiceStatus

logger = logging.getLogger(__name__)

# Icon colors per state
_STATE_COLORS: dict[str, tuple[int, int, int]] = {
    "running":  (34, 197, 94),   # green
    "starting": (251, 191, 36),  # yellow
    "degraded": (249, 115, 22),  # orange
    "stopped":  (107, 114, 128), # gray
    "error":    (239, 68, 68),   # red
}

# Local-only URL — never contacts production
_ADMIN_MOCK_UI_URL = "http://localhost:3000/browser-approvals"

# Repo-relative log dir
_LOG_DIR = Path(__file__).parent.parent / "logs"


def _make_icon_image(state: str, size: int = 64) -> Image.Image:
    """Creates a simple solid-color circle icon for the given state."""
    color = _STATE_COLORS.get(state, (107, 114, 128))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color + (255,),
    )
    return img


class TrayApp:
    """Windows system tray application for local agent management."""

    def __init__(
        self,
        runner: Optional[LocalRunner] = None,
        status_provider: Optional[LocalStatusProvider] = None,
        admin_ui_url: str = _ADMIN_MOCK_UI_URL,
        log_dir: Optional[Path] = None,
    ) -> None:
        self._runner = runner or LocalRunner()
        self._status = status_provider or LocalStatusProvider(
            log_dir=log_dir or _LOG_DIR,
            admin_ui_url=admin_ui_url,
        )
        self._admin_ui_url = admin_ui_url
        self._log_dir = log_dir or _LOG_DIR
        self._icon: Optional[pystray.Icon] = None
        self._update_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Menu items

    def _menu_status_line(self) -> str:
        s = self._runner.get_status()
        label = {
            "running": "● 실행 중",
            "starting": "○ 시작 중",
            "degraded": "⚠ 저하됨",
            "stopped": "■ 중지됨",
            "error": "✗ 오류",
        }.get(s, f"? {s}")
        return f"상태: {label}"

    def _menu_pending_line(self) -> str:
        try:
            store_status = self._status.get_approval_store_status()
            return f"대기 작업: {store_status.pending_count}"
        except Exception:
            return "대기 작업: -"

    def _menu_task_queue_line(self) -> str:
        """작업 큐 분류 요약 — 실행 없음, 표시만."""
        try:
            return self._status.get_task_queue_tray_label(source="local")
        except Exception:
            return "수신 작업: -"

    def _menu_agent_notice_line(self) -> str:
        """LOCAL_AGENT_REQUIRED / USER_DIRECT_REQUIRED 수신 여부 표시."""
        try:
            queue = self._status.get_server_task_queue_status(source="local")
            if queue is None:
                return "에이전트 분류: -"
            parts = []
            if queue.local_agent_count:
                parts.append(f"에이전트 {queue.local_agent_count}건")
            if queue.user_direct_count:
                parts.append(f"직접조작 {queue.user_direct_count}건 ⚠")
            if queue.blocked_count:
                parts.append(f"차단 {queue.blocked_count}건 ✗")
            return "  " + (", ".join(parts) if parts else "대기 없음")
        except Exception:
            return "  에이전트 분류: -"

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(self._menu_status_line(), None, enabled=False),
            pystray.MenuItem(self._menu_pending_line(), None, enabled=False),
            pystray.MenuItem(self._menu_task_queue_line(), None, enabled=False),
            pystray.MenuItem(self._menu_agent_notice_line(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("시작 (Start)", self._on_start),
            pystray.MenuItem("중지 (Stop)", self._on_stop),
            pystray.MenuItem("재시작 (Restart)", self._on_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Admin Mock UI 열기", self._on_open_admin_ui),
            pystray.MenuItem("뉴스 조회", self._on_open_news),
            pystray.MenuItem("로그 폴더 열기", self._on_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료 (Exit)", self._on_exit),
        )

    # ------------------------------------------------------------------
    # Menu callbacks

    def _on_start(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        logger.info("tray: start requested")
        self._runner.start()
        self._update_icon()

    def _on_stop(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        logger.info("tray: stop requested")
        self._runner.stop()
        self._update_icon()

    def _on_restart(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        logger.info("tray: restart requested")
        self._runner.restart()
        self._update_icon()

    def _on_open_admin_ui(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        # Opens localhost only — never a production URL
        url = self._status.get_admin_mock_ui_url()
        logger.info("tray: opening admin mock UI: %s", url)
        webbrowser.open(url)

    def _on_open_news(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        url = "http://localhost:3000/assistant/news"
        logger.info("tray: opening news page: %s", url)
        webbrowser.open(url)

    def _on_open_logs(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        log_path = self._status.get_local_logs_path()
        logger.info("tray: opening logs: %s", log_path)
        if sys.platform == "win32":
            os.startfile(str(log_path))
        else:
            subprocess.Popen(["xdg-open", str(log_path)])

    def _on_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        logger.info("tray: exit requested")
        self._runner.stop()  # graceful stop before exit
        icon.stop()

    # ------------------------------------------------------------------
    # Icon update

    def _update_icon(self) -> None:
        with self._update_lock:
            if self._icon is None:
                return
            state = self._runner.get_status()
            self._icon.icon = _make_icon_image(state)
            self._icon.menu = self._build_menu()

    def _schedule_periodic_update(self, interval: float = 30.0) -> None:
        def _loop() -> None:
            import time
            while self._icon and self._icon.visible:
                time.sleep(interval)
                self._update_icon()
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Run

    def run(self) -> None:
        initial_state = self._runner.get_status()
        self._icon = pystray.Icon(
            name="haehan-agent",
            icon=_make_icon_image(initial_state),
            title="Haehan Agent",
            menu=self._build_menu(),
        )
        self._schedule_periodic_update()
        logger.info("tray app running")
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    # ------------------------------------------------------------------
    # Status snapshot for tests / external monitoring

    def get_status_snapshot(self) -> ServiceStatus:
        runner_state = self._runner.get_status()
        return self._status.get_service_status(runner_state=runner_state)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app = TrayApp()
    app.run()


if __name__ == "__main__":
    main()
