"""CHAT_GPT_CONVERSION — 카페·블로그·스마트스토어 채팅이 GPT(OpenAI) 규약을 쓰는지 검증.

배경: 앱은 GPT 설계인데 cafe/blog/smartstore 채팅이 Anthropic Claude로 작성돼
ANTHROPIC_API_KEY 미설정 시 동작하지 않았다. 전부 OpenAI function-calling 으로 전환.
본 테스트는 OpenAI 호출 없이(도구 포맷·진입점·키없음 경로) 전환을 고정한다.
"""

from __future__ import annotations

import importlib

import pytest

CAFE = "ai_orchestrator.connectors.naver_cafe_router"
BLOG = "ai_orchestrator.connectors.naver_blog_router"


def _mod(name):
    return importlib.import_module(name)


# ── 1) GPT 진입점 존재 / Claude 진입점 제거 ──────────────────────


def test_cafe_gpt_entrypoint_replaces_claude():
    m = _mod(CAFE)
    assert hasattr(m, "_run_cafe_gpt")
    assert not hasattr(m, "_run_cafe_claude")  # Claude 경로 제거됨


def test_blog_gpt_entrypoint_replaces_claude():
    m = _mod(BLOG)
    assert hasattr(m, "_run_blog_gpt")
    assert not hasattr(m, "_run_blog_claude")


# ── 2) 도구 정의가 OpenAI function 포맷인지 ──────────────────────


@pytest.mark.parametrize("mod,fn", [(CAFE, "_to_gpt_tools_cafe"), (BLOG, "_to_gpt_tools_blog")])
def test_tools_are_openai_function_format(mod, fn):
    tools = getattr(_mod(mod), fn)(confirmed=True)
    assert tools, "도구가 비어있으면 안 됨"
    for t in tools:
        assert t["type"] == "function"
        f = t["function"]
        assert isinstance(f["name"], str) and f["name"]
        assert "parameters" in f and f["parameters"]["type"] == "object"


# ── 3) 쓰기 도구는 confirmed=False 일 때 노출 안 됨(승인 게이트) ──


def test_cafe_write_tool_hidden_until_confirmed():
    m = _mod(CAFE)
    names_unconf = {t["function"]["name"] for t in m._to_gpt_tools_cafe(False)}
    names_conf = {t["function"]["name"] for t in m._to_gpt_tools_cafe(True)}
    assert "write_cafe_post" not in names_unconf  # 미승인 시 발행도구 숨김
    assert "write_cafe_post" in names_conf


# ── 4) OPENAI_API_KEY 미설정 시 떠넘기지 않고 명확한 에러 ────────


def test_cafe_gpt_errors_without_openai_key(monkeypatch):
    m = _mod(CAFE)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    events = list(m._run_cafe_gpt([{"role": "user", "content": "현황 알려줘"}], False))
    # 첫 이벤트가 error 이고 OPENAI 키를 가리킴(ANTHROPIC 아님)
    assert any("OPENAI_API_KEY" in e for e in events)
    assert not any("ANTHROPIC" in e for e in events)
