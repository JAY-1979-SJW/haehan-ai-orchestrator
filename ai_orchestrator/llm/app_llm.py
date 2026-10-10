"""앱 런타임 AI 없음 — AI 는 Claude Code 가 MCP 로 수행 (2026-09-24 OpenAI 삭제).

아키텍처 경계(중요):
  • 앱(단독앱·FastAPI 서버·웹·데스크톱 런타임)은 더 이상 유료 AI API를 호출하지 않는다.
  • 판단·글쓰기·에이전트 작업은 Claude Code 가 MCP(``ai_orchestrator/server/mcp_server.py``,
    `.mcp.json` 의 ``haehan-orchestrator``)로 앱에 붙어서 수행한다.
  • 앱은 도구·데이터만 제공한다(``list_api_endpoints``/``call_api`` 등).
  • 경계 강제: ``tests/server_core/test_app_llm_boundary.py`` 가 경계 밖의 Anthropic 직접호출을 차단한다.

레이어: L1 공유 계약 — 순수 상수, 외부 의존 0.
"""

from __future__ import annotations

# 앱 LLM 공급자 — 앱 런타임 AI 없음(Claude Code/MCP가 앱 밖에서 수행).
APP_LLM_PROVIDER = "none"

__all__ = ("APP_LLM_PROVIDER",)
