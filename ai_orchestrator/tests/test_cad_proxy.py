"""CAD 프록시 라우터(/api/v1/cad/*) 권한/승인/중계/감사 스모크.

실 cad-backend 없이 동작하도록 httpx.AsyncClient 를 monkeypatch 로 stub.

검증 포인트:
- /api/v1/cad/* 는 인증 없으면 401
- 읽기(GET) 는 viewer 이상 모두 허용
- 쓰기(POST/PATCH/DELETE) 는 operator 이상이고 approval token 이 유효해야 허용
- approval 미첨부/무효 시 403 + CAD_PROXY_DENIED 이벤트
- 정상 호출 시 상류 응답 상태/바디가 그대로 통과하고 CAD_PROXY_CALL 감사
- 상류 네트워크 실패 → 502 + CAD_PROXY_UPSTREAM_ERROR
- 상류 타임아웃 → 504
- 상류 URL 이 /api/v1/{path} 로 재조립되고 query 가 그대로 전달
- 요청 헤더의 Authorization / X-Task-Id / X-Approval-Token-Id 는 상류로 전달되지 않음
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    users_path = tmp_path_factory.mktemp("policies") / "http_users.json"
    users_path.write_text(
        json.dumps([
            {"username": "owner_u",    "password_hash": "pw-owner",    "role": "owner",    "enabled": True},
            {"username": "admin_u",    "password_hash": "pw-admin",    "role": "admin",    "enabled": True},
            {"username": "operator_u", "password_hash": "pw-operator", "role": "operator", "enabled": True},
            {"username": "viewer_u",   "password_hash": "pw-viewer",   "role": "viewer",   "enabled": True},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["HTTP_USERS_PATH"] = str(users_path)
    os.environ["CAD_BACKEND_URL"] = "http://cad-backend.test:8000"

    # 모듈 리로드 순서: config → auth → 서브라우터들 → main router → server
    from ai_orchestrator import config as _config
    importlib.reload(_config)
    from ai_orchestrator import auth as _auth
    importlib.reload(_auth)
    from ai_orchestrator.sites import router as _sites_router
    importlib.reload(_sites_router)
    from ai_orchestrator.cad import router as _cad_router
    importlib.reload(_cad_router)
    from ai_orchestrator import router as _router
    importlib.reload(_router)
    from ai_orchestrator import server as _server
    importlib.reload(_server)

    from fastapi.testclient import TestClient
    c = TestClient(_server.app, raise_server_exceptions=True)
    yield c

    os.environ["AUTH_ENABLED"] = "false"
    os.environ.pop("HTTP_USERS_PATH", None)
    os.environ.pop("CAD_BACKEND_URL", None)
    importlib.reload(_config)
    importlib.reload(_auth)
    importlib.reload(_sites_router)
    importlib.reload(_cad_router)
    importlib.reload(_router)
    importlib.reload(_server)


def _basic(username: str) -> tuple:
    return (username, f"pw-{username.split('_')[0]}")


# ───────────────────────────────────────────────────────────────────
# httpx stub — AsyncClient(...).request(...) 를 가로채서 지정 응답 반환
# ───────────────────────────────────────────────────────────────────
class _FakeResp:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"{}",
        headers: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.content = content
        self.headers = httpx.Headers(headers or {"content-type": "application/json"})


def _install_httpx_stub(monkeypatch, *, response=None, exc: Exception = None):
    """httpx.AsyncClient 를 통째로 대체. request 호출 인자를 calls 에 기록.

    response 가 주어지면 해당 응답을, exc 면 해당 예외를 던진다.
    """
    calls: list[dict] = []

    class _StubClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kw):
            calls.append({"method": method, "url": url, **kw})
            if exc is not None:
                raise exc
            return response if response is not None else _FakeResp()

    from ai_orchestrator.cad import router as cad_mod
    monkeypatch.setattr(cad_mod.httpx, "AsyncClient", _StubClient)
    return calls


# ═══════════════════════════════════════════════════════════════════
# 1) 인증/권한 게이트
# ═══════════════════════════════════════════════════════════════════
def test_requires_auth(client):
    r = client.get("/api/v1/cad/projects")
    assert r.status_code == 401


def test_viewer_can_read(client, monkeypatch):
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200, content=b'{"items":[]}'),
    )
    r = client.get("/api/v1/cad/projects", auth=_basic("viewer_u"))
    assert r.status_code == 200
    assert r.json() == {"items": []}
    assert len(calls) == 1
    # 상류 URL 재조립 확인
    assert calls[0]["url"] == "http://cad-backend.test:8000/api/v1/projects"
    assert calls[0]["method"] == "GET"


def test_query_string_passed(client, monkeypatch):
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200, content=b'{"ok":true}'),
    )
    r = client.get(
        "/api/v1/cad/projects?status=active&limit=10",
        auth=_basic("admin_u"),
    )
    assert r.status_code == 200
    assert calls[0]["url"].endswith("/api/v1/projects?status=active&limit=10")


# ═══════════════════════════════════════════════════════════════════
# 2) 쓰기 메서드 — approval 게이트
# ═══════════════════════════════════════════════════════════════════
def test_write_without_approval_forbidden(client, monkeypatch):
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200),
    )
    r = client.post(
        "/api/v1/cad/projects",
        json={"name": "t1"},
        auth=_basic("operator_u"),
    )
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["error"] == "approval_required"
    # 상류 호출은 발생하지 않았어야 한다
    assert calls == []


def test_write_viewer_forbidden_even_with_token(client, monkeypatch):
    # viewer 는 쓰기 role 자체가 부족 — 토큰이 있어도 막혀야 한다
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200),
    )
    with patch(
        "ai_orchestrator.cad.router.approval.validate_token",
        return_value=True,
    ):
        r = client.post(
            "/api/v1/cad/projects",
            json={"name": "t1"},
            auth=_basic("viewer_u"),
            headers={
                "X-Task-Id": "t-1",
                "X-Approval-Token-Id": "tok-1",
            },
        )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "role_insufficient"
    assert calls == []


def test_write_invalid_token_denied(client, monkeypatch):
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200),
    )
    with patch(
        "ai_orchestrator.cad.router.approval.validate_token",
        return_value=False,
    ):
        r = client.post(
            "/api/v1/cad/projects",
            json={"name": "t1"},
            auth=_basic("operator_u"),
            headers={
                "X-Task-Id": "t-x",
                "X-Approval-Token-Id": "tok-bad",
            },
        )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "approval_invalid_or_expired"
    assert calls == []


def test_write_with_valid_approval_proxies(client, monkeypatch):
    calls = _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(
            status_code=201,
            content=b'{"id":42,"name":"t1"}',
        ),
    )
    with patch(
        "ai_orchestrator.cad.router.approval.validate_token",
        return_value=True,
    ):
        r = client.post(
            "/api/v1/cad/projects",
            json={"name": "t1"},
            auth=_basic("admin_u"),
            headers={
                "X-Task-Id": "t-ok",
                "X-Approval-Token-Id": "tok-good",
                "X-Custom-Trace": "abc123",
            },
        )
    assert r.status_code == 201
    assert r.json() == {"id": 42, "name": "t1"}
    assert len(calls) == 1
    # 상류 URL
    assert calls[0]["url"] == "http://cad-backend.test:8000/api/v1/projects"
    # 헤더 검증 — Authorization / X-Task-Id / X-Approval-Token-Id 는
    # 상류로 새지 않아야 한다. X-Custom-Trace 같은 일반 헤더는 전달.
    fwd = calls[0]["headers"]
    low = {k.lower() for k in fwd.keys()}
    assert "authorization" not in low
    assert "x-task-id" not in low
    assert "x-approval-token-id" not in low
    assert fwd.get("X-Orchestrator-Actor") == "admin_u"
    assert fwd.get("X-Forwarded-For") == "orchestrator"
    # 본문은 그대로 전달
    assert calls[0]["content"] == b'{"name":"t1"}' or b'"name":"t1"' in calls[0]["content"]


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_other_write_methods_require_approval(client, monkeypatch, method):
    calls = _install_httpx_stub(monkeypatch, response=_FakeResp())
    r = client.request(
        method,
        "/api/v1/cad/projects/1",
        auth=_basic("admin_u"),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "approval_required"
    assert calls == []


# ═══════════════════════════════════════════════════════════════════
# 3) 상류 에러 전파
# ═══════════════════════════════════════════════════════════════════
def test_upstream_unreachable_502(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        exc=httpx.ConnectError("no route"),
    )
    r = client.get("/api/v1/cad/projects", auth=_basic("viewer_u"))
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "upstream_unreachable"


def test_upstream_timeout_504(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        exc=httpx.ReadTimeout("slow"),
    )
    r = client.get("/api/v1/cad/projects", auth=_basic("viewer_u"))
    assert r.status_code == 504
    assert r.json()["detail"]["error"] == "upstream_timeout"


# ═══════════════════════════════════════════════════════════════════
# 4) 감사 로그
# ═══════════════════════════════════════════════════════════════════
def test_successful_call_logs_cad_proxy_call(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(status_code=200, content=b"{}"),
    )
    logged: list = []
    with patch(
        "ai_orchestrator.cad.router.log_event",
        side_effect=lambda event_type, **kw: logged.append({"event_type": event_type, **kw}),
    ):
        r = client.get(
            "/api/v1/cad/projects/1/drawings",
            auth=_basic("operator_u"),
        )
    assert r.status_code == 200
    events = [e["event_type"] for e in logged]
    assert "CAD_PROXY_CALL" in events
    e = next(e for e in logged if e["event_type"] == "CAD_PROXY_CALL")
    assert e["actor"] == "operator_u"
    assert e["role"] == "operator"
    assert e["target"] == "/api/v1/projects/1/drawings"
    assert e["decision"] == "200"


def test_denied_write_logs_cad_proxy_denied(client, monkeypatch):
    _install_httpx_stub(monkeypatch, response=_FakeResp())
    logged: list = []
    with patch(
        "ai_orchestrator.cad.router.log_event",
        side_effect=lambda event_type, **kw: logged.append({"event_type": event_type, **kw}),
    ):
        r = client.post(
            "/api/v1/cad/projects",
            json={"name": "x"},
            auth=_basic("operator_u"),
        )
    assert r.status_code == 403
    events = [e["event_type"] for e in logged]
    assert "CAD_PROXY_DENIED" in events
    e = next(e for e in logged if e["event_type"] == "CAD_PROXY_DENIED")
    assert e["decision"] == "approval_required"
    assert e["target"] == "/api/v1/projects"


def test_upstream_error_logs_upstream_error(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        exc=httpx.ConnectError("nope"),
    )
    logged: list = []
    with patch(
        "ai_orchestrator.cad.router.log_event",
        side_effect=lambda event_type, **kw: logged.append({"event_type": event_type, **kw}),
    ):
        r = client.get("/api/v1/cad/projects", auth=_basic("owner_u"))
    assert r.status_code == 502
    events = [e["event_type"] for e in logged]
    assert "CAD_PROXY_UPSTREAM_ERROR" in events


def test_event_types_registered():
    from ai_orchestrator.audit_logger import EVENT_TYPES
    assert "CAD_PROXY_CALL" in EVENT_TYPES
    assert "CAD_PROXY_DENIED" in EVENT_TYPES
    assert "CAD_PROXY_UPSTREAM_ERROR" in EVENT_TYPES


# ═══════════════════════════════════════════════════════════════════
# 5) body / response 패스스루
# ═══════════════════════════════════════════════════════════════════
def test_response_body_passthrough(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(
            status_code=418,
            content=b'{"hello":"world","n":3}',
            headers={"content-type": "application/json"},
        ),
    )
    r = client.get("/api/v1/cad/anything", auth=_basic("owner_u"))
    assert r.status_code == 418
    assert r.json() == {"hello": "world", "n": 3}


def test_upstream_4xx_passes_through(client, monkeypatch):
    _install_httpx_stub(
        monkeypatch,
        response=_FakeResp(
            status_code=404,
            content=b'{"detail":"not found"}',
        ),
    )
    r = client.get("/api/v1/cad/projects/9999", auth=_basic("viewer_u"))
    assert r.status_code == 404
    assert r.json()["detail"] == "not found"
