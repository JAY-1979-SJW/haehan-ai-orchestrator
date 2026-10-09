"""콘솔 HTTP 계약 — POST /api/v1/ai-agent/run (UniversalChat.tsx:285)과 작업 폴링
GET /api/v1/local-agents/{agent_id}/tasks/{task_id} (UniversalChat.tsx:212).

로컬 에이전트·claude CLI·MCP 는 시험 관례대로 가짜 레지스트리로 대체한다(실행·큐 적재 없음).
확인 항목: 인증 필요 여부(401/403), 정상 응답의 핵심 키, 잘못된 입력의 4xx/503. 동작 변경 없음.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_orchestrator.agent_hub import redaction as redaction
from ai_orchestrator.agent_hub.registry.common import LocalAgentTask
from ai_orchestrator.agent_hub.router import task as task_mod
from ai_orchestrator.contracts import mcp_tool_names as tool_names
from ai_orchestrator.site_work import ai_agent_router as agent_mod
from tests.console_api_contract_support import (
    API,
    basic,
    disable_auth,
    enable_basic_auth,
    make_client,
)

RUN = f"{API}/ai-agent/run"
TASK = f"{API}/local-agents/la-1/tasks"


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def queued(monkeypatch):
    """가짜 레지스트리: 에이전트 1대(idle), 큐 적재는 목록에만 기록한다."""
    calls: list[dict] = []
    fake = SimpleNamespace(
        list_agents=lambda: [{"agent_id": "la-1", "agent_status": "idle"}],
        select_agent=lambda agents: agents[0] if agents else None,
        enqueue_task=lambda **kw: calls.append(kw) or SimpleNamespace(task_id="task-1", status="queued"),
        UnknownActionError=ValueError,
    )
    monkeypatch.setattr(agent_mod, "_reg", fake)
    return calls


def _task(**overrides: Any) -> LocalAgentTask:
    base: dict[str, Any] = {
        "task_id": "task-1",
        "agent_id": "la-1",
        "action": "run_claude_agent",
        "params": {"prompt": "p"},
        "risk_level": "medium",
        "status": "completed",
        "requested_by": "owner",
        "created_at": "2026-10-07T00:00:00Z",
        "updated_at": "2026-10-07T00:00:01Z",
        "result_data": {
            "result": "요약",
            "result_full": "전문",
            "session_id": "sess-1",
        },
    }
    base.update(overrides)
    return LocalAgentTask(**base)


# ── /ai-agent/run: 인증 ──────────────────────────────────────────────────────


def test_run_requires_credentials(client, monkeypatch, tmp_path, queued):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.post(RUN, json={"prompt": "x"}).status_code == 401
    assert queued == []  # 인증 실패 시 큐에 아무것도 넣지 않는다


def test_run_forbidden_for_viewer(client, monkeypatch, tmp_path, queued):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.post(RUN, json={"prompt": "x"}, headers=basic("viewer_u")).status_code == 403
    assert queued == []


@pytest.mark.parametrize("user", ["owner_u", "admin_u"])
def test_run_allowed_for_owner_and_admin(client, monkeypatch, tmp_path, queued, user):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.post(RUN, json={"prompt": "x"}, headers=basic(user)).status_code == 200


# ── /ai-agent/run: 정상 응답 ─────────────────────────────────────────────────


def test_run_response_shape_and_queued_task(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    r = client.post(RUN, json={"prompt": "  상품 목록 보여줘  ", "model": " opus "})
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "agent_id": "la-1",
        "task_id": "task-1",
        "status": "queued",
    }
    call = queued[-1]
    assert call["agent_id"] == "la-1"
    assert call["action"] == "run_claude_agent"
    assert call["params"]["prompt"] == "상품 목록 보여줘"  # 앞뒤 공백 제거
    assert call["params"]["model"] == "opus"
    assert call["params"]["allowed_tools"] == tool_names.qualified(tool_names.DEFAULT_ALLOWED)


def test_run_clamps_timeout_and_budget(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    client.post(RUN, json={"prompt": "x", "timeout": 1, "max_budget_usd": 999})
    assert queued[-1]["params"]["timeout"] == 30
    assert queued[-1]["params"]["max_budget_usd"] == 20.0
    client.post(RUN, json={"prompt": "x", "timeout": 10**6, "max_budget_usd": 0})
    assert queued[-1]["params"]["timeout"] == 1800
    assert queued[-1]["params"]["max_budget_usd"] == 0.1


def test_run_omits_model_when_blank(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    client.post(RUN, json={"prompt": "x", "model": "   "})
    assert "model" not in queued[-1]["params"]


def test_run_passes_explicit_allowed_tools(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    client.post(
        RUN,
        json={
            "prompt": "x",
            "allowed_tools": ["mcp__haehan-orchestrator__list_products"],
        },
    )
    assert queued[-1]["params"]["allowed_tools"] == ["mcp__haehan-orchestrator__list_products"]


def test_run_resumes_claude_session_of_existing_chat(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    monkeypatch.setattr(
        agent_mod,
        "_chat_store",
        SimpleNamespace(get_session=lambda chat_id: SimpleNamespace(claude_session_id="sess-9")),
    )
    client.post(RUN, json={"prompt": "x", "chat_id": "chat-1"})
    assert queued[-1]["params"]["resume_session_id"] == "sess-9"


def test_run_ignores_unknown_chat_id(client, monkeypatch, queued):
    disable_auth(monkeypatch)
    monkeypatch.setattr(agent_mod, "_chat_store", SimpleNamespace(get_session=lambda chat_id: None))
    assert client.post(RUN, json={"prompt": "x", "chat_id": "chat-nope"}).status_code == 200
    assert "resume_session_id" not in queued[-1]["params"]


# ── /ai-agent/run: 잘못된 입력·실패 ──────────────────────────────────────────


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t"])
def test_run_blank_prompt_is_400_and_not_queued(client, monkeypatch, queued, prompt):
    disable_auth(monkeypatch)
    assert client.post(RUN, json={"prompt": prompt}).status_code == 400
    assert queued == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"prompt": 123},
        {"prompt": "x", "timeout": "soon"},
        {"prompt": "x", "allowed_tools": "a"},
    ],
)
def test_run_invalid_body_is_422(client, monkeypatch, queued, body):
    disable_auth(monkeypatch)
    assert client.post(RUN, json=body).status_code == 422
    assert queued == []


def test_run_without_local_agent_is_503_with_guidance(client, monkeypatch):
    # UniversalChat.tsx 는 이 문구로 '로컬 에이전트 없음' 안내를 띄운다 — 문구가 바뀌면 프론트 안내가 깨진다
    disable_auth(monkeypatch)
    fake = SimpleNamespace(
        list_agents=list,
        select_agent=lambda agents: None,
        UnknownActionError=ValueError,
    )
    monkeypatch.setattr(agent_mod, "_reg", fake)
    r = client.post(RUN, json={"prompt": "x"})
    assert r.status_code == 503
    assert "연결된 로컬 에이전트가 없습니다" in r.json()["detail"]


def test_run_unknown_action_is_400(client, monkeypatch):
    disable_auth(monkeypatch)

    class _Unknown(Exception):
        pass

    def _boom(**kw):
        raise _Unknown("미등록 액션: run_claude_agent")

    fake = SimpleNamespace(
        list_agents=lambda: [{"agent_id": "la-1"}],
        select_agent=lambda agents: agents[0],
        enqueue_task=_boom,
        UnknownActionError=_Unknown,
    )
    monkeypatch.setattr(agent_mod, "_reg", fake)
    assert client.post(RUN, json={"prompt": "x"}).status_code == 400


# ── 작업 폴링: GET /local-agents/{agent_id}/tasks/{task_id} ──────────────────


def test_task_poll_requires_credentials(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(f"{TASK}/task-1").status_code == 401


def test_task_poll_allows_viewer_but_run_does_not(client, monkeypatch, tmp_path):
    # 폴링은 admin/owner/viewer, 실행은 admin/owner — 권한이 의도적으로 다르다
    enable_basic_auth(monkeypatch, tmp_path)
    monkeypatch.setattr(task_mod._reg, "get_task", lambda agent_id, task_id: _task())
    assert client.get(f"{TASK}/task-1", headers=basic("viewer_u")).status_code == 200


def test_task_poll_returns_fields_the_console_reads(client, monkeypatch):
    # UniversalChat.tsx:227-245 가 읽는 키: status, result_data.{result_full,result,session_id}, result_summary,
    # failure_reason, error_summary
    disable_auth(monkeypatch)
    monkeypatch.setattr(task_mod._reg, "get_task", lambda agent_id, task_id: _task())
    r = client.get(f"{TASK}/task-1")
    assert r.status_code == 200
    body = r.json()
    assert {
        "task_id",
        "agent_id",
        "status",
        "result_data",
        "result_summary",
        "failure_reason",
        "error_summary",
    } <= set(body)
    assert body["status"] == "completed"
    assert {"result", "result_full", "session_id"} <= set(body["result_data"])


@pytest.mark.parametrize("status", ["failed", "timed_out", "cancelled"])
def test_task_poll_reports_terminal_failure_states(client, monkeypatch, status):
    disable_auth(monkeypatch)
    monkeypatch.setattr(
        task_mod._reg,
        "get_task",
        lambda agent_id, task_id: _task(status=status, result_data=None, failure_reason="사유"),
    )
    body = client.get(f"{TASK}/task-1").json()
    assert body["status"] == status
    assert body["failure_reason"] == "사유"


def test_task_poll_unknown_task_is_404_with_error_code(client, monkeypatch):
    disable_auth(monkeypatch)
    monkeypatch.setattr(task_mod._reg, "get_task", lambda agent_id, task_id: None)
    r = client.get(f"{TASK}/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "TASK_NOT_FOUND"


def test_result_data_filter_keeps_keys_the_console_needs():
    # 에이전트가 올린 result_data 를 서버가 거를 때 콘솔이 읽는 키가 살아남는지(전문·세션 id) — 정본: local_agent_redaction
    kept = redaction._strip_result_data(
        {
            "result": "요약",
            "result_full": "전문",
            "session_id": "sess-1",
            "cost_usd": 0.1,
            "num_turns": 2,
        }
    )
    assert kept is not None
    assert {"result", "result_full", "session_id"} <= set(kept)
