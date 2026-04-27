"""api_client — HTTP 호출 단위 테스트.

실제 네트워크를 쓰지 않는다. ``urllib.request.urlopen`` 을 fake 로
대체해 요청 URL / 메서드 / 헤더 / 응답 파싱을 검증한다.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional
from urllib import error as urllib_error

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


class _FakeResp:
    def __init__(self, status: int = 200, body: bytes = b""):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_urlopen(monkeypatch, handler):
    """handler(req) -> _FakeResp 또는 raise HTTPError/URLError 로 동작."""
    from agent import api_client
    captured = {"calls": []}

    def _fake(req, timeout: float = 10):
        captured["calls"].append({
            "url": req.full_url,
            "method": req.get_method(),
            "headers": {k.lower(): v for k, v in req.header_items()},
            "data": req.data,
            "timeout": timeout,
        })
        return handler(req)

    monkeypatch.setattr(api_client.urllib_request, "urlopen", _fake)
    return captured


# ──────────────────────────────────────────────────────────────────
# fetch_task
# ──────────────────────────────────────────────────────────────────
def test_fetch_task_success_wrapped(monkeypatch):
    from agent import api_client
    cap = _install_urlopen(
        monkeypatch,
        lambda req: _FakeResp(
            200, b'{"task": {"id": "t-1", "action": "excel.run_poc"}}',
        ),
    )
    task, err = api_client.fetch_task("http://x.example", "abc123")
    assert err is None
    assert task == {"id": "t-1", "action": "excel.run_poc"}
    call = cap["calls"][0]
    assert call["url"] == "http://x.example/tasks/poll"
    assert call["method"] == "GET"
    assert call["headers"]["authorization"] == "Bearer abc123"


def test_fetch_task_success_bare_task_body(monkeypatch):
    from agent import api_client
    _install_urlopen(
        monkeypatch,
        lambda req: _FakeResp(200, b'{"id": "t-2", "action": "excel.read_cell"}'),
    )
    task, err = api_client.fetch_task("http://x", "t")
    assert err is None
    assert task["id"] == "t-2"


def test_fetch_task_empty_queue_empty_object(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b"{}"))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err is None


def test_fetch_task_empty_queue_null(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b"null"))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err is None


def test_fetch_task_empty_queue_wrapped_null(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b'{"task": null}'))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err is None


def test_fetch_task_empty_body(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b""))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err is None


def test_fetch_task_malformed_json(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b"{bad json"))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err == api_client.API_BAD_RESPONSE


def test_fetch_task_wrapped_non_dict(monkeypatch):
    from agent import api_client
    _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b'{"task": 123}'))
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err == api_client.API_BAD_RESPONSE


def test_fetch_task_auth_failed(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.HTTPError(
            req.full_url, 401, "unauth", hdrs=None, fp=None,
        )

    _install_urlopen(monkeypatch, _raise)
    task, err = api_client.fetch_task("http://x", "t")
    assert task is None
    assert err == api_client.API_AUTH_FAILED


def test_fetch_task_server_error(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.HTTPError(
            req.full_url, 503, "down", hdrs=None, fp=None,
        )

    _install_urlopen(monkeypatch, _raise)
    task, err = api_client.fetch_task("http://x", "t")
    assert err == api_client.API_SERVER_ERROR


def test_fetch_task_unreachable(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.URLError("connection refused")

    _install_urlopen(monkeypatch, _raise)
    task, err = api_client.fetch_task("http://x", "t")
    assert err == api_client.API_UNREACHABLE


def test_fetch_task_empty_url():
    from agent import api_client
    task, err = api_client.fetch_task("", "tok")
    assert err == api_client.API_BAD_RESPONSE


def test_fetch_task_skips_auth_header_without_token(monkeypatch):
    from agent import api_client
    cap = _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b"{}"))
    api_client.fetch_task("http://x", "")
    assert "authorization" not in cap["calls"][0]["headers"]


# ──────────────────────────────────────────────────────────────────
# report_result
# ──────────────────────────────────────────────────────────────────
def test_report_result_success(monkeypatch):
    from agent import api_client
    cap = _install_urlopen(monkeypatch, lambda req: _FakeResp(200, b'{"stored": true}'))
    err = api_client.report_result(
        "http://x", "tok", {"id": "t-1", "ok": True, "data": {"v": 1}},
    )
    assert err is None
    call = cap["calls"][0]
    assert call["url"] == "http://x/tasks/result"
    assert call["method"] == "POST"
    assert call["headers"]["authorization"] == "Bearer tok"
    assert call["headers"]["content-type"] == "application/json"
    body = json.loads(call["data"].decode("utf-8"))
    assert body["id"] == "t-1"
    assert body["ok"] is True


def test_report_result_auth_failed(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.HTTPError(
            req.full_url, 403, "forbidden", hdrs=None, fp=None,
        )

    _install_urlopen(monkeypatch, _raise)
    err = api_client.report_result("http://x", "tok", {"id": "t"})
    assert err == api_client.API_AUTH_FAILED


def test_report_result_server_error(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.HTTPError(req.full_url, 500, "oops", hdrs=None, fp=None)

    _install_urlopen(monkeypatch, _raise)
    err = api_client.report_result("http://x", "tok", {"id": "t"})
    assert err == api_client.API_SERVER_ERROR


def test_report_result_unreachable(monkeypatch):
    from agent import api_client

    def _raise(req):
        raise urllib_error.URLError("no route")

    _install_urlopen(monkeypatch, _raise)
    err = api_client.report_result("http://x", "tok", {"id": "t"})
    assert err == api_client.API_UNREACHABLE


def test_report_result_empty_url():
    from agent import api_client
    err = api_client.report_result("", "tok", {"id": "t"})
    assert err == api_client.API_BAD_RESPONSE


def test_report_result_unserializable_body(monkeypatch):
    from agent import api_client

    class _NotJsonable:
        pass

    # default=str 가 강제로 str 화 해주므로 실패하지 않는 편이지만,
    # 재귀 참조는 default=str 로도 통과하지 못한다.
    bad = {}
    bad["self"] = bad  # 순환 참조

    err = api_client.report_result("http://x", "t", bad)
    assert err == api_client.API_BAD_RESPONSE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
