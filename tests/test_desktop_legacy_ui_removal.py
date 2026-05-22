"""HAEHAN-DESKTOP-LEGACY-UI-REMOVAL-01 검증 테스트.

legacy UI 제거 + new_shell 기본화 + API 보존을 검증한다.
서버 불필요 항목은 구조 검사만, live 항목은 8765 실행 시에만 동작.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

ROOT    = Path(__file__).parent.parent
DESKTOP = ROOT / "desktop"


def _alive() -> bool:
    s = socket.socket(); s.settimeout(0.5)
    r = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close(); return r


# ── 1. 기본 UI route 가 /app-new 다 ──────────────────────────────────────────

def test_default_ui_route_is_app_new():
    import importlib
    import desktop.app_config as cfg
    importlib.reload(cfg)
    assert cfg.ACTIVE_SHELL_URL.endswith("/app-new"), \
        f"기본 ACTIVE_SHELL_URL이 /app-new가 아님: {cfg.ACTIVE_SHELL_URL}"


# ── 2. HAEHAN_DESKTOP_UI 미설정 시 new_shell 이 기본이다 ─────────────────────

def test_default_env_is_new_shell(monkeypatch):
    monkeypatch.delenv("HAEHAN_DESKTOP_UI", raising=False)
    import importlib
    import desktop.app_config as cfg
    importlib.reload(cfg)
    assert cfg.ACTIVE_SHELL_URL.endswith("/app-new"), \
        f"env 미설정 시 new_shell이 기본이 아님: {cfg.ACTIVE_SHELL_URL}"


# ── 3. legacy UI 파일이 존재하지 않는다 ─────────────────────────────────────

def test_tray_app_removed():
    assert not (DESKTOP / "tray_app.py").exists(), "tray_app.py 가 아직 존재함"


def test_webview_app_removed():
    assert not (DESKTOP / "webview_app.py").exists(), "webview_app.py 가 아직 존재함"


def test_webview_app_pywebview_removed():
    assert not (DESKTOP / "webview_app_pywebview.py").exists(), \
        "webview_app_pywebview.py 가 아직 존재함"


# ── 4. desktop/ui 디렉터리가 존재하지 않는다 ──────────────────────────────────

def test_legacy_ui_dir_removed():
    assert not (DESKTOP / "ui").exists(), "desktop/ui/ 디렉터리가 아직 존재함"


# ── 5. legacy import 가 남아 있지 않다 (운영 코드 기준) ───────────────────────

def test_no_legacy_import_in_main_launcher():
    src = (DESKTOP / "main_launcher.py").read_text(encoding="utf-8")
    assert "from desktop.webview_app_pywebview import _check_consent" not in src
    assert "from desktop.tray_app import" not in src


def test_no_legacy_import_in_app_config():
    src = (DESKTOP / "app_config.py").read_text(encoding="utf-8")
    assert "webview_app" not in src
    assert "tray_app" not in src


# ── 6~10. API 보존 (source 검사) ─────────────────────────────────────────────

REQUIRED_ENDPOINTS = [
    "/health",
    "/agent/status",
    "/agent/register",
    "/local-agent/health",
    "/local-agent/preflight",
    "/local-agent/run",
    "/cad/bridge/status",
    "/cad/bridge/start",
    "/cad/bridge/stop",
    "/cad/bridge/restart",
    "/cad/bridge/proxy",
    "/api/v1/whoami",
    "/logs",
    "/ws/ui",
]

def test_required_endpoints_in_local_server():
    src = (DESKTOP / "local_server.py").read_text(encoding="utf-8")
    missing = [ep for ep in REQUIRED_ENDPOINTS if ep not in src]
    assert missing == [], f"local_server.py 에서 endpoint 누락: {missing}"


def test_app_new_route_in_local_server():
    src = (DESKTOP / "local_server.py").read_text(encoding="utf-8")
    assert '"/app-new"' in src or "'/app-new'" in src


# ── 11. API prefix 는 HTML fallback 되지 않는다 ───────────────────────────────

def test_api_prefixes_protected_in_local_server():
    src = (DESKTOP / "local_server.py").read_text(encoding="utf-8")
    assert "_API_PREFIXES" in src or "API_PREFIX" in src or "NOT_FOUND" in src


# ── 12. local-agent/run 버튼은 자동 실행되지 않는다 ──────────────────────────

def test_shell_html_no_auto_run_local_agent():
    src = (DESKTOP / "ui_new" / "shell_html.py").read_text(encoding="utf-8")
    assert "local-agent/run" not in src or "disabled" in src


# ── 13. CAD start/stop 버튼은 자동 실행되지 않는다 ───────────────────────────

def test_shell_html_no_auto_cad_control():
    src = (DESKTOP / "ui_new" / "shell_html.py").read_text(encoding="utf-8")
    assert "cad/bridge/start" not in src
    assert "cad/bridge/stop" not in src
    assert "cad/bridge/restart" not in src


# ── 14. secret/token/cookie/API key 가 HTML/JSON 에 노출되지 않는다 ───────────

SECRET_PATTERNS = ("api_key_value", "sk-", "ghp_", "bearer ", "password=", "cookie:")

def test_shell_html_no_secrets():
    src = (DESKTOP / "ui_new" / "shell_html.py").read_text(encoding="utf-8").lower()
    for p in SECRET_PATTERNS:
        assert p not in src, f"shell_html.py 에 민감 패턴 발견: {p}"


# ── 15. 보존 엔드포인트 13개가 source 에 남아 있다 ───────────────────────────

def test_all_14_endpoints_preserved():
    """REQUIRED_ENDPOINTS 14개 전체 보존 확인 (source 검사)."""
    src = (DESKTOP / "local_server.py").read_text(encoding="utf-8")
    missing = [ep for ep in REQUIRED_ENDPOINTS if ep not in src]
    assert missing == [], f"endpoint 누락: {missing}"


# ── 보너스: consent 모듈 ────────────────────────────────────────────────────

def test_consent_module_exists():
    assert (DESKTOP / "consent.py").exists()


def test_consent_module_has_check_consent():
    src = (DESKTOP / "consent.py").read_text(encoding="utf-8")
    assert "def check_consent(" in src


# ── live 서버 smoke ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_health_returns_json():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
    d = json.loads(r.read())
    assert d.get("ok") is True


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_returns_html():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace")
    assert "<!doctype html" in content.lower() or "<html" in content.lower()
    assert "Haehan AI Desktop" in content


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_agent_status_returns_json():
    import urllib.request, urllib.error
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/agent/status", timeout=3)
        body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()
    assert b"<!doctype" not in body.lower(), "/agent/status 가 HTML 반환"


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_preflight_returns_json():
    import urllib.request, urllib.error
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/local-agent/preflight", timeout=3)
        body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()
    assert b"<!doctype" not in body.lower(), "/local-agent/preflight 가 HTML 반환"


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_whoami_returns_json():
    import urllib.request, urllib.error
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/api/v1/whoami", timeout=3)
        body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()
    assert b"<!doctype" not in body.lower(), "/api/v1/whoami 가 HTML 반환"


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_no_secret_in_app_new():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace").lower()
    for p in SECRET_PATTERNS:
        assert p not in content, f"/app-new 에 민감 패턴 발견: {p}"
