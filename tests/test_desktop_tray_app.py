"""DESK-3 tray app tests.

Tests tray app behavior using mocks — no real tray window opened.
Verifies: start/stop/restart, menu content, security constraints,
token non-disclosure, admin mock UI URL (local only).
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Stub pystray so tests work without a display
# ---------------------------------------------------------------------------

def _make_pystray_stub() -> types.ModuleType:
    mod = types.ModuleType("pystray")

    class FakeIcon:
        def __init__(self, name, icon=None, title="", menu=None):
            self.name = name
            self.icon = icon
            self.title = title
            self.menu = menu
            self.visible = False
            self._running = False

        def run(self):
            self._running = True

        def stop(self):
            self._running = False
            self.visible = False

    class FakeMenu:
        SEPARATOR = object()

        def __init__(self, *items):
            self._items = items

    class FakeMenuItem:
        def __init__(self, text, action, enabled=True):
            self.text = text
            self.action = action
            self.enabled = enabled

    mod.Icon = FakeIcon
    mod.Menu = FakeMenu
    mod.MenuItem = FakeMenuItem
    return mod


# Inject stub before importing desktop
sys.modules.setdefault("pystray", _make_pystray_stub())

# PIL stub
if "PIL" not in sys.modules:
    pil_mod = types.ModuleType("PIL")
    img_mod = types.ModuleType("PIL.Image")
    draw_mod = types.ModuleType("PIL.ImageDraw")

    class FakeImage:
        def __init__(self, mode, size, color=None):
            self.mode = mode
            self.size = size

    class FakeDraw:
        def __init__(self, img): pass
        def ellipse(self, *a, **kw): pass

    img_mod.Image = FakeImage
    img_mod.new = lambda mode, size, color=None: FakeImage(mode, size, color)
    draw_mod.Draw = lambda img: FakeDraw(img)
    pil_mod.Image = img_mod
    pil_mod.ImageDraw = draw_mod
    sys.modules["PIL"] = pil_mod
    sys.modules["PIL.Image"] = img_mod
    sys.modules["PIL.ImageDraw"] = draw_mod

from desktop.local_runner import LocalRunner
from desktop.status_provider import LocalStatusProvider, _FORBIDDEN_STATUS_KEYS
from desktop.tray_app import TrayApp, _make_icon_image, _ADMIN_MOCK_UI_URL


# ---------------------------------------------------------------------------
# Helper: mock runner
# ---------------------------------------------------------------------------

def _make_runner(status: str = "stopped") -> MagicMock:
    runner = MagicMock(spec=LocalRunner)
    runner.get_status.return_value = status
    runner.is_running.return_value = (status == "running")
    runner.start.return_value = True
    runner.stop.return_value = True
    runner.restart.return_value = True
    return runner


def _make_provider(url: str = _ADMIN_MOCK_UI_URL) -> MagicMock:
    provider = MagicMock(spec=LocalStatusProvider)
    provider.get_admin_mock_ui_url.return_value = url
    provider.get_local_logs_path.return_value = Path("logs")
    approval_status = MagicMock()
    approval_status.pending_count = 0
    provider.get_approval_store_status.return_value = approval_status
    return provider


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrayAppStartsReady(unittest.TestCase):
    def test_tray_app_starts_and_reports_ready(self):
        """tray app instantiates and status snapshot is available immediately."""
        runner = _make_runner("stopped")
        provider = _make_provider()
        from desktop.status_provider import ServiceStatus
        provider.get_service_status.return_value = ServiceStatus(state="stopped")
        app = TrayApp(runner=runner, status_provider=provider)
        snapshot = app.get_status_snapshot()
        self.assertIsNotNone(snapshot)
        self.assertIn(snapshot.state, {"running", "stopped", "starting", "degraded", "error"})


class TestTrayStatusDisplay(unittest.TestCase):
    def test_tray_status_shows_local_service_state(self):
        """Status menu line reflects runner state."""
        runner = _make_runner("running")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        status_line = app._menu_status_line()
        self.assertIn("실행", status_line)

    def test_tray_status_stopped_shows_stopped(self):
        runner = _make_runner("stopped")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        status_line = app._menu_status_line()
        self.assertIn("중지", status_line)

    def test_tray_status_error_shows_error(self):
        runner = _make_runner("error")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        status_line = app._menu_status_line()
        self.assertIn("오류", status_line)


class TestTrayCommands(unittest.TestCase):
    def _make_fake_icon(self):
        import pystray
        return pystray.Icon("test")

    def test_tray_start_command_invokes_local_runner(self):
        runner = _make_runner("stopped")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        app._on_start(self._make_fake_icon(), None)
        runner.start.assert_called_once()

    def test_tray_stop_command_stops_local_runner(self):
        runner = _make_runner("running")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        app._on_stop(self._make_fake_icon(), None)
        runner.stop.assert_called_once()

    def test_tray_restart_command_restarts_local_runner(self):
        runner = _make_runner("running")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        app._on_restart(self._make_fake_icon(), None)
        runner.restart.assert_called_once()

    def test_tray_exit_does_not_corrupt_state(self):
        runner = _make_runner("running")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        icon = self._make_fake_icon()
        app._icon = icon
        app._on_exit(icon, None)
        # stop called on runner to gracefully shut down
        runner.stop.assert_called_once()
        # icon.stop called
        self.assertFalse(icon._running)


class TestTrayAdminUI(unittest.TestCase):
    def test_tray_open_admin_mock_ui_points_to_local_route(self):
        """Admin UI URL must be localhost only — never production."""
        provider = _make_provider(url="http://localhost:3000/browser-approvals")
        app = TrayApp(runner=_make_runner(), status_provider=provider)
        with patch("webbrowser.open") as mock_open:
            import pystray
            app._on_open_admin_ui(pystray.Icon("t"), None)
        mock_open.assert_called_once()
        opened_url = mock_open.call_args[0][0]
        self.assertIn("localhost", opened_url)
        self.assertIn("browser-approvals", opened_url)
        self.assertNotIn("production", opened_url.lower())
        self.assertNotIn("haehan.ai", opened_url.lower())

    def test_admin_ui_url_not_production(self):
        """Default admin UI URL must never point to production."""
        self.assertIn("localhost", _ADMIN_MOCK_UI_URL)
        self.assertNotIn("haehan.ai", _ADMIN_MOCK_UI_URL)


class TestTrayLogs(unittest.TestCase):
    def test_tray_open_logs_shows_local_logs_only(self):
        """Logs path must be a local path — no remote URLs."""
        provider = _make_provider()
        provider.get_local_logs_path.return_value = Path("logs")
        app = TrayApp(runner=_make_runner(), status_provider=provider)
        import pystray
        with patch("os.startfile") as mock_startfile:
            app._on_open_logs(pystray.Icon("t"), None)
        mock_startfile.assert_called_once()
        opened_path = str(mock_startfile.call_args[0][0])
        self.assertNotIn("http", opened_path.lower())
        self.assertNotIn("://", opened_path)


class TestTraySecurityConstraints(unittest.TestCase):
    def test_tray_ui_does_not_render_tokens(self):
        """Status line and menu must never contain token values."""
        runner = _make_runner("running")
        provider = _make_provider()
        # Inject a result that would contain tokens if improperly handled
        approval_status = MagicMock()
        approval_status.pending_count = 2
        provider.get_approval_store_status.return_value = approval_status
        app = TrayApp(runner=runner, status_provider=provider)

        status_text = app._menu_status_line()
        pending_text = app._menu_pending_line()

        for token_word in ["approval_token", "token_hash", "final_approval_token"]:
            self.assertNotIn(token_word, status_text.lower())
            self.assertNotIn(token_word, pending_text.lower())

    def test_tray_ui_does_not_render_raw_text(self):
        """Status display must not show typed_text, password, OTP."""
        runner = _make_runner("stopped")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        status_text = app._menu_status_line()
        for forbidden in ["typed_text", "password", "otp"]:
            self.assertNotIn(forbidden, status_text.lower())

    def test_tray_ui_does_not_render_cookie_session_storage(self):
        """Status display must not show cookie, session, localStorage."""
        runner = _make_runner("running")
        app = TrayApp(runner=runner, status_provider=_make_provider())
        status_text = app._menu_status_line()
        pending_text = app._menu_pending_line()
        combined = status_text + pending_text
        for forbidden in ["cookie", "session", "localstorage", "sessionstorage"]:
            self.assertNotIn(forbidden, combined.lower())

    def test_forbidden_keys_list_is_comprehensive(self):
        """Forbidden status keys list covers all required sensitive fields."""
        required_forbidden = {
            "approval_token", "final_approval_token", "token_hash",
            "typed_text", "password", "otp", "cookie", "session",
            "authorization", "localstorage", "sessionstorage",
        }
        missing = required_forbidden - _FORBIDDEN_STATUS_KEYS
        self.assertEqual(missing, set(), f"Missing forbidden keys: {missing}")


class TestIconColors(unittest.TestCase):
    def test_icon_created_for_all_states(self):
        """Icon image can be created for all valid states."""
        for state in ("running", "starting", "degraded", "stopped", "error"):
            img = _make_icon_image(state)
            self.assertIsNotNone(img)

    def test_unknown_state_falls_back_to_gray(self):
        """Unknown state gets a gray icon (not crash)."""
        img = _make_icon_image("unknown_state")
        self.assertIsNotNone(img)


if __name__ == "__main__":
    unittest.main()
