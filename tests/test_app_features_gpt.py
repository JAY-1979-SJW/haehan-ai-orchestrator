"""APP_FEATURES_GPT — 앱에 연결된 모든 AI 기능이 GPT(OpenAI)를 쓰는지 검증.

원칙: 터미널 사용은 Claude Code(별개), **앱에 연결된 모든 기능은 GPT**.
대상: AIResponder(블로그 작성/댓글/SEO·스마트스토어), 리뷰 자동답변, 상세설명 도구.
"""

from __future__ import annotations

import importlib

# ── 1) AIResponder 기본 provider = openai (블로그·스마트스토어 공용) ──


def test_ai_responder_defaults_to_openai():
    m = importlib.import_module("scripts.naver.automation.integration.ai_responder")
    r = m.AIResponder()  # 인자 없이 = 앱 기본
    assert r.provider == "openai"
    assert r.model.startswith("gpt")
    assert "openai.com" in r.endpoint
    assert "anthropic" not in r.endpoint


def test_ai_responder_anthropic_still_opt_in():
    # dual-provider 능력은 유지(명시 지정 시에만 anthropic)
    m = importlib.import_module("scripts.naver.automation.integration.ai_responder")
    r = m.AIResponder(provider="anthropic")
    assert r.provider == "anthropic"


# ── 2) 리뷰 자동답변 = GPT (Anthropic 상수 제거) ─────────────────


def test_review_reply_uses_gpt():
    m = importlib.import_module("scripts.naver.smartstore.product.review_reply")
    assert m._GPT_MODEL.startswith("gpt")
    # 구 Anthropic 상수가 남아있지 않아야 한다
    assert not hasattr(m, "_CLAUDE_API")
    assert not hasattr(m, "_CLAUDE_MODEL")


# ── 3) 상세설명 생성 도구 = GPT writer 전용 ──────────────────────


def test_generate_description_tool_routes_to_gpt(monkeypatch):
    chat = importlib.import_module("ai_orchestrator.connectors.smartstore.chat")
    captured = {}

    class _FakeGptWriter:
        def __init__(self, model=None):
            captured["model"] = model

        def generate(self, data, images=None):
            captured["called"] = True
            return {"ok": True, "html": "<div>ok</div>"}

    # GPT writer 가 호출되는지 — Claude writer 는 import 조차 안 돼야 함
    import scripts.naver.smartstore.product.gpt_description_writer as gw

    monkeypatch.setattr(gw, "GptDescriptionWriter", _FakeGptWriter)

    def _boom(*a, **k):
        raise AssertionError("Claude AIDescriptionWriter 가 호출되면 안 됨")

    import scripts.naver.smartstore.product.ai_description_writer as aw

    monkeypatch.setattr(aw, "AIDescriptionWriter", _boom)

    out = chat._run_tool("generate_description", {"data": {"name": "테스트"}}, None, None)
    assert captured.get("called") is True
    assert out.get("ok") is True
