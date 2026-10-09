"""AI 에이전트 실행 API (/api/v1/ai-agent/*).

앱 버튼/채팅에서 Claude(MCP)를 실제로 실행시키는 진입점. 2026-09-28 기준서
(docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md)에서 구현·검증된
run_claude_agent 액션(core/agent_runtime/connection/actions.py) + 기존 local_agent_registry 작업 큐를
그대로 재사용한다 — 신규 실행 로직 없음, 신규 큐/프로세스 없음.

이 라우터가 추가하는 건 딱 하나: "어느 로컬 에이전트로 보낼지"를 프런트가 몰라도 되게
자동 선택하는 얇은 편의 계층. 작업 상태 폴링은 기존
GET /api/v1/local-agents/{agent_id}/tasks/{task_id} 를 그대로 쓴다(신규 폴링 엔드포인트 없음).

- POST /run : 등록된 로컬 에이전트 자동 선택(idle 우선) -> run_claude_agent 작업 큐잉
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.contracts import mcp_tool_names as _tool_names
from tools.gates.auth import require_role

from ..agent_hub.registry import facade as _reg
from ..contracts.agent_result_limits import RESULT_FULL_MAX_CHARS
from ..tasks import chat_sessions as _chat_store

ai_agent_router = APIRouter(prefix="/ai-agent", tags=["ai-agent"])

# 이 앱 자신의 MCP 도구(mcp_server.py, 설계문서 §5.3) — run_claude_agent가 기본으로 허용할
# 화이트리스트. --allowedTools 없이는 claude -p 헤드리스에서 MCP 도구 호출이 전부 거부되므로
# (설계문서 §5.1 실측 확인) 앱을 실제로 조작하려면 이 목록이 필요하다.
# 이름 정의는 mcp_tool_names.py 한 곳(삭제/설정 변경 도구는 제외 — 그 파일 RESTRICTED 참고).
_DEFAULT_ALLOWED_TOOLS = _tool_names.qualified(_tool_names.DEFAULT_ALLOWED)


CHAT_RESULT_MAX_CHARS = RESULT_FULL_MAX_CHARS  # result_full 상한(정본: contracts/agent_result_limits.py)


class RunAgentRequest(BaseModel):
    prompt: str
    allowed_tools: list[str] | None = None  # None이면 기본 화이트리스트 사용
    timeout: int = 300
    max_budget_usd: float = 2.0
    chat_id: str = ""  # 주어지면 그 세션의 claude_session_id로 --resume(대화 이어가기, 속도 개선)
    model: str = ""  # 공식 --model 그대로 전달("sonnet"/"opus"/"haiku"/"fable" 또는 전체 모델명)
    # 결과 전문 길이. 서버 결과 필터가 result 를 500자로 자르므로 result_full 로 받는다.
    # 기본값은 대화기록 저장 상한(chat_sessions._MAX_MESSAGE_TEXT_LEN)과 같게 맞춘다.
    result_max_chars: int = CHAT_RESULT_MAX_CHARS


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

    agent = _reg.select_agent(_reg.list_agents())
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail=("연결된 로컬 에이전트가 없습니다. python -m core.agent_runtime.agent --run 이 실행 중인지 확인하세요."),
        )
    agent_id = agent["agent_id"]

    allowed_tools = body.allowed_tools if body.allowed_tools is not None else _DEFAULT_ALLOWED_TOOLS
    timeout = max(30, min(1800, body.timeout))
    max_budget = max(0.1, min(20.0, body.max_budget_usd))

    params: dict = {
        "prompt": prompt,
        "allowed_tools": allowed_tools,
        "timeout": timeout,
        "max_budget_usd": max_budget,
        "result_max_chars": max(0, min(20000, body.result_max_chars)),
    }
    if body.model.strip():
        params["model"] = body.model.strip()
    if body.chat_id:
        # 같은 채팅의 이전 대화가 있으면 그 claude_session_id로 이어간다(--resume) —
        # 공식 --system-prompt-snapshot 문서 근거로 콜드 스타트 지연을 줄인다
        # (core/agent_runtime/connection/actions.py::action_run_claude_agent 참고).
        chat_session = _chat_store.get_session(body.chat_id)
        if chat_session and chat_session.claude_session_id:
            params["resume_session_id"] = chat_session.claude_session_id

    try:
        task = _reg.enqueue_task(
            agent_id=agent_id,
            action="run_claude_agent",
            params=params,
            requested_by=user["actor"],
        )
    except _reg.UnknownActionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"ok": True, "agent_id": agent_id, "task_id": task.task_id, "status": task.status}
