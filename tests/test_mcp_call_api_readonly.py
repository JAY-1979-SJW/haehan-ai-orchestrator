"""call_api_readonly — call_api 의 GET 전용 안전 모드 (2026-10-08).

AI 콘솔 전용 에이전트(SAFE_DEFAULT_ALLOWED)는 call_api(등록된 메서드로 POST 도 가능) 대신
이 도구를 기본으로 쓴다. 메일함(mailbox.*) 조회는 되고, 발송·초안 작성·동기화 같은 POST
endpoint 는 호출 전에 거부돼야 한다(명시적으로 call_api 를 allowed_tools 에 넣어야만 가능).
"""

from __future__ import annotations

from ai_orchestrator import mcp_server
from ai_orchestrator import mcp_tool_names as names


class _Resp:
    ok = True
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True}


def test_get_endpoint_passes_through(monkeypatch):
    seen = {}

    def fake(method, url, params=None, json=None, timeout=None):
        seen.update(method=method, url=url, params=params)
        return _Resp()

    monkeypatch.setattr(mcp_server.requests, "request", fake)
    res = mcp_server._api_call_readonly("mailbox.list", query={"account": "a", "folder": "INBOX"})
    assert res["ok"] is True
    assert seen["method"] == "GET"
    assert seen["url"].endswith("/api/v1/naver-mailbox/messages")


def test_post_endpoint_rejected_before_any_request(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_server.requests, "request", lambda *a, **k: calls.append((a, k)))
    res = mcp_server._api_call_readonly("mailbox.draft")
    assert res["ok"] is False
    assert "GET" in res["error"]
    assert calls == []  # 서버로 요청 자체가 나가지 않는다


def test_mail_send_and_compose_rejected(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_server.requests, "request", lambda *a, **k: calls.append((a, k)))
    for endpoint in ("mail.send", "mail.compose"):
        res = mcp_server._api_call_readonly(endpoint)
        assert res["ok"] is False, endpoint
    assert calls == []


def test_unknown_endpoint_still_reports_allowlist_error(monkeypatch):
    monkeypatch.setattr(
        mcp_server.requests, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no request"))
    )
    res = mcp_server._api_call_readonly("does.not.exist")
    assert res["ok"] is False
    assert "허용되지 않은" in res["error"]


def test_all_get_registered_endpoints_pass_method_check(monkeypatch):
    """등록된 모든 GET endpoint 가 call_api_readonly 의 메서드 검사를 통과하는지(회귀 방지) —
    실제 요청은 모두 가짜 응답으로 막는다."""
    monkeypatch.setattr(mcp_server.requests, "request", lambda *a, **k: _Resp())
    for key, spec in mcp_server.API_REGISTRY.items():
        if spec["method"] != "GET":
            continue
        path_params = dict.fromkeys(_path_placeholders(spec["path"]), "x")
        res = mcp_server._api_call_readonly(key, path_params=path_params)
        assert res["ok"] is True, (key, res)


def test_all_non_get_registered_endpoints_are_blocked(monkeypatch):
    monkeypatch.setattr(
        mcp_server.requests, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no request"))
    )
    blocked = [k for k, spec in mcp_server.API_REGISTRY.items() if spec["method"] != "GET"]
    assert blocked  # 쓰기 endpoint 가 실제로 존재한다(이 시험이 공허하지 않음)
    for key in blocked:
        res = mcp_server._api_call_readonly(key)
        assert res["ok"] is False, key


def _path_placeholders(path: str) -> list[str]:
    import re

    return re.findall(r"\{(\w+)\}", path)


def test_call_api_readonly_is_in_safe_default_and_call_api_is_not():
    assert "call_api_readonly" in names.SAFE_DEFAULT_ALLOWED
    assert "call_api" not in names.SAFE_DEFAULT_ALLOWED
    assert "call_api" in names.DEFAULT_ALLOWED  # 명시적 allowed_tools 로는 여전히 쓸 수 있다
