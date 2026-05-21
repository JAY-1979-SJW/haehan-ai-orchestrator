# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-REGISTRY-STATUS-01 — registry + status route tests.

본 트랙 범위: registry 모델 + GET /cad/bridge/status 만. start/stop/
restart/proxy/kill 일체 없음.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop import cad_bridge_registry as reg
from desktop.local_server import app

REGISTRY_FILE = ROOT / "desktop" / "cad_bridge_registry.py"
LOCAL_SERVER_FILE = ROOT / "desktop" / "local_server.py"


# ──────────────────────────────────────────────
# 1. 포트 / host 기본값 contract
# ──────────────────────────────────────────────

def test_default_cad_bridge_port_is_8766():
    assert reg.DEFAULT_CAD_BRIDGE_PORT == 8766


def test_desktop_hub_port_separated_from_bridge():
    """desktop:8765 와 CAD bridge default:8766 분리."""
    assert reg.DESKTOP_HUB_PORT == 8765
    assert reg.DEFAULT_CAD_BRIDGE_PORT != reg.DESKTOP_HUB_PORT


def test_8001_is_forbidden():
    assert 8001 in reg.FORBIDDEN_CAD_BRIDGE_PORTS


def test_default_host_is_loopback():
    assert reg.DEFAULT_CAD_BRIDGE_HOST == "127.0.0.1"


def test_no_8001_anywhere_in_registry_as_live_port():
    """8001 은 정책 docstring + FORBIDDEN_CAD_BRIDGE_PORTS 상수 외에 등장 금지.

    docstring 정책 표기 1줄 + 상수 1줄 = 최대 2회. host:port 문자열,
    DEFAULT_*, 변수 할당에 8001 사용 금지.
    """
    src = REGISTRY_FILE.read_text(encoding="utf-8")
    occurrences = src.count("8001")
    assert occurrences <= 2, f"expected ≤2 (docstring+const), found {occurrences}"
    # 실제 포트 할당으로서의 8001 금지
    forbidden_live = (
        ":8001", "= 8001", "port=8001", "PORT = 8001", "PORT=8001",
    )
    for token in forbidden_live:
        assert token not in src, f"8001 used as live port: {token!r}"


# ──────────────────────────────────────────────
# 2. cross-repo boundary — CAD 모듈 import 금지
# ──────────────────────────────────────────────

def test_registry_does_not_import_cad_repo_modules():
    src = REGISTRY_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_prefixes = (
        "local_bridge", "app.backend", "app.frontend",
        "mcp_server",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fp in forbidden_prefixes:
                assert not node.module.startswith(fp), (
                    f"forbidden import: {node.module}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for fp in forbidden_prefixes:
                    assert not alias.name.startswith(fp), (
                        f"forbidden import: {alias.name}"
                    )


def test_registry_does_not_import_autocad_or_com():
    src = REGISTRY_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "win32com", "pythoncom", "AutoCAD.Application",
        "GetActiveObject", ".SendCommand(", ".SelectAll(",
        "from sqlalchemy", "import sqlalchemy",
    ):
        assert forbidden not in src


# ──────────────────────────────────────────────
# 3. process start/stop/kill 0건
# ──────────────────────────────────────────────

def test_registry_has_no_process_lifecycle_code():
    src = REGISTRY_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess.Popen", "subprocess.run", "subprocess.call",
        "os.kill(", "taskkill /F", "taskkill -F",
        "Stop-Process", ".terminate()", ".kill()",
        "psutil",
    ):
        assert forbidden not in src, (
            f"lifecycle keyword leaked into registry: {forbidden}"
        )


def test_local_server_route_does_not_start_process():
    src = LOCAL_SERVER_FILE.read_text(encoding="utf-8")
    # status route 본문이 process lifecycle 호출 안 함
    idx = src.find("def get_cad_bridge_status")
    assert idx >= 0
    block = src[idx: idx + 800]
    for forbidden in (
        "subprocess.", "Popen(", "os.kill(", "Stop-Process",
        ".terminate(", ".kill(",
    ):
        assert forbidden not in block


# ──────────────────────────────────────────────
# 4. CadBridgeConfig
# ──────────────────────────────────────────────

def test_config_is_configured_with_defaults():
    c = reg.CadBridgeConfig()
    assert c.is_configured() is True
    assert c.host == "127.0.0.1"
    assert c.port == 8766


def test_config_not_configured_when_port_is_forbidden():
    c = reg.CadBridgeConfig(port=8001)
    assert c.is_configured() is False


def test_config_not_configured_when_port_collides_with_hub():
    c = reg.CadBridgeConfig(port=reg.DESKTOP_HUB_PORT)
    assert c.is_configured() is False


def test_config_base_url():
    c = reg.CadBridgeConfig(host="127.0.0.1", port=8766)
    assert c.base_url() == "http://127.0.0.1:8766"


# ──────────────────────────────────────────────
# 5. check_status — 네 분류
# ──────────────────────────────────────────────

def test_check_status_not_configured_returns_NOT_CONFIGURED():
    c = reg.CadBridgeConfig(port=8001)
    s = reg.check_status(c)
    assert s.status == reg.STATUS_NOT_CONFIGURED
    assert s.port == 8001


def test_check_status_connection_refused_returns_STOPPED(monkeypatch):
    """fetch 가 URLError 면 STOPPED."""
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    c = reg.CadBridgeConfig(port=8766)
    s = reg.check_status(c)
    assert s.status == reg.STATUS_STOPPED


def test_check_status_running_when_signature_path_present(monkeypatch):
    fake_openapi = {
        "paths": {
            "/acad/arch-quantity-tab/build-cards": {"post": {}},
            "/foo/bar": {"get": {}},
        }
    }
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: fake_openapi)
    c = reg.CadBridgeConfig(port=8766)
    s = reg.check_status(c)
    assert s.status == reg.STATUS_RUNNING
    assert s.signaturePathsPresent == 1


def test_check_status_unreachable_when_different_service_on_port(monkeypatch):
    """port 응답이 있지만 CAD bridge signature path 부재 → UNREACHABLE."""
    fake_openapi = {"paths": {"/some/other": {}, "/ws/ui": {}}}
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: fake_openapi)
    c = reg.CadBridgeConfig(port=8766)
    s = reg.check_status(c)
    assert s.status == reg.STATUS_UNREACHABLE
    assert "no CAD bridge signature path" in (s.detail or "")


def test_check_status_unknown_when_paths_not_dict(monkeypatch):
    fake_openapi = {"paths": "broken"}
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: fake_openapi)
    s = reg.check_status(reg.CadBridgeConfig())
    assert s.status == reg.STATUS_UNKNOWN


# ──────────────────────────────────────────────
# 6. _safe_fetch_openapi 예외 격리 — desktop 서버 보호
# ──────────────────────────────────────────────

def test_safe_fetch_returns_none_on_url_error(monkeypatch):
    def boom(url, timeout=None):  # noqa: ARG001
        raise URLError("connection refused")
    monkeypatch.setattr(reg, "urlopen", boom)
    assert reg._safe_fetch_openapi("http://127.0.0.1:8766") is None


def test_safe_fetch_returns_none_on_unexpected_error(monkeypatch):
    def boom(url, timeout=None):  # noqa: ARG001
        raise RuntimeError("unexpected")
    monkeypatch.setattr(reg, "urlopen", boom)
    assert reg._safe_fetch_openapi("http://127.0.0.1:8766") is None


# ──────────────────────────────────────────────
# 7. GET /cad/bridge/status route
# ──────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


def test_status_route_returns_200_when_bridge_unreachable(client, monkeypatch):
    """bridge 미기동이어도 desktop 서버는 200 + STOPPED 반환."""
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == reg.STATUS_STOPPED
    assert data["port"] == reg.DEFAULT_CAD_BRIDGE_PORT


def test_status_route_returns_200_when_bridge_running(client, monkeypatch):
    fake_openapi = {
        "paths": {"/acad/arch-quantity-tab/build-cards": {"post": {}}}
    }
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: fake_openapi)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    assert res.json()["status"] == reg.STATUS_RUNNING


def test_status_route_does_not_crash_desktop_on_internal_error(
    client, monkeypatch,
):
    """registry.check_status 가 어떤 예외를 던져도 desktop 서버는 200 유지.

    local_server 가 import 시점에 `_cad_bridge_check_status` 로 alias
    binding 을 만들었으므로 그 binding 을 monkeypatch.
    """
    from desktop import local_server

    def boom(_config):
        raise RuntimeError("simulated catastrophic failure")
    monkeypatch.setattr(local_server, "_cad_bridge_check_status", boom)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UNKNOWN"


# ──────────────────────────────────────────────
# 8. lifecycle/proxy 라우트가 아직 없음 — 본 트랙 범위 분리
# ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/cad/bridge/proxy/openapi.json",
    "/cad/bridge/proxy/acad/arch-quantity-tab/build-cards",
])
def test_proxy_routes_not_yet_registered(client, path):
    """CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01 이후 의미 보존 갱신.

    lifecycle 트랙에서 start/stop/restart 가 등록되었으므로 본 테스트는
    proxy 미등록 검증만 남긴다 (proxy 는 별 트랙).
    """
    res = client.get(path)
    assert res.status_code in (404, 405)


# ──────────────────────────────────────────────
# 9. envelope contract
# ──────────────────────────────────────────────

def test_status_response_shape(client, monkeypatch):
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    res = client.get("/cad/bridge/status")
    data = res.json()
    for k in ("status", "host", "port", "detail", "signaturePathsPresent"):
        assert k in data
    assert data["status"] in reg.ALL_STATUSES + ("UNKNOWN",)
