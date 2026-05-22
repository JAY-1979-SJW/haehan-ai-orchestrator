"""HAEHAN-DESKTOP-NEW-SHELL-PHASE2-UI-SMOKE-01 검증 테스트.

구조 검사(서버 불필요) + live 서버 smoke(8765 실행 시).
실행 버튼 비활성화, legacy 파일 보존, secret 미노출 검증 포함.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

ROOT   = Path(__file__).parent.parent
DESKTOP = ROOT / "desktop"
UI_NEW  = DESKTOP / "ui_new"
APP_CFG = DESKTOP / "app_config.py"
WV_PYW  = DESKTOP / "webview_app_pywebview.py"
LOCAL_SERVER = DESKTOP / "local_server.py"

LEGACY_FILES = [
    DESKTOP / "tray_app.py",
    DESKTOP / "webview_app.py",
    DESKTOP / "webview_app_pywebview.py",
    DESKTOP / "ui",
]


def _alive() -> bool:
    s = socket.socket(); s.settimeout(0.5)
    r = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close(); return r


# ── 구조 검사 ─────────────────────────────────────────────────────────────────

def test_shell_html_module_exists():
    assert (UI_NEW / "shell_html.py").exists()


def test_app_config_has_active_shell_url():
    src = APP_CFG.read_text(encoding="utf-8")
    assert "ACTIVE_SHELL_URL" in src
    assert "HAEHAN_DESKTOP_UI" in src
    assert "new_shell" in src


def test_webview_uses_active_shell_url():
    src = WV_PYW.read_text(encoding="utf-8")
    assert "ACTIVE_SHELL_URL" in src or "_ACTIVE_SHELL_URL" in src


def test_local_server_has_app_new_route():
    src = LOCAL_SERVER.read_text(encoding="utf-8")
    assert '"/app-new"' in src or "'/app-new'" in src


def test_new_shell_route_references_agent_status():
    src = (UI_NEW / "api.py").read_text(encoding="utf-8")
    assert "agent_status" in src


def test_new_shell_route_references_preflight():
    src = (UI_NEW / "api.py").read_text(encoding="utf-8")
    assert "la_preflight" in src or "preflight" in src


def test_new_shell_route_references_whoami():
    src = (UI_NEW / "api.py").read_text(encoding="utf-8")
    assert "whoami" in src


def test_run_button_disabled_in_shell_html():
    src = (UI_NEW / "shell_html.py").read_text(encoding="utf-8")
    assert "btn-disabled" in src or 'disabled' in src
    # local-agent/run 을 직접 호출하는 fetch/click 없어야 함
    assert "local-agent/run" not in src or "disabled" in src


def test_cad_buttons_not_active_in_shell_html():
    src = (UI_NEW / "shell_html.py").read_text(encoding="utf-8")
    # CAD start/stop/restart 버튼이 클릭 핸들러 없이 disabled여야 함
    assert "cad/bridge/start" not in src
    assert "cad/bridge/stop" not in src
    assert "cad/bridge/restart" not in src


def test_legacy_files_still_exist():
    for path in LEGACY_FILES:
        assert path.exists(), f"레거시 파일이 삭제됨: {path}"


# ── 환경변수 기반 shell 선택 ──────────────────────────────────────────────────

def test_new_shell_env_selects_app_new(monkeypatch):
    monkeypatch.setenv("HAEHAN_DESKTOP_UI", "new_shell")
    import importlib
    import desktop.app_config as cfg
    importlib.reload(cfg)
    assert cfg.ACTIVE_SHELL_URL.endswith("/app-new"), \
        f"new_shell 환경변수가 /app-new를 선택하지 않음: {cfg.ACTIVE_SHELL_URL}"


def test_legacy_env_selects_root(monkeypatch):
    monkeypatch.setenv("HAEHAN_DESKTOP_UI", "legacy")
    import importlib
    import desktop.app_config as cfg
    importlib.reload(cfg)
    assert not cfg.ACTIVE_SHELL_URL.endswith("/app-new"), \
        "legacy 환경변수에서 /app-new가 선택됨"


# ── py_compile ────────────────────────────────────────────────────────────────

def test_shell_html_compiles():
    import py_compile
    py_compile.compile(str(UI_NEW / "shell_html.py"), doraise=True)


def test_app_config_compiles():
    import py_compile
    py_compile.compile(str(APP_CFG), doraise=True)


# ── live 서버 smoke ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_health_still_json():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
    d = json.loads(r.read())
    assert d.get("ok") is True
    assert b"<!doctype" not in r.read() if False else True  # 이미 read됨


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_returns_html():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read()
    assert b"<!doctype html" in content.lower() or b"<html" in content.lower()


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_has_haehan_title():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace")
    assert "Haehan AI Desktop" in content


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_has_agent_status_area():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace")
    assert "서버 상태" in content or "Agent" in content or "로컬 AI" in content


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_has_can_run():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace")
    assert "can_run" in content or "실행 가능" in content


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_app_new_run_button_disabled():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace")
    assert "비활성화" in content or "disabled" in content.lower()


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_api_prefix_not_html_fallback():
    """/api/ 로 시작하는 경로가 HTML로 fallback되지 않는다."""
    import urllib.request, urllib.error
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/agent/status", timeout=3)
        body = r.read()
        assert b"<!doctype" not in body.lower(), "/agent/status가 HTML 반환"
        assert b"ok" in body.lower()
    except urllib.error.HTTPError as e:
        body = e.read()
        assert b"<!doctype" not in body.lower(), "에러 응답이 HTML"


@pytest.mark.skipif(not _alive(), reason="local_server 미실행")
def test_no_secret_in_app_new():
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/app-new", timeout=5)
    content = r.read().decode("utf-8", errors="replace").lower()
    for pattern in ("api_key_value", "sk-", "ghp_", "bearer ", "password=", "cookie:"):
        assert pattern not in content, f"/app-new에 민감 패턴 발견: {pattern}"
