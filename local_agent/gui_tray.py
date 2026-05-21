"""시스템 트레이 (pystray) — 옵션. 미설치 시 GUI 창만 띄움.

기능:
  - 트레이 아이콘에 상태 색 반영
  - 메뉴: [열기], [진단], [재등록], [종료]
  - 백그라운드에서 WS 연결 유지 (gui_app 의 controller 공유)
"""
from __future__ import annotations

import logging
import threading

from . import gui_state as gs

logger = logging.getLogger("haehan_tray")


def _try_import_pystray():
    try:
        import pystray  # type: ignore
        from PIL import Image  # type: ignore
        return pystray, Image
    except Exception:
        return None, None


def _make_icon_image(color: str = "#080", size: int = 64):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill=color, outline="black")
    return img


def _state_to_color(state: str) -> str:
    if state == gs.STATE_HEARTBEAT_OK or state == gs.STATE_CONNECTED:
        return "#1a8"
    if state in (gs.STATE_AUTH_FAILED, gs.STATE_SERVER_UNREACHABLE):
        return "#c33"
    if state in (gs.STATE_RECONNECTING, gs.STATE_CONNECTING,
                  gs.STATE_AUTHENTICATING):
        return "#e90"
    return "#888"


def run_tray_with_app(server_url: str = "https://haehan-ai.kr/orchestrator"
                       ) -> int:
    """pystray 사용 가능하면 tray + gui_app 백그라운드, 아니면 gui_app 만."""
    from . import gui_app as ga
    pystray, Image = _try_import_pystray()
    ctrl = gs.GuiController(server_url=server_url)

    if pystray is None:
        # fallback — tray 없이 GUI 창만
        app = ga.HaehanAgentGuiApp(controller=ctrl)
        app.run()
        return 0

    # tray + GUI 둘 다 — GUI 는 별도 스레드 (tkinter mainloop)
    gui_state = {"app": None, "icon": None}

    def _gui_thread():
        app = ga.HaehanAgentGuiApp(controller=ctrl)
        gui_state["app"] = app
        # GUI 가 닫혀도 tray 는 살아 있게 — 단, GUI mainloop 종료 후 안전 종료
        try:
            app.run()
        finally:
            # tray 도 같이 종료
            if gui_state.get("icon"):
                try:
                    gui_state["icon"].stop()
                except Exception:
                    pass

    threading.Thread(target=_gui_thread, daemon=True).start()

    def on_open(icon, item):
        # GUI mainloop 재시작은 어려움 — 정보 로그만
        logger.info("tray: open requested")

    def on_diagnostics(icon, item):
        logger.info("tray: diagnostics -- %s", ctrl.model.state)

    def on_reset(icon, item):
        from . import token_store as ts
        m = ctrl.model
        if m.agent_id:
            try:
                ts.delete_device_token(server_url=m.server_url,
                                        agent_id=m.agent_id)
            except Exception:
                pass
        ctrl.fire("reset_token", user_event="token 삭제됨 (tray)")

    def on_quit(icon, item):
        icon.stop()

    image = _make_icon_image(color=_state_to_color(ctrl.model.state))
    menu = pystray.Menu(
        pystray.MenuItem("열기", on_open),
        pystray.MenuItem("진단", on_diagnostics),
        pystray.MenuItem("재등록", on_reset),
        pystray.MenuItem("종료", on_quit),
    )
    icon = pystray.Icon("HaehanAgent", image, "Haehan AI Local Agent", menu)
    gui_state["icon"] = icon

    # controller 상태 변경 시 icon 색 갱신
    def _on_model_change(snap):
        try:
            icon.icon = _make_icon_image(color=_state_to_color(snap.state))
        except Exception:
            pass

    ctrl.subscribe(_on_model_change)
    icon.run()
    return 0
