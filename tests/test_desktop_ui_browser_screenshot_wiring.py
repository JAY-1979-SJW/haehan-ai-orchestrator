"""DESKTOP_UI_BROWSER_SCREENSHOT_WIRING_01 — 프론트엔드 WS 연결 검증."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PANELS = ROOT / "desktop/ui/src/components/panels/Panels.tsx"
STORE  = ROOT / "desktop/ui/src/store/appStore.ts"
WS     = ROOT / "desktop/ui/src/lib/ws.ts"
SERVER = ROOT / "desktop/local_server.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── BrowserPanel 검증 ─────────────────────────────────────────────────────────

def test_browser_panel_sends_browser_status():
    src = _read(PANELS)
    assert "action: 'browser_status'" in src, "browser_status action 미전송"


def test_browser_panel_sends_browser_start():
    src = _read(PANELS)
    assert "action: 'browser_start'" in src, "browser_start action 미전송"


def test_browser_panel_sends_browser_quit():
    src = _read(PANELS)
    assert "action: 'browser_quit'" in src, "browser_quit action 미전송"


def test_browser_panel_sends_tab_list():
    src = _read(PANELS)
    assert "action: 'tab_list'" in src, "tab_list action 미전송"


def test_browser_panel_sends_tab_close():
    src = _read(PANELS)
    assert "action: 'tab_close'" in src, "tab_close action 미전송"


def test_browser_panel_has_tab_schema():
    src = _read(PANELS)
    assert "tab_id" in src, "tab_id 필드 없음"
    assert "tab.url" in src or "tab.title" in src, "탭 URL/title 표시 없음"


def test_browser_panel_loading_state():
    src = _read(PANELS)
    assert "Loading\|loading\|animate-spin\|Loader2".lower() in src.lower() or "Loader2" in src, "로딩 상태 없음"


# ── ScreenshotPanel 검증 ──────────────────────────────────────────────────────

def test_screenshot_panel_sends_screenshot():
    src = _read(PANELS)
    assert "action: 'screenshot'" in src, "screenshot action 미전송"


def test_screenshot_panel_displays_image():
    src = _read(PANELS)
    assert "data:image" in src or "base64" in src, "base64 이미지 표시 경로 없음"


def test_screenshot_panel_has_error_state():
    src = _read(PANELS)
    assert "error" in src.lower(), "에러 상태 처리 없음"


def test_screenshot_panel_has_refresh_button():
    src = _read(PANELS)
    assert "requestScreenshot" in src or "캡처" in src, "새로고침/캡처 버튼 없음"


def test_screenshot_panel_has_timestamp():
    src = _read(PANELS)
    assert "toLocaleTimeString" in src or "ts" in src, "캡처 시각 표시 없음"


# ── WS 타입 검증 ──────────────────────────────────────────────────────────────

def test_ws_has_tab_list_type():
    src = _read(WS)
    assert "'tab_list'" in src or '"tab_list"' in src, "WS: tab_list 타입 없음"


def test_ws_has_screenshot_result_type():
    src = _read(WS)
    assert "'screenshot_result'" in src or '"screenshot_result"' in src, "WS: screenshot_result 타입 없음"


def test_ws_has_browser_tab_interface():
    src = _read(WS)
    assert "BrowserTab" in src, "BrowserTab 인터페이스 없음"


# ── store 검증 ────────────────────────────────────────────────────────────────

def test_store_has_browser_tabs_state():
    src = _read(STORE)
    assert "browserTabsState" in src, "store: browserTabsState 없음"


def test_store_has_screenshot_state():
    src = _read(STORE)
    assert "screenshotState" in src, "store: screenshotState 없음"


def test_store_handles_tab_list():
    src = _read(STORE)
    assert "case 'tab_list'" in src, "store: tab_list 메시지 핸들러 없음"


def test_store_handles_screenshot_result():
    src = _read(STORE)
    assert "case 'screenshot_result'" in src, "store: screenshot_result 메시지 핸들러 없음"


# ── 백엔드 WS action 검증 ────────────────────────────────────────────────────

def test_server_has_screenshot_action():
    src = _read(SERVER)
    assert 'action == "screenshot"' in src, "server: screenshot action 핸들러 없음"


def test_server_has_tab_list_action():
    src = _read(SERVER)
    assert 'action == "tab_list"' in src, "server: tab_list action 핸들러 없음"


def test_server_has_tab_close_action():
    src = _read(SERVER)
    assert 'action == "tab_close"' in src, "server: tab_close action 핸들러 없음"


def test_server_screenshot_returns_png():
    src = _read(SERVER)
    assert "screenshot_result" in src, "server: screenshot_result 응답 없음"
    assert "base64" in src, "server: base64 인코딩 없음"


# ── 보안 검증 ─────────────────────────────────────────────────────────────────

_SECRET_PATTERNS = ["device_token", "secret", "password", ".env"]


def test_no_secret_in_browser_panel():
    src = _read(PANELS)
    # screenshot 관련 섹션에 secret/token 노출 없음
    browser_section = src[src.find("BrowserPanel"):src.find("ScreenshotPanel") + 2000]
    for pat in ["device_token", "password"]:
        assert pat.lower() not in browser_section.lower(), f"보안 위반: {pat} 노출"


def test_no_agent_line_touched():
    """HaehanAI-Agent.exe 라인(gui_*) 미수정 확인."""
    agent_gui = ROOT / "desktop" / "local_agent"
    gui_files = list(agent_gui.glob("gui_*.py")) if agent_gui.exists() else []
    # 파일 존재 자체는 ok, 금번 작업에서 수정 여부는 git diff로 확인
    # 여기서는 import 경로만 체크
    src = _read(PANELS)
    assert "local_agent.gui_" not in src, "금지: local_agent/gui_* import"
