"""AI 채팅 도구 레지스트리 — 도메인별 도구 정의의 단일 출처 + OpenAI 변환.

각 도메인(cafe/blog/smartstore 등)의 도구 정의를 한 곳에서 OpenAI function-calling
포맷으로 변환하고, 중앙 인벤토리로 등록한다. (도메인마다 중복돼 있던
_to_gpt_tools_* 변환기를 일원화 — app_llm 과 같은 '단일 출처' 패턴.)

도구 정의 포맷(도메인 공통):
    {"name": str, "description": str, "params": {prop: jsonschema}, "required": [str]?}

레이어: L1 공유 계약 — 순수 변환/등록, 외부 의존 0.
"""

from __future__ import annotations

from collections.abc import Callable

# 도메인 → {"tool_defs": callable()->list[dict], "write_tools": set[str]}
_REGISTRY: dict[str, dict] = {}


def to_openai_tools(
    tool_defs: list[dict],
    write_tools: set[str] | None = None,
    confirmed: bool = False,
) -> list[dict]:
    """도구 정의 리스트 → OpenAI function-calling 포맷.

    write_tools(발행·결제·삭제 등)는 confirmed=False 면 노출 제외(승인 게이트).
    """
    write = write_tools or set()
    result = []
    for t in tool_defs:
        if not confirmed and t["name"] in write:
            continue
        params: dict = {"type": "object", "properties": t.get("params", {})}
        if "required" in t:
            params["required"] = t["required"]
        result.append(
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": params},
            }
        )
    return result


def register(domain: str, tool_defs: Callable[[], list[dict]], write_tools: set[str] | None = None) -> None:
    """도메인 도구를 중앙 레지스트리에 등록(같은 domain 재등록은 덮어씀)."""
    _REGISTRY[domain] = {"tool_defs": tool_defs, "write_tools": set(write_tools or set())}


def openai_tools_for(domain: str, confirmed: bool = False) -> list[dict]:
    """등록된 도메인의 OpenAI 도구 목록을 바로 반환."""
    info = _REGISTRY.get(domain)
    if not info:
        return []
    return to_openai_tools(info["tool_defs"](), info["write_tools"], confirmed)


def all_tools() -> dict[str, list[dict]]:
    """등록된 전 도메인 도구 인벤토리 — {domain: [tool_def, ...]}."""
    out: dict[str, list[dict]] = {}
    for domain, info in _REGISTRY.items():
        try:
            out[domain] = info["tool_defs"]()
        except Exception:
            out[domain] = []
    return out


def domains() -> list[str]:
    """등록된 도메인 목록."""
    return sorted(_REGISTRY)


__all__ = ("all_tools", "domains", "openai_tools_for", "register", "to_openai_tools")
