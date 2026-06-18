"""tool_registry — AI 도구 단일 출처 레지스트리 검증.

도메인별로 중복돼 있던 _to_gpt_tools_* 변환기를 일원화한 모듈.
"""

from __future__ import annotations

import importlib


def _load_domains():
    importlib.import_module("ai_orchestrator.connectors.naver_cafe_router")
    importlib.import_module("ai_orchestrator.connectors.naver_blog_router")
    importlib.import_module("ai_orchestrator.connectors.smartstore.chat")
    from ai_orchestrator.connectors import tool_registry as TR

    return TR


def test_to_openai_tools_format_and_write_gate():
    from ai_orchestrator.connectors.tool_registry import to_openai_tools

    defs = [
        {"name": "read_x", "description": "읽기", "params": {"a": {"type": "string"}}, "required": ["a"]},
        {"name": "write_x", "description": "발행", "params": {}},
    ]
    write = {"write_x"}
    unconf = {t["function"]["name"] for t in to_openai_tools(defs, write, confirmed=False)}
    conf = {t["function"]["name"] for t in to_openai_tools(defs, write, confirmed=True)}
    assert unconf == {"read_x"}  # write 도구는 미승인 시 제외(승인 게이트)
    assert conf == {"read_x", "write_x"}

    spec = next(t for t in to_openai_tools(defs, write, confirmed=True) if t["function"]["name"] == "read_x")
    assert spec["type"] == "function"
    assert spec["function"]["parameters"]["type"] == "object"
    assert spec["function"]["parameters"]["required"] == ["a"]


def test_domains_registered():
    TR = _load_domains()
    assert {"cafe", "blog", "smartstore"} <= set(TR.domains())
    inv = TR.all_tools()
    assert len(inv["cafe"]) >= 1
    assert len(inv["smartstore"]) >= 5  # 스마트스토어는 도구가 많다


def test_openai_tools_for_unknown_domain_is_empty():
    from ai_orchestrator.connectors.tool_registry import openai_tools_for

    assert openai_tools_for("nonexistent-domain") == []
