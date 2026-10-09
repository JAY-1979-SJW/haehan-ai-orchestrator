"""AI 채팅(UniversalChat) 대화기록 CRUD — L8 Server API.

사용자 지시 '이전 대화기록을 저장해서 볼수 있게 해줘'. 실행 자체(run_claude_agent 큐잉)는
ai_agent_router.py가 담당 — 이 라우터는 세션 목록/조회/생성/메시지 append/삭제만.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tools.gates.auth import require_role

from ..tasks import chat_sessions as store

chat_router = APIRouter(prefix="/chat/sessions", tags=["chat"])

# 지원 모델 별칭 (공식 --model 플래그, code.claude.com/docs/en/cli-reference 확인) —
# 이 목록 밖의 값도 CLI에 그대로 전달은 되지만(전체 모델명일 수 있으므로 서버에서 차단하지
# 않음), 프론트 드롭다운은 이 4개만 노출한다.
SUPPORTED_MODEL_ALIASES = ("sonnet", "opus", "haiku", "fable")


class CreateSessionRequest(BaseModel):
    first_message: str = ""
    model: str = ""


class AddMessageRequest(BaseModel):
    role: str
    text: str
    task_id: str = ""
    claude_session_id: str = ""  # assistant 메시지 완료 시 --resume용 session_id 갱신


@chat_router.get("")
def api_list_sessions(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    return {"ok": True, "sessions": store.list_sessions(), "supported_models": list(SUPPORTED_MODEL_ALIASES)}


@chat_router.post("")
def api_create_session(body: CreateSessionRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    session = store.create_session(first_message=body.first_message, model=body.model.strip())
    return {"ok": True, "session": session.to_detail()}


@chat_router.get("/{chat_id}")
def api_get_session(chat_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    session = store.get_session(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다")
    return {"ok": True, "session": session.to_detail()}


@chat_router.post("/{chat_id}/messages")
def api_add_message(
    chat_id: str, body: AddMessageRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    if body.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role은 user 또는 assistant여야 합니다")
    session = store.add_message(
        chat_id,
        role=body.role,
        text=body.text,
        task_id=body.task_id,
        claude_session_id=body.claude_session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다")
    return {"ok": True, "session": session.to_detail()}


@chat_router.delete("/{chat_id}")
def api_delete_session(chat_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    existed = store.delete_session(chat_id)
    if not existed:
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다")
    return {"ok": True}


__all__ = ["chat_router"]
