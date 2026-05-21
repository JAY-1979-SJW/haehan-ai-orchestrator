"""AGENT_OPENAI_DIRECT_TEST_CALL_01 — 22+ 테스트."""
from __future__ import annotations

import io
import json
import re
import urllib.error
from pathlib import Path
from unittest import mock

import pytest


# ── 1) module imports + 상수 ──────────────────────────────


def test_module_exports():
    from local_agent import openai_chat_client as occ
    for sym in ("OpenAiDirectTestClient", "OpenAiChatRequest",
                "OpenAiChatResponse", "live_smoke",
                "DEFAULT_MODEL", "DEFAULT_MAX_TOKENS",
                "DEFAULT_TIMEOUT_SEC"):
        assert hasattr(occ, sym), f"missing: {sym}"


def test_error_codes_complete():
    from local_agent import openai_chat_client as occ
    for code in ("API_KEY_NOT_SET", "API_KEY_INVALID",
                 "API_QUOTA_EXCEEDED", "RATE_LIMITED",
                 "NETWORK_ERROR", "MODEL_NOT_AVAILABLE",
                 "REQUEST_TIMEOUT", "PROVIDER_ERROR",
                 "RESPONSE_EMPTY", "KEY_STORE_ERROR"):
        assert hasattr(occ, f"ERR_{code}")


# ── 2) Request/Response schema ───────────────────────────


def test_chat_request_default_fields():
    from local_agent.openai_chat_client import (
        OpenAiChatRequest, DEFAULT_MODEL, DEFAULT_MAX_TOKENS,
    )
    r = OpenAiChatRequest(text="hello")
    assert r.text == "hello"
    assert r.model == DEFAULT_MODEL
    assert r.max_tokens == DEFAULT_MAX_TOKENS


def test_chat_response_defaults():
    from local_agent.openai_chat_client import OpenAiChatResponse
    r = OpenAiChatResponse(ok=False)
    assert r.external_call_count == 0
    assert r.text_redacted == ""


# ── 3) is_configured / fingerprint ───────────────────────


def test_is_configured_false_when_no_key(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "has_dev_key", lambda **kw: False)
    c = occ.OpenAiDirectTestClient()
    assert c.is_configured() is False


def test_is_configured_true_when_key_present(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "has_dev_key", lambda **kw: True)
    c = occ.OpenAiDirectTestClient()
    assert c.is_configured() is True


def test_get_key_fingerprint_returns_string(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "get_key_fingerprint",
                         lambda **kw: "sk-****abcd")
    c = occ.OpenAiDirectTestClient()
    assert c.get_key_fingerprint() == "sk-****abcd"


# ── 4) chat() — key 없으면 API_KEY_NOT_SET ───────────────


def test_chat_returns_key_not_set_when_no_key(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: None)
    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"))
    assert r.ok is False
    assert r.error_code == "API_KEY_NOT_SET"
    assert r.external_call_count == 0


def test_chat_returns_response_empty_for_empty_input(monkeypatch):
    from local_agent import openai_chat_client as occ
    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text=""))
    assert r.ok is False
    assert r.error_code == "RESPONSE_EMPTY"


# ── 5) chat() — HTTP 오류 분류 ──────────────────────────


def _make_http_error(code: int, body: str = ""):
    return urllib.error.HTTPError(
        "https://api.openai.com/v1/chat/completions",
        code, "err", {}, io.BytesIO(body.encode("utf-8")),
    )


def test_chat_401_returns_api_key_invalid(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise _make_http_error(401, '{"error":"invalid api key"}')

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "API_KEY_INVALID"


def test_chat_429_returns_rate_limited(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise _make_http_error(429, "rate limit exceeded")

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "RATE_LIMITED"


def test_chat_429_quota_returns_quota_exceeded(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise _make_http_error(429, '{"error":{"code":"insufficient_quota"}}')

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "API_QUOTA_EXCEEDED"


def test_chat_404_model_returns_model_not_available(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise _make_http_error(404, "model not found")

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "MODEL_NOT_AVAILABLE"


def test_chat_500_returns_provider_error(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise _make_http_error(500, "internal error")

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "PROVIDER_ERROR"


def test_chat_network_url_error(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        raise urllib.error.URLError("name resolution failed")

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "NETWORK_ERROR"


# ── 6) chat() — 성공 응답 파싱 ─────────────────────────


class _FakeResp:
    def __init__(self, data: dict):
        self._body = json.dumps(data).encode("utf-8")
        self.status = 200

    def read(self): return self._body

    def __enter__(self): return self

    def __exit__(self, *a): pass


def test_chat_success_parses_choice(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        return _FakeResp({
            "choices": [{"message": {"content": "안녕"},
                          "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3,
                       "total_tokens": 8},
            "model": "gpt-4o-mini",
        })

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.ok is True
    assert r.text_redacted == "안녕"
    assert r.finish_reason == "stop"
    assert r.external_call_count == 1
    assert c.external_call_count == 1
    assert r.usage_summary["total_tokens"] == 8


def test_chat_success_empty_content_returns_response_empty(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        return _FakeResp({"choices": [{"message": {"content": ""}}]})

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert r.error_code == "RESPONSE_EMPTY"


# ── 7) redaction — echo back 보호 ───────────────────────


def test_chat_response_redacts_echoed_key(monkeypatch):
    from local_agent import openai_chat_client as occ
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "load_dev_key", lambda **kw: "FAKE_KEY_xxxxxxxxxxxxxxxxxxx")

    def fake_open(req, **kw):
        return _FakeResp({
            "choices": [{"message": {"content":
                "your token is sk-abcdef12345678901234567890ZZZZ here"},
                          "finish_reason": "stop"}],
        })

    c = occ.OpenAiDirectTestClient()
    r = c.chat(occ.OpenAiChatRequest(text="hi"), _opener=fake_open)
    assert "sk-abcdef12345678901234567890ZZZZ" not in r.text_redacted


# ── 8) source 정적 검사 ──────────────────────────────────


def test_source_no_chat_history_file_write():
    src = Path("local_agent/openai_chat_client.py").read_text(encoding="utf-8")
    # write mode open 부재
    assert not re.search(r"open\s*\([^)]*['\"][wa]", src)
    assert ".write_text" not in src


def test_source_no_raw_api_key_pattern():
    src = Path("local_agent/openai_chat_client.py").read_text(encoding="utf-8")
    matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", src)
    real = [m for m in matches if "A-Za-z" not in m]
    assert real == []


def test_source_does_not_log_api_key():
    src = Path("local_agent/openai_chat_client.py").read_text(encoding="utf-8")
    # logger.X(...api_key 패턴 부재 (변수 자체 인자 전달)
    bad = re.findall(r"log(?:ger)?\.\w+\([^)]*api_key\b", src)
    assert bad == []


# ── 9) adapter dev mode 분기 ───────────────────────────


def test_adapter_dev_mode_returns_openai_direct_adapter():
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs
    a = adp.make_default_adapter(mode=cs.MODE_DEV_TEST_KEY)
    assert isinstance(a, adp.OpenAiDirectTestAdapter)


def test_adapter_server_proxy_returns_placeholder():
    """직전: SERVER_PROXY → Placeholder. 신: SERVER_PROXY → ServerProxyChatAdapter."""
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs
    a = adp.make_default_adapter(mode=cs.MODE_SERVER_PROXY)
    # 둘 다 허용 (구버전 호환 + 신 구현)
    assert isinstance(a, (adp.PlaceholderAdapter,
                            adp.ServerProxyChatAdapter))


def test_adapter_byok_returns_placeholder():
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs
    a = adp.make_default_adapter(mode=cs.MODE_USER_BYOK)
    assert isinstance(a, adp.PlaceholderAdapter)


def test_adapter_dev_send_returns_key_not_set_when_no_key(monkeypatch):
    from local_agent import ai_chat_adapter as adp
    from local_agent import gui_chat_state as cs
    from local_agent import openai_key_store as ks
    monkeypatch.setattr(ks, "has_dev_key", lambda **kw: False)
    a = adp.make_default_adapter(mode=cs.MODE_DEV_TEST_KEY)
    r = a.send_message(text_raw="hello")
    assert r.ok is False
    assert r.error_code == "API_KEY_NOT_SET"
    assert r.external_call_count == 0


# ── 10) GUI modal handlers ───────────────────────────


def test_gui_modal_has_save_test_delete_handlers():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    for h in ("_on_save", "_on_test", "_on_delete",
              "btn_modal_save", "btn_modal_test", "btn_modal_delete"):
        assert h in src, f"missing: {h}"


def test_gui_modal_buttons_dev_mode_active():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    assert "MODE_DEV_TEST_KEY" in src
    assert "state=\"normal\" if dev_mode" in src


def test_gui_modal_does_not_persist_api_key_to_file():
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    # GUI 자체는 var_key 만 사용, file 쓰기 없음
    # 입력값 폐기 명시
    assert "var_key.set(\"\")" in src


# ── 11) live smoke report ─────────────────────────────


def test_live_smoke_report_schema_if_present():
    p = Path("data/inspection/openai_direct_test_call/live_smoke_report.json")
    if not p.exists():
        pytest.skip("smoke report not present (key 없거나 미실행)")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "result" in d
    res = d["result"]
    assert "ok" in res
    assert "external_call_count" in res
    # 응답 전문 부재 — preview 만
    if "response_preview_redacted" in res:
        assert len(res["response_preview_redacted"]) <= 80
    # raw key 부재
    body_text = json.dumps(d, ensure_ascii=False)
    matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", body_text)
    real = [m for m in matches if "A-Za-z" not in m]
    assert real == []


# ── 12) audit ─────────────────────────────────────────


def test_audit_warn_proxy_deferred():
    from scripts.ops import audit_openai_direct_test_call as a
    v = a.judge_call(desktop_ui_unchanged=True, proxy_implemented=False)
    assert v.code in ("PASS_OPENAI_DIRECT_TEST_CALL",
                       "WARN_PRODUCTION_PROXY_NOT_IMPLEMENTED")


def test_audit_fail_desktop_ui_touched():
    from scripts.ops import audit_openai_direct_test_call as a
    v = a.judge_call(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_TOUCHED"


# ── 13) 회귀 가드 ────────────────────────────────────


def test_regression_openai_key_store_intact():
    from local_agent import openai_key_store as ks
    assert hasattr(ks, "save_dev_key")
    assert hasattr(ks, "load_dev_key")


def test_regression_ai_chat_client_intact():
    from local_agent import ai_chat_client as aic
    assert hasattr(aic, "MockAiChatClient")
    assert hasattr(aic, "redact_input")


def test_regression_gui_state_intact():
    from local_agent import gui_state as gs
    assert hasattr(gs, "GuiController")
