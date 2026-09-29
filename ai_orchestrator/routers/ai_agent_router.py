"""AI 에이전트 실행 API (/api/v1/ai-agent/*).

앱 버튼/채팅에서 Claude(MCP)를 실제로 실행시키는 진입점. 2026-09-28 기준서
(docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md)에서 구현·검증된
run_claude_agent 액션(local_agent/actions.py) + 기존 local_agent_registry 작업 큐를
그대로 재사용한다 — 신규 실행 로직 없음, 신규 큐/프로세스 없음.

이 라우터가 추가하는 건 딱 하나: "어느 로컬 에이전트로 보낼지"를 프런트가 몰라도 되게
자동 선택하는 얇은 편의 계층. 작업 상태 폴링은 기존
GET /api/v1/local-agents/{agent_id}/tasks/{task_id} 를 그대로 쓴다(신규 폴링 엔드포인트 없음).

- POST /run : 등록된 로컬 에이전트 자동 선택(idle 우선) -> run_claude_agent 작업 큐잉
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import local_agent_registry as _reg
from ..gates.auth import require_role

ai_agent_router = APIRouter(prefix="/ai-agent", tags=["ai-agent"])

# 이 앱 자신의 MCP 도구(mcp_server.py, 설계문서 §5.3) — run_claude_agent가 기본으로 허용할
# 화이트리스트. --allowedTools 없이는 claude -p 헤드리스에서 MCP 도구 호출이 전부 거부되므로
# (설계문서 §5.1 실측 확인) 앱을 실제로 조작하려면 이 목록이 필요하다.
_DEFAULT_ALLOWED_TOOLS = [
    "mcp__haehan-orchestrator__list_api_endpoints",
    "mcp__haehan-orchestrator__call_api",
    "mcp__haehan-orchestrator__snapshot_page",
    "mcp__haehan-orchestrator__act_on_page",
    "mcp__haehan-orchestrator__navigate_page",
]


class RunAgentRequest(BaseModel):
    prompt: str
    allowed_tools: list[str] | None = None  # None이면 기본 화이트리스트 사용
    timeout: int = 300
    max_budget_usd: float = 2.0


@ai_agent_router.post("/run")
def run_agent(
    body: RunAgentRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록된 로컬 에이전트 자동 선택 -> run_claude_agent 작업 큐잉.

    결과는 여기서 기다리지 않는다(작업이 몇 초~몇 분 걸릴 수 있음) — task_id를 반환하니
    프런트는 기존 GET /api/v1/local-agents/{agent_id}/tasks/{task_id} 로 폴링한다.
    """
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt가 비어 있습니다")

    agents = _reg.list_agents()
    if not agents:
        raise HTTPException(
            status_code=503,
            detail=("연결된 로컬 에이전트가 없습니다. python -m local_agent.agent --run 이 실행 중인지 확인하세요."),
        )
    # idle 상태 에이전트 우선, 없으면 첫 번째(다른 작업 처리 중이어도 큐에는 쌓임)
    agent = next((a for a in agents if a.get("agent_status") == "idle"), agents[0])
    agent_id = agent["agent_id"]

    allowed_tools = body.allowed_tools if body.allowed_tools is not None else _DEFAULT_ALLOWED_TOOLS
    timeout = max(30, min(1800, body.timeout))
    max_budget = max(0.1, min(20.0, body.max_budget_usd))

    try:
        task = _reg.enqueue_task(
            agent_id=agent_id,
            action="run_claude_agent",
            params={
                "prompt": prompt,
                "allowed_tools": allowed_tools,
                "timeout": timeout,
                "max_budget_usd": max_budget,
            },
            requested_by=user["actor"],
        )
    except _reg.UnknownActionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"ok": True, "agent_id": agent_id, "task_id": task.task_id, "status": task.status}
