# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-PROXY-01 — proxy tests.

httpx.AsyncClient 를 FakeAsyncClient 로 monkeypatch — 실 upstream 호출 0건.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop import cad_bridge_proxy as proxy_mod
from desktop.local_server import app

PROXY_FILE = ROOT / "desktop" / "cad_bridge_proxy.py"
SRV_FILE = ROOT / "desktop" / "local_server.py"


# ──────────────────────────────────────────────
# Fake httpx — capture upstream interaction
# ──────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code=200, content=b'{"ok":true}',
                 content_type="application/json", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type, **(headers or {})}


class FakeAsyncClient:
    captured = []
    response_factory = staticmethod(lambda: FakeResponse())
    raise_on_call = None  # 예: httpx.TimeoutException()

    def __init__(self, timeout=None, **kw):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        FakeAsyncClient.captured.append({
            "method": "GET", "url": url, "headers": dict(headers or {}),
            "body": None,
        })
        if FakeAsyncClient.raise_on_call is not None:
            raise FakeAsyncClient.raise_on_call
        return FakeAsyncClient.response_factory()

    async def post(self, url, content=None, headers=None):
        FakeAsyncClient.captured.append({
            "method": "POST", "url": url, "headers": dict(headers or {}),
            "body": content,
        })
        if FakeAsyncClient.raise_on_call is not None:
            raise FakeAsyncClient.raise_on_call
        return FakeAsyncClient.response_factory()


@pytest.fixture
def fake_httpx(monkeypatch):
    FakeAsyncClient.captured = []
    FakeAsyncClient.response_factory = staticmethod(lambda: FakeResponse())
    FakeAsyncClient.raise_on_call = None
    monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


@pytest.fixture
def client():
    return TestClient(app)


# ──────────────────────────────────────────────
# 1. Allow-list — GET / POST
# ──────────────────────────────────────────────

def test_get_acad_health_allowed(client, fake_httpx):
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.status_code == 200
    assert len(fake_httpx.captured) == 1
    captured = fake_httpx.captured[0]
    assert captured["method"] == "GET"
    assert captured["url"] == "http://127.0.0.1:8766/acad/health"


def test_get_query_string_passthrough(client, fake_httpx):
    res = client.get(
        "/cad/bridge/proxy/acad/openapi.json?include=tags&v=1",
    )
    assert res.status_code == 200
    captured = fake_httpx.captured[0]
    assert "include=tags" in captured["url"]
    assert "v=1" in captured["url"]


def test_post_arch_quantity_tab_build_cards_allowed(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/arch-quantity-tab/build-cards",
        json={"hint": "x"},
    )
    assert res.status_code == 200
    captured = fake_httpx.captured[0]
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/acad/arch-quantity-tab/build-cards")
    assert b'"hint"' in captured["body"]


def test_post_inventory_analyze_allowed(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/inventory/analyze-drawing-inventory",
        json={},
    )
    assert res.status_code == 200


def test_post_schedule_tables_detect_allowed(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/schedule-tables/detect", json={},
    )
    assert res.status_code == 200


def test_post_construction_sequence_plan_allowed(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/construction-sequence/plan", json={},
    )
    assert res.status_code == 200


# ──────────────────────────────────────────────
# 2. Upstream response passthrough
# ──────────────────────────────────────────────

def test_upstream_status_code_preserved(client, fake_httpx):
    fake_httpx.response_factory = staticmethod(
        lambda: FakeResponse(status_code=418, content=b"teapot"),
    )
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.status_code == 418


def test_upstream_content_type_preserved(client, fake_httpx):
    fake_httpx.response_factory = staticmethod(
        lambda: FakeResponse(
            content=b"plain text", content_type="text/plain; charset=utf-8",
        ),
    )
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.headers["content-type"].startswith("text/plain")


def test_upstream_500_propagates(client, fake_httpx):
    fake_httpx.response_factory = staticmethod(
        lambda: FakeResponse(status_code=500, content=b'{"err":"x"}'),
    )
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.status_code == 500


def test_upstream_response_body_no_source_marker_injected(client, fake_httpx):
    """live response 에 _source / fallback marker 주입 0건."""
    fake_httpx.response_factory = staticmethod(
        lambda: FakeResponse(content=b'{"ok":true,"cards":[]}'),
    )
    res = client.get("/cad/bridge/proxy/acad/health")
    body = res.text
    assert "_source" not in body
    assert "fallback" not in body
    assert "_generatedBy" not in body


def test_upstream_timeout_returns_504(client, fake_httpx):
    fake_httpx.raise_on_call = httpx.TimeoutException("simulated")
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.status_code == 504
    data = res.json()
    assert data["error"] == "upstream_timeout"


def test_upstream_unreachable_returns_502(client, fake_httpx):
    fake_httpx.raise_on_call = httpx.ConnectError("refused")
    res = client.get("/cad/bridge/proxy/acad/health")
    assert res.status_code == 502


# ──────────────────────────────────────────────
# 3. Method 차단
# ──────────────────────────────────────────────

@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_method_blocked(client, fake_httpx, method):
    res = client.request(method, "/cad/bridge/proxy/acad/health")
    # FastAPI 라우트가 GET/POST 만 정의되어 405 또는 method_not_allowed
    assert res.status_code in (403, 405)
    # upstream 호출 0건
    assert len(fake_httpx.captured) == 0


def test_is_allowed_rejects_put():
    ok, reason = proxy_mod.is_allowed_cad_proxy_request("PUT", "acad/health")
    assert ok is False
    assert "method_not_allowed" in reason


# ──────────────────────────────────────────────
# 4. Allow-list 외 path → 403
# ──────────────────────────────────────────────

def test_get_non_allowlisted_acad_path_403(client, fake_httpx):
    res = client.get("/cad/bridge/proxy/acad/unknown/path")
    assert res.status_code == 403
    assert len(fake_httpx.captured) == 0
    data = res.json()
    assert data["blocked"] is True


def test_post_non_allowlisted_acad_path_403(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/random/endpoint", json={"x": 1},
    )
    assert res.status_code == 403
    assert len(fake_httpx.captured) == 0


def test_non_acad_namespace_blocked(client, fake_httpx):
    res = client.get("/cad/bridge/proxy/other/path")
    assert res.status_code == 403
    data = res.json()
    assert data["reason"] == "path_not_in_acad_namespace"


# ──────────────────────────────────────────────
# 5. Mutating keyword 차단
# ──────────────────────────────────────────────

@pytest.mark.parametrize("kw_path", [
    "acad/quantity/execute",
    "acad/inventory/apply",
    "acad/dxf/mutate",
    "acad/save/document",
    "acad/file/delete",
    "acad/material/remove",
    "acad/finish/update",
    "acad/approve/binding",
    "acad/reject/candidate",
    "acad/command/run",
    "acad/command/execute",
    "acad/cad-control/execute",
])
def test_mutating_keyword_blocked(client, fake_httpx, kw_path):
    res = client.post(f"/cad/bridge/proxy/{kw_path}", json={})
    assert res.status_code == 403
    assert len(fake_httpx.captured) == 0
    data = res.json()
    assert "mutating_keyword_blocked" in data["reason"]


# ──────────────────────────────────────────────
# 6. Path traversal / absolute URL injection
# ──────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "acad/../etc/passwd",
    "acad/health/../secret",
])
def test_path_traversal_blocked(client, fake_httpx, bad):
    res = client.get(f"/cad/bridge/proxy/{bad}")
    assert res.status_code == 403
    assert len(fake_httpx.captured) == 0


def test_normalize_rejects_traversal():
    with pytest.raises(ValueError, match="traversal"):
        proxy_mod.normalize_proxy_path("acad/../../foo")


def test_normalize_rejects_absolute_url_injection():
    with pytest.raises(ValueError, match="absolute URL"):
        proxy_mod.normalize_proxy_path("http://evil.local/x")


def test_normalize_rejects_double_slash_prefix():
    with pytest.raises(ValueError, match="absolute URL"):
        proxy_mod.normalize_proxy_path("//evil.local/x")


def test_normalize_collapses_duplicate_slashes_and_dot_segments():
    assert proxy_mod.normalize_proxy_path("acad//health") == "acad/health"
    assert proxy_mod.normalize_proxy_path("acad/./health") == "acad/health"


# ──────────────────────────────────────────────
# 7. Host header injection / Authorization stripping
# ──────────────────────────────────────────────

def test_host_header_does_not_change_upstream_host(client, fake_httpx):
    """클라이언트가 Host: evil.local 헤더를 보내도 upstream 은 127.0.0.1:8766 유지."""
    res = client.get(
        "/cad/bridge/proxy/acad/health",
        headers={"Host": "evil.local"},
    )
    assert res.status_code == 200
    captured = fake_httpx.captured[0]
    assert captured["url"].startswith("http://127.0.0.1:8766/")
    # forward 된 헤더에 Host 포함 0건
    assert all(k.lower() != "host" for k in captured["headers"])


def test_authorization_header_not_forwarded(client, fake_httpx):
    res = client.get(
        "/cad/bridge/proxy/acad/health",
        headers={"Authorization": "Bearer secret-token"},
    )
    captured = fake_httpx.captured[0]
    assert all(
        k.lower() != "authorization" for k in captured["headers"]
    )


def test_only_content_type_and_accept_forwarded(client, fake_httpx):
    res = client.post(
        "/cad/bridge/proxy/acad/arch-quantity-tab/build-cards",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": "session=abc",
            "X-Custom": "leak-attempt",
        },
        content=b"{}",
    )
    captured = fake_httpx.captured[0]
    keys_lower = {k.lower() for k in captured["headers"]}
    assert "content-type" in keys_lower
    assert "accept" in keys_lower
    assert "cookie" not in keys_lower
    assert "x-custom" not in keys_lower


# ──────────────────────────────────────────────
# 8. 기존 route 무회귀
# ──────────────────────────────────────────────

def test_status_route_still_works(client, fake_httpx, monkeypatch):
    from desktop import cad_bridge_registry as reg
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    assert "status" in res.json()


def test_lifecycle_routes_registered(client):
    # start/stop/restart 라우트 매핑은 존재 — body 없는 POST 가 200
    # (FakeRunner 미설치 상태에서 실제 runner 가 호출되나, runner 가 안전하게
    # cad_repo_path 미설정 → error snapshot 반환)
    res_start = client.post("/cad/bridge/start")
    res_stop = client.post("/cad/bridge/stop")
    res_restart = client.post("/cad/bridge/restart")
    assert res_start.status_code == 200
    assert res_stop.status_code == 200
    assert res_restart.status_code == 200


def test_proxy_admin_route_not_disturbed():
    """기존 /proxy/admin/{path} prefix 와 충돌 0건."""
    src = SRV_FILE.read_text(encoding="utf-8")
    assert "/proxy/admin/{path:path}" in src
    # cad bridge proxy 는 다른 prefix
    assert "/cad/bridge/proxy/{path:path}" in src


# ──────────────────────────────────────────────
# 9. 정책 — CAD repo import / AutoCAD / subprocess / executor wiring 0
# ──────────────────────────────────────────────

def test_proxy_does_not_import_cad_repo():
    src = PROXY_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_prefixes = ("local_bridge", "app.backend", "app.frontend",
                          "mcp_server")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fp in forbidden_prefixes:
                assert not node.module.startswith(fp), (
                    f"forbidden import: {node.module}"
                )
        elif isinstance(node, ast.Import):
            for a in node.names:
                for fp in forbidden_prefixes:
                    assert not a.name.startswith(fp)


def test_proxy_does_not_run_subprocess_or_kill():
    src = PROXY_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess.Popen", "subprocess.run", "subprocess.call",
        "os.system(", "os.kill(", "taskkill /F", "taskkill -F",
        "Stop-Process", ".terminate(", ".kill(",
    ):
        assert forbidden not in src


def test_proxy_does_not_import_autocad_or_com():
    src = PROXY_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "win32com", "pythoncom", "AutoCAD.Application",
        "GetActiveObject", ".SendCommand(", ".SelectAll(",
    ):
        assert forbidden not in src


def test_proxy_does_not_wire_executor():
    src = PROXY_FILE.read_text(encoding="utf-8")
    # local_agent.cad.executor / cad_execute 등 실 실행 함수 호출 0건
    for forbidden in (
        "cad_execute(", "from local_agent.cad.executor",
        "command_executor", "execute_cad_command",
    ):
        assert forbidden not in src


# ──────────────────────────────────────────────
# 10. Allow-list ↔ command_contract 정합
# ──────────────────────────────────────────────

def test_post_allow_superset_of_command_contract_candidates():
    """proxy POST allow-list 는 command_contract 의 CANDIDATE_PAYLOAD
    endpointPath 를 모두 포함한다."""
    from local_agent.cad.command_contract import (
        DEFAULT_REGISTRY, RiskLevel,
    )
    cp_paths = set()
    for tid in DEFAULT_REGISTRY.list_by_risk(RiskLevel.CANDIDATE_PAYLOAD):
        entry = DEFAULT_REGISTRY.get(tid)
        if entry.endpointPath:
            cp_paths.add(entry.endpointPath.lstrip("/"))
    assert cp_paths <= proxy_mod.POST_ALLOW


# ──────────────────────────────────────────────
# 11. Build URL contract
# ──────────────────────────────────────────────

def test_build_upstream_url_default_8766():
    url = proxy_mod.build_cad_bridge_upstream_url("acad/health")
    assert url == "http://127.0.0.1:8766/acad/health"


def test_build_upstream_url_with_query():
    url = proxy_mod.build_cad_bridge_upstream_url(
        "acad/openapi.json", query="v=1",
    )
    assert url == "http://127.0.0.1:8766/acad/openapi.json?v=1"


def test_build_upstream_url_rejects_absolute():
    with pytest.raises(ValueError):
        proxy_mod.build_cad_bridge_upstream_url("http://evil/x")
