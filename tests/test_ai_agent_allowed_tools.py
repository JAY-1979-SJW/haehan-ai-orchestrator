"""AI 에이전트 기본 허용 도구 — 공유 이름 모듈·라우터·MCP 서버 등록 도구의 일치 검사."""

from __future__ import annotations

import asyncio

import pytest

from ai_orchestrator import mcp_tool_names as names
from ai_orchestrator.routers.ai_agent_router import _DEFAULT_ALLOWED_TOOLS


def test_router_uses_shared_names_without_restricted():
    assert _DEFAULT_ALLOWED_TOOLS == names.qualified(names.DEFAULT_ALLOWED)
    assert not set(names.RESTRICTED) & {t.removeprefix(names.MCP_TOOL_PREFIX) for t in _DEFAULT_ALLOWED_TOOLS}


def test_no_duplicate_names_across_groups():
    all_listed = (*names.DEFAULT_ALLOWED, *names.RESTRICTED)
    assert len(all_listed) == len(set(all_listed)) == len(names.ALL_TOOL_NAMES)


def test_registered_mcp_tools_match_shared_names():
    # mcp 패키지 버전이 맞지 않는 환경(서버는 py -3.14)에서는 import 자체가 안 되므로 건너뛴다.
    try:
        from ai_orchestrator import mcp_server

        registered = {t.name for t in asyncio.run(mcp_server.list_tools())}
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"mcp_server import 불가 환경: {exc}")
    assert registered == set(names.ALL_TOOL_NAMES)
