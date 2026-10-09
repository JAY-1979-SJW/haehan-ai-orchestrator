"""AI 에이전트 기본 허용 도구 — 공유 이름 모듈·라우터·MCP 서버 등록 도구의 일치 검사."""

from __future__ import annotations

import asyncio

import pytest

from ai_orchestrator.contracts import mcp_tool_names as names
from ai_orchestrator.site_work.ai_agent_router import _DEFAULT_ALLOWED_TOOLS


def test_router_uses_shared_names_without_restricted():
    assert _DEFAULT_ALLOWED_TOOLS == names.qualified(names.DEFAULT_ALLOWED)
    assert not set(names.RESTRICTED) & {t.removeprefix(names.MCP_TOOL_PREFIX) for t in _DEFAULT_ALLOWED_TOOLS}


def test_no_duplicate_names_across_groups():
    all_listed = (*names.DEFAULT_ALLOWED, *names.RESTRICTED)
    assert len(all_listed) == len(set(all_listed)) == len(names.ALL_TOOL_NAMES)


def test_registered_mcp_tools_match_shared_names():
    # mcp 패키지 버전이 맞지 않는 환경(서버는 py -3.14)에서는 import 자체가 안 되므로 건너뛴다.
    try:
        from ai_orchestrator.server import mcp_server

        registered = {t.name for t in asyncio.run(mcp_server.list_tools())}
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"mcp_server import 불가 환경: {exc}")
    assert registered == set(names.ALL_TOOL_NAMES)


def test_chat_run_requests_full_result_and_limits_match_chat_store():
    """채팅 답변이 서버 필터 500자에서 잘리던 문제(2026-10-02) — /run 이 전문(result_full)을 요청하고 저장 상한과 일치."""
    from ai_orchestrator.site_work import ai_agent_router as router
    from ai_orchestrator.tasks import chat_sessions

    assert router.RunAgentRequest(prompt="x").result_max_chars == router.CHAT_RESULT_MAX_CHARS == 20000
    assert chat_sessions._MAX_MESSAGE_TEXT_LEN == router.CHAT_RESULT_MAX_CHARS


def test_run_endpoint_passes_result_max_chars_to_queued_task(monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.site_work import ai_agent_router as router
    from tools.gates.auth import get_current_user

    queued: list[dict] = []
    fake_reg = SimpleNamespace(
        list_agents=lambda: [{"agent_id": "ag1", "agent_status": "idle"}],
        select_agent=lambda agents: agents[0],
        enqueue_task=lambda **kw: queued.append(kw) or SimpleNamespace(task_id="t1", status="queued"),
        UnknownActionError=ValueError,
    )
    monkeypatch.setattr(router, "_reg", fake_reg)
    app = FastAPI()
    app.include_router(router.ai_agent_router)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "actor": "t"}
    client = TestClient(app)

    assert client.post("/ai-agent/run", json={"prompt": "안녕"}).status_code == 200
    assert queued[-1]["params"]["result_max_chars"] == 20000  # 기본값: 채팅 전문 요청
    client.post("/ai-agent/run", json={"prompt": "안녕", "result_max_chars": 10**9})
    assert queued[-1]["params"]["result_max_chars"] == 20000  # 상한 클램프
    client.post("/ai-agent/run", json={"prompt": "안녕", "result_max_chars": -5})
    assert queued[-1]["params"]["result_max_chars"] == 0  # 음수는 0(= result_full 미요청)
