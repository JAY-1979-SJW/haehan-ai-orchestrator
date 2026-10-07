"""tool_registry — AI 도구 포맷 변환 유틸 검증.

2026-09-24: 도메인별 GPT 채팅 루프(cafe/blog/smartstore/agent)가 삭제되면서
그 도구들을 등록하던 register()/register_openai() 호출도 함께 삭제되었다.
이 테스트는 tool_registry 자체(포맷 변환 로직)만 검증한다 — 유료 AI 호출 없음.
"""

from __future__ import annotations


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


def test_openai_tools_for_unknown_domain_is_empty():
    from ai_orchestrator.connectors.tool_registry import openai_tools_for

    assert openai_tools_for("nonexistent-domain") == []


def test_register_openai_normalizes_format():
    from ai_orchestrator.connectors.tool_registry import all_tools, register_openai

    register_openai(
        "_t_norm",
        [
            {
                "type": "function",
                "function": {
                    "name": "foo",
                    "description": "d",
                    "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            }
        ],
    )
    spec = all_tools()["_t_norm"][0]
    assert spec["name"] == "foo"
    assert spec["params"] == {"x": {"type": "string"}}
    assert spec["required"] == ["x"]
