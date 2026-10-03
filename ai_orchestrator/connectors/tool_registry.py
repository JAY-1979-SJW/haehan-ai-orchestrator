"""AI 채팅 도구 레지스트리 — 도메인별 도구 정의의 단일 출처 + OpenAI 변환.

각 도메인(cafe/blog/smartstore 등)의 도구 정의를 한 곳에서 OpenAI function-calling
포맷으로 변환하고, 중앙 인벤토리로 등록한다. (도메인마다 중복돼 있던
_to_gpt_tools_* 변환기를 일원화 — app_llm 과 같은 '단일 출처' 패턴.)

도구 정의 포맷(도메인 공통):
    {"name": str, "description": str, "params": {prop: jsonschema}, "required": [str]?}

레이어: L1 공유 계약 — 순수 변환/등록, 외부 의존 0.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

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


def register_openai(domain: str, openai_tools: list[dict]) -> None:
    """이미 OpenAI function 포맷인 도구를 등록(free_agent 등).

    중앙 인벤토리(all_tools) 일관성을 위해 공통 도구정의 포맷으로 정규화해 보관한다.
    """
    normalized: list[dict] = []
    for t in openai_tools:
        fn = t.get("function", {})
        params = fn.get("parameters", {}) or {}
        spec = {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "params": params.get("properties", {}),
        }
        if "required" in params:
            spec["required"] = params["required"]
        normalized.append(spec)
    _REGISTRY[domain] = {"tool_defs": lambda: normalized, "write_tools": set()}


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
        except Exception as exc:  # noqa: BLE001 - 도메인별 tool_defs() 호출 실패 시 해당 도메인만 빈 목록으로 처리 — 다른 도메인 조회에 영향 없는 격리, 실행 권한 부여와 무관한 목록 조회 함수
            logger.warning("도메인 tool_defs 조회 실패: %s", type(exc).__name__)
            out[domain] = []
    return out


def domains() -> list[str]:
    """등록된 도메인 목록."""
    return sorted(_REGISTRY)


__all__ = ("all_tools", "domains", "openai_tools_for", "register", "register_openai", "to_openai_tools")
