"""DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE_01 — 정적 + 보고서 검증."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT       = Path(__file__).parent.parent
PANELS     = ROOT / "desktop/ui/src/components/panels/Panels.tsx"
STORE      = ROOT / "desktop/ui/src/store/appStore.ts"
WS_TS      = ROOT / "desktop/ui/src/lib/ws.ts"
SERVER     = ROOT / "desktop/local_server.py"
REPORT_DIR = ROOT / "data/inspection/desktop_webview_browser_cdp_package_smoke"
SPEC       = ROOT / "HaehanAI-Desktop.spec"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── report schema ──────────────────────────────────────────────────────

def test_report_exists():
    assert (REPORT_DIR / "browser_cdp_report.json").exists(), "browser_cdp_report.json 없음"


def test_report_schema():
    data = json.loads((REPORT_DIR / "browser_cdp_report.json").read_text(encoding="utf-8"))
    assert "verdicts" in data
    assert "dependencies" in data
    assert "cdp_daemon" in data
    assert "connect_over_cdp" in data
    assert "security" in data


def test_report_pass_verdict():
    data = json.loads((REPORT_DIR / "browser_cdp_report.json").read_text(encoding="utf-8"))
    verdicts = data.get("verdicts", [])
    assert any("PASS" in v for v in verdicts), f"PASS verdict 없음: {verdicts}"


def test_report_no_fail_verdict():
    data = json.loads((REPORT_DIR / "browser_cdp_report.json").read_text(encoding="utf-8"))
    fails = [v for v in data.get("verdicts", []) if v.startswith("FAIL")]
    assert not fails, f"FAIL verdict 존재: {fails}"


def test_screenshot_report_exists():
    assert (REPORT_DIR / "screenshot_smoke.json").exists(), "screenshot_smoke.json 없음"


def test_screenshot_report_schema():
    data = json.loads((REPORT_DIR / "screenshot_smoke.json").read_text(encoding="utf-8"))
    assert "ok" in data
    assert "size_bytes" in data
    assert "target" in data


def test_screenshot_target_safe():
    data = json.loads((REPORT_DIR / "screenshot_smoke.json").read_text(encoding="utf-8"))
    target = data.get("target", "")
    # URL 부분만 검사 — 괄호 안 설명 제외
    url_part = target.split("(")[0].strip()
    for forbidden in ["naver.com", "google.com/accounts", "login.microsoftonline"]:
        assert forbidden not in url_part.lower(), f"screenshot target이 민감 URL: {url_part}"


# ── CDP status schema ──────────────────────────────────────────────────

def test_cdp_daemon_schema():
    data = json.loads((REPORT_DIR / "browser_cdp_report.json").read_text(encoding="utf-8"))
    cdp = data["cdp_daemon"]
    assert "port_9222_listening" in cdp
    assert "tab_count" in cdp


def test_connect_over_cdp_schema():
    data = json.loads((REPORT_DIR / "browser_cdp_report.json").read_text(encoding="utf-8"))
    conn = data["connect_over_cdp"]
    assert "ok" in conn


# ── BrowserPanel action schema ──────────────────────────────────────────

def test_browser_panel_browser_status():
    assert "action: 'browser_status'" in _read(PANELS)


def test_browser_panel_browser_start():
    assert "action: 'browser_start'" in _read(PANELS)


def test_browser_panel_browser_quit():
    assert "action: 'browser_quit'" in _read(PANELS)


def test_browser_panel_tab_list():
    assert "action: 'tab_list'" in _read(PANELS)


def test_browser_panel_tab_close():
    assert "action: 'tab_close'" in _read(PANELS)


def test_browser_panel_login_watcher():
    src = _read(PANELS)
    assert "login_watcher_start" in src, "login_watcher_start 없음"
    assert "login_watcher_stop" in src, "login_watcher_stop 없음"


# ── ScreenshotPanel schema ─────────────────────────────────────────────

def test_screenshot_panel_action():
    assert "action: 'screenshot'" in _read(PANELS)


def test_screenshot_panel_image_display():
    assert "data:image" in _read(PANELS)


def test_screenshot_panel_error_state():
    assert "error" in _read(PANELS).lower()


# ── WS / store schema ─────────────────────────────────────────────────

def test_ws_screenshot_result_type():
    assert "'screenshot_result'" in _read(WS_TS)


def test_ws_tab_list_type():
    assert "'tab_list'" in _read(WS_TS)


def test_store_screenshot_state():
    assert "screenshotState" in _read(STORE)


def test_store_browser_tabs_state():
    assert "browserTabsState" in _read(STORE)


def test_store_login_watcher_state():
    assert "loginWatcherState" in _read(STORE)


# ── server action schema ───────────────────────────────────────────────

def test_server_screenshot_handler():
    assert 'action == "screenshot"' in _read(SERVER)


def test_server_tab_list_handler():
    assert 'action == "tab_list"' in _read(SERVER)


def test_server_browser_start_handler():
    assert 'action == "browser_start"' in _read(SERVER)


# ── secret leak detection ──────────────────────────────────────────────

FORBIDDEN_PATTERNS = ["device_token", "registration_code", "sk-", "openai_api_key"]


def test_report_no_secret_leak():
    if not REPORT_DIR.exists():
        return
    for f in REPORT_DIR.glob("*.json"):
        content = f.read_text(encoding="utf-8", errors="replace").lower()
        for pat in FORBIDDEN_PATTERNS:
            assert pat not in content, f"{f.name}에 '{pat}' 노출"


def test_no_cookie_in_report():
    if not REPORT_DIR.exists():
        return
    for f in REPORT_DIR.glob("*.json"):
        content = f.read_text(encoding="utf-8", errors="replace").lower()
        # set-cookie 값 원문 금지 (키워드 'set-cookie:' 패턴)
        assert "set-cookie:" not in content, f"{f.name}에 Set-Cookie 헤더 값 노출"


# ── spec / playwright exclusion 확인 ──────────────────────────────────

def test_playwright_excluded_from_spec():
    if not SPEC.exists():
        return
    spec = _read(SPEC)
    assert "excludes" in spec and "playwright" in spec, "spec에서 playwright 제외 확인 불가"


# ── 회귀: 기존 wiring 테스트가 통과 상태인지 ──────────────────────────

def test_regression_browser_wiring_actions_present():
    """이전 WIRING 공정 결과가 유지되는지 확인."""
    src = _read(PANELS)
    for action in ["browser_status", "browser_start", "browser_quit", "tab_list", "tab_close", "screenshot"]:
        assert f"action: '{action}'" in src, f"회귀: {action} 없음"


def test_regression_login_watcher_events_handled():
    src = _read(STORE)
    for evt in ["target_created", "login_state_changed", "auth_popup_detected"]:
        assert evt in src, f"회귀: store에 {evt} 핸들러 없음"
