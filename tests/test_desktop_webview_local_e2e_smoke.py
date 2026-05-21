"""tests/test_desktop_webview_local_e2e_smoke.py

DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01 단위 테스트.
실제 서버 연결 없이 리포트 스키마 / 로직 / 보안만 검증.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_PATH = ROOT / "data" / "inspection" / "desktop_webview_local_e2e_smoke" / "local_e2e_report.json"
NETWORK_PATH = ROOT / "data" / "inspection" / "desktop_webview_local_e2e_smoke" / "network_summary.json"
SUMMARY_PATH = ROOT / "data" / "inspection" / "desktop_webview_local_e2e_smoke" / "local_e2e_summary.md"

_SECRET_PATTERNS = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


# ── 1. local_server URL schema ───────────────────────────────────────────────

def test_local_server_url_schema():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import BASE_URL
    assert BASE_URL.startswith("http://127.0.0.1"), "BASE_URL must be localhost"
    assert "8765" in BASE_URL


# ── 2. ui_dist asset check ────────────────────────────────────────────────────

def test_ui_assets_exist():
    dist = ROOT / "desktop" / "ui_dist"
    assert dist.exists(), "ui_dist 폴더 없음"
    assert (dist / "index.html").exists(), "index.html 없음"
    js_files = list((dist / "assets").glob("index-*.js"))
    css_files = list((dist / "assets").glob("index-*.css"))
    assert js_files, "JS asset 없음"
    assert css_files, "CSS asset 없음"


# ── 3. webview_app_pywebview.py 존재 ─────────────────────────────────────────

def test_webview_app_pywebview_exists():
    entry = ROOT / "desktop" / "webview_app_pywebview.py"
    assert entry.exists(), "webview_app_pywebview.py 없음"
    src = entry.read_text(encoding="utf-8")
    assert "pywebview" in src or "webview" in src
    assert "127.0.0.1:8765" in src or "_LOCAL_URL" in src


# ── 4. report schema test ─────────────────────────────────────────────────────

def test_report_schema():
    if not REPORT_PATH.exists():
        import pytest; pytest.skip("리포트 미생성 — smoke 미실행")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    required = ["run_at", "task_id", "server", "ui_assets", "websocket",
                "agent_status", "panels", "admin_proxy", "pywebview",
                "lifecycle", "final_verdict", "verdicts"]
    for key in required:
        assert key in report, f"리포트에 '{key}' 누락"
    assert report["task_id"] == "DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01"


# ── 5. ws status schema ───────────────────────────────────────────────────────

def test_ws_status_schema():
    if not REPORT_PATH.exists():
        import pytest; pytest.skip("리포트 미생성")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    ws = report["websocket"]
    assert "ok" in ws
    assert "ws_path" in ws
    assert "verdict" in ws
    assert ws["ws_path"] == "/ws/ui"


# ── 6. panel smoke schema ─────────────────────────────────────────────────────

def test_panel_smoke_schema():
    if not REPORT_PATH.exists():
        import pytest; pytest.skip("리포트 미생성")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    panels = report["panels"]
    assert isinstance(panels, dict)
    for name, r in panels.items():
        assert "http_code" in r, f"panels.{name} http_code 누락"
        assert "ok" in r


# ── 7. iframe proxy schema ────────────────────────────────────────────────────

def test_iframe_proxy_schema():
    if not REPORT_PATH.exists():
        import pytest; pytest.skip("리포트 미생성")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    admin = report["admin_proxy"]
    expected = ["admin_dashboard", "admin_ops", "admin_approvals", "admin_agents", "admin_cad"]
    for key in expected:
        assert key in admin, f"admin_proxy.{key} 누락"
        r = admin[key]
        assert "path" in r
        assert "http_code" in r
        assert "verdict" in r


# ── 8. secret leak detection ──────────────────────────────────────────────────

def test_no_secret_in_report():
    if not REPORT_PATH.exists():
        import pytest; pytest.skip("리포트 미생성")
    text = REPORT_PATH.read_text(encoding="utf-8")
    match = _SECRET_PATTERNS.search(text)
    assert not match, f"리포트에 secret 노출: {match.group()[:30]}…"


def test_no_secret_in_network_summary():
    if not NETWORK_PATH.exists():
        import pytest; pytest.skip("리포트 미생성")
    text = NETWORK_PATH.read_text(encoding="utf-8")
    match = _SECRET_PATTERNS.search(text)
    assert not match, f"network_summary에 secret 노출: {match.group()[:30]}…"


# ── 9. audit verdict logic ────────────────────────────────────────────────────

def test_verdict_fail_when_server_down():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import check_server
    with mock.patch("scripts.ops.audit_desktop_webview_local_e2e_smoke._port_listening", return_value=False):
        r = check_server()
    assert not r["ok"]
    assert r["verdict"] == "FAIL_LOCAL_SERVER_NOT_LISTENING"


def test_verdict_warn_pywebview_not_installed():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import check_pywebview
    with mock.patch.dict(sys.modules, {"webview": None}):
        r = check_pywebview()
    # ImportError 분기
    assert "WARN_PYWEBVIEW_NOT_INSTALLED" in r.get("verdict", "") or r.get("installed") is True


def test_verdict_fail_secret_leak():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import check_secret_leaks
    leaky = {"data": "device_token=abc123xyz_secret"}
    r = check_secret_leaks(leaky)
    assert not r["ok"]
    assert r["verdict"] == "FAIL_SECRET_LEAK"


def test_verdict_ok_no_leak():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import check_secret_leaks
    clean = {"agent_id": "la-<REDACTED>", "server_connected": True}
    r = check_secret_leaks(clean)
    assert r["ok"]
    assert r["verdict"] == "OK"


# ── 10. admin proxy path format ───────────────────────────────────────────────

def test_admin_proxy_paths():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import _ADMIN_PATHS
    for name, path in _ADMIN_PATHS.items():
        assert path.startswith("/proxy/admin"), f"{name} 경로 형식 오류: {path}"


# ── 11. mask function ─────────────────────────────────────────────────────────

def test_mask_function():
    from scripts.ops.audit_desktop_webview_local_e2e_smoke import _mask
    raw = 'device_token=abc123 api_key=xyz registration_code=FJ6X-MEZW'
    masked = _mask(raw)
    assert "abc123" not in masked
    assert "xyz" not in masked
    assert "FJ6X" not in masked
    assert "REDACTED" in masked


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
