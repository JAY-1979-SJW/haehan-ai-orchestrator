"""HAEHAN-DESKTOP-NEW-SHELL-PHASE1-API-SEPARATION-01 검증 테스트.

실행 중인 local_server가 없어도 구조/파일 존재 여부/라우팅 정책 검사는 통과해야 한다.
실제 서버 호출 테스트는 live_server 픽스처가 있을 때만 동작한다.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DESKTOP = ROOT / "desktop"
LOCAL_SERVER = DESKTOP / "local_server.py"
UI_NEW = DESKTOP / "ui_new"
LEGACY_DOC = DESKTOP / "LEGACY_UI_DEPRECATED.md"
LEGACY_UI = DESKTOP / "ui"

PRESERVED_ENDPOINTS = [
    "/agent/status",
    "/agent/register",
    "/local-agent/health",
    "/local-agent/preflight",
    "/local-agent/run",
    "/api/v1/whoami",
    "/logs",
    "/ws/ui",
]

LEGACY_FILES = [
    "tray_app.py",
    "webview_app.py",
    "webview_app_pywebview.py",
]


def _server_alive() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    result = s.connect_ex(("127.0.0.1", 8765)) == 0
    s.close()
    return result


# ── 구조 검사 ─────────────────────────────────────────────────────────────────


def test_local_server_exists():
    assert LOCAL_SERVER.exists(), "desktop/local_server.py 없음"


def test_ui_new_exists():
    assert UI_NEW.is_dir(), "desktop/ui_new/ 디렉터리 없음"


def test_ui_new_api_module():
    assert (UI_NEW / "api.py").exists(), "desktop/ui_new/api.py 없음"


def test_ui_new_dashboard_module():
    assert (UI_NEW / "dashboard.py").exists(), "desktop/ui_new/dashboard.py 없음"


def test_legacy_deprecated_doc():
    assert LEGACY_DOC.exists(), "desktop/LEGACY_UI_DEPRECATED.md 없음"


# ── local_server.py 라우팅 정책 검사 (AST, 서버 불필요) ──────────────────────


def _server_source() -> str:
    return LOCAL_SERVER.read_text(encoding="utf-8")


def test_health_json_endpoint_defined():
    src = _server_source()
    assert '"/health"' in src or "'/health'" in src, "/health 라우트 없음"
    assert "health_check" in src, "health_check 함수 없음"


def test_health_does_not_serve_html():
    src = _server_source()
    # /health 라우트가 index.html read_bytes 를 직접 호출하지 않는지 확인
    lines = src.splitlines()
    in_health = False
    for line in lines:
        if '"/health"' in line or "'/health'" in line:
            in_health = True
        if in_health and "read_bytes" in line and "index" in line:
            pytest.fail("/health 함수 내에서 index.html read_bytes 호출 발견")
        if in_health and line.strip().startswith("@app.") and "health" not in line:
            break  # 다음 라우트 진입 → health 블록 종료


def test_spa_fallback_has_api_protection():
    src = _server_source()
    assert "_API_PREFIXES" in src, "SPA fallback에 _API_PREFIXES 보호 없음"
    assert "NOT_FOUND" in src, "SPA fallback에 API 경로 404 반환 없음"


def test_preserved_endpoints_in_source():
    src = _server_source()
    missing = []
    for ep in PRESERVED_ENDPOINTS:
        # /ws/ui 는 WebSocket 라우트
        token = ep.replace("/", "", 1).split("/")[0]  # 첫 세그먼트
        if token not in src:
            missing.append(ep)
    assert not missing, f"누락된 endpoint 세그먼트: {missing}"


# ── api.py registry 검사 ────────────────────────────────────────────────────


def test_ui_new_api_uses_registry():
    api_src = (UI_NEW / "api.py").read_text(encoding="utf-8")
    assert "ENDPOINTS" in api_src, "api.py에 ENDPOINTS 레지스트리 없음"
    assert "def url(" in api_src, "api.py에 url() 헬퍼 없음"


def test_ui_new_api_no_hardcoded_in_dashboard():
    dash_src = (UI_NEW / "dashboard.py").read_text(encoding="utf-8")
    # dashboard.py는 직접 URL 문자열 대신 url() 함수를 통해 endpoint를 참조해야 함
    # url(key) 형태로 호출하거나 from .api import url 로 import 해야 함
    assert "from .api import url" in dash_src or "api.url(" in dash_src, (
        "dashboard.py가 api.url() 레지스트리를 사용하지 않음"
    )
    # 8765 포트 하드코딩은 api.py에만 있어야 함
    assert "8765" not in dash_src, "dashboard.py에 포트 번호 하드코딩"


# ── legacy deprecated 등록 검사 ──────────────────────────────────────────────


def test_legacy_files_in_deprecated_doc():
    doc = LEGACY_DOC.read_text(encoding="utf-8")
    for f in LEGACY_FILES:
        assert f in doc, f"{f} 가 deprecated 문서에 없음"


def test_legacy_ui_dir_in_deprecated_doc():
    doc = LEGACY_DOC.read_text(encoding="utf-8")
    assert "desktop/ui/" in doc or "ui/" in doc, "desktop/ui/ 가 deprecated 문서에 없음"


# ── py_compile 검사 ──────────────────────────────────────────────────────────


def test_local_server_compiles():
    import py_compile

    py_compile.compile(str(LOCAL_SERVER), doraise=True)


def test_ui_new_api_compiles():
    import py_compile

    py_compile.compile(str(UI_NEW / "api.py"), doraise=True)


def test_ui_new_dashboard_compiles():
    import py_compile

    py_compile.compile(str(UI_NEW / "dashboard.py"), doraise=True)


# ── live 서버 테스트 (8765 실행 중일 때만) ─────────────────────────────────────


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_health_returns_json():
    import urllib.request

    r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
    data = json.loads(r.read())
    assert data.get("ok") is True
    assert "service" in data
    assert "ts" in data


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_health_is_not_html():
    import urllib.request

    r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
    content = r.read()
    assert b"<!doctype" not in content.lower(), "/health가 HTML을 반환함"
    assert b"<html" not in content.lower()


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_agent_status_returns_json():
    import urllib.request

    r = urllib.request.urlopen("http://127.0.0.1:8765/agent/status", timeout=3)
    data = json.loads(r.read())
    assert "ok" in data


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_la_preflight_returns_json():
    import urllib.request

    r = urllib.request.urlopen("http://127.0.0.1:8765/local-agent/preflight", timeout=3)
    data = json.loads(r.read())
    assert "can_run" in data


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_unknown_nonapi_path_returns_index_not_json():
    """SPA fallback은 /app/ 같은 비API 경로에서만 동작해야 한다."""
    import urllib.request

    # /app/unknown 같은 비API 경로 → index.html (SPA 라우팅)
    r = urllib.request.urlopen("http://127.0.0.1:8765/app/unknown-page", timeout=3)
    content = r.read()
    # SPA fallback이면 HTML 또는 404 (index.html 없으면 404 텍스트)
    assert b"<html" in content.lower() or b"not found" in content.lower(), "/app/ 경로가 HTML 또는 404를 반환해야 함"


@pytest.mark.skipif(not _server_alive(), reason="local_server 미실행")
def test_no_secret_in_health_response():
    import urllib.request

    r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
    body = r.read().decode()
    for pattern in ("password", "token", "cookie", "api_key", "secret", "sk-", "bearer"):
        assert pattern not in body.lower(), f"/health 응답에 민감 패턴 발견: {pattern}"
