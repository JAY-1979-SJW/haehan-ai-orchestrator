# -*- coding: utf-8 -*-
"""AI CAD 채팅 라우터.

POST /api/v1/cad-ai/chat
  - 사용자의 자연어 메시지를 받아 OpenAI로 CAD 액션을 결정
  - 해당 액션을 로컬 에이전트 태스크로 등록
  - AI 응답 + task_id 반환

GET /api/v1/cad-ai/actions
  - 사용 가능한 CAD 액션 목록 반환 (UI에서 활용)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_role
from .config import OPENAI_API_KEY
from . import local_agent_registry as _reg
from .local_agent_registry import UnknownActionError

logger = logging.getLogger(__name__)

cad_ai_router = APIRouter(prefix="/cad-ai", tags=["cad-ai"])

# ── CAD 액션 카탈로그 ──────────────────────────────────────────────────────────

CAD_ACTIONS: list[dict[str, Any]] = [
    {
        "name": "detect_cad_apps",
        "label": "AutoCAD 감지",
        "description": "현재 실행 중인 AutoCAD 프로세스를 모두 찾습니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "check_cad_app_status",
        "label": "CAD 상태 확인",
        "description": "AutoCAD 앱이 열려 있는지 확인합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "search_drawings",
        "label": "도면 검색",
        "description": "열려 있는 도면 파일 목록을 찾습니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_layers",
        "label": "레이어 목록",
        "description": "현재 도면의 전체 레이어 목록과 색상을 조회합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_blocks",
        "label": "블록 목록",
        "description": "도면에 삽입된 블록 참조(INSERT) 목록을 가져옵니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_entities",
        "label": "엔티티 통계",
        "description": "도면 내 엔티티 유형별 개수를 집계합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_texts",
        "label": "텍스트 조회",
        "description": "도면 내 모든 TEXT/MTEXT 내용을 읽어옵니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_geometry",
        "label": "선/원 조회",
        "description": "LINE·ARC·CIRCLE 좌표와 길이를 조회합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_dimensions",
        "label": "치수 목록",
        "description": "도면 내 치수(DIMENSION) 엔티티를 조회합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "read_modelspace",
        "label": "모델스페이스 요약",
        "description": "모델스페이스 전체 구조를 요약합니다",
        "params": {},
        "risk": "low",
    },
    {
        "name": "cad_inventory_collect",
        "label": "인벤토리 수집",
        "description": "레이어·블록·텍스트·엔티티를 한 번에 수집합니다",
        "params": {},
        "risk": "medium",
    },
]

_CATALOG_TEXT = "\n".join(
    f'- {a["name"]}: {a["description"]}' for a in CAD_ACTIONS
)

_SYSTEM_PROMPT = f"""당신은 AutoCAD 도면 분석 AI 직원입니다.
사용자의 자연어 요청을 분석해서 아래 CAD 액션 중 하나를 선택하고 실행 계획을 세웁니다.

사용 가능한 CAD 액션:
{_CATALOG_TEXT}

응답은 반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 포함하지 마세요.
{{
  "reply": "사용자에게 보낼 한국어 설명 (1-2문장, 어떤 작업을 실행하는지 설명)",
  "action": "액션_이름",
  "params": {{}},
  "confidence": 0.95
}}

도면 분석에 해당하지 않거나 위 목록에 없는 요청이면:
{{
  "reply": "해당 요청은 현재 지원하지 않습니다. 도면 레이어, 블록, 텍스트, 엔티티 조회 등을 요청해주세요.",
  "action": null,
  "params": null,
  "confidence": 0
}}"""


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────

class CadChatRequest(BaseModel):
    agent_id: str
    message: str
    conversation: list[dict] = []


class CadChatResponse(BaseModel):
    reply: str
    action: Optional[str] = None
    params: Optional[dict] = None
    task_id: Optional[str] = None
    task_status: Optional[str] = None
    confidence: float = 0.0
    ai_used: bool = False


# ── OpenAI 호출 ───────────────────────────────────────────────────────────────

def _call_openai(message: str, conversation: list[dict]) -> dict:
    """OpenAI로 사용자 메시지를 분석해 CAD 액션 결정."""
    if not OPENAI_API_KEY.strip():
        # MOCK 모드 — 키워드 기반 fallback
        return _keyword_fallback(message)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        # 최근 대화 이력 (최대 6턴)
        for turn in conversation[-6:]:
            if turn.get("role") in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": str(turn.get("content", ""))})
        messages.append({"role": "user", "content": message})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0.2,
            timeout=15,
        )
        raw = resp.choices[0].message.content.strip()
        # JSON 파싱
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # JSON 블록 추출 시도
            import re
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group())
            raise
    except Exception as e:
        logger.warning("OpenAI 호출 실패: %s — fallback 사용", e)
        return _keyword_fallback(message)


def _keyword_fallback(message: str) -> dict:
    """OpenAI 없을 때 키워드 기반으로 액션 결정 (MOCK 모드)."""
    msg = message.lower()
    mapping = [
        (["레이어", "layer"],           "read_layers",     "레이어 목록을 조회합니다."),
        (["블록", "block"],             "read_blocks",     "블록 목록을 조회합니다."),
        (["텍스트", "문자", "text"],     "read_texts",      "텍스트 내용을 조회합니다."),
        (["치수", "dimension"],         "read_dimensions", "치수 목록을 조회합니다."),
        (["선", "원", "geometry"],      "read_geometry",   "선·원 좌표를 조회합니다."),
        (["엔티티", "entity", "통계"],  "read_entities",   "엔티티 통계를 집계합니다."),
        (["모델스페이스", "modelspace"], "read_modelspace", "모델스페이스를 요약합니다."),
        (["도면", "파일", "drawing"],   "search_drawings", "도면 파일을 검색합니다."),
        (["감지", "autocad", "열린"],   "detect_cad_apps", "AutoCAD 프로세스를 감지합니다."),
        (["인벤토리", "수집", "전체"],  "cad_inventory_collect", "전체 인벤토리를 수집합니다."),
    ]
    for keywords, action, reply in mapping:
        if any(k in msg for k in keywords):
            return {"reply": f"[MOCK] {reply}", "action": action, "params": {}, "confidence": 0.7}
    return {
        "reply": "[MOCK] 요청을 이해하지 못했습니다. 도면 레이어, 블록, 텍스트 조회 등을 요청해주세요.",
        "action": None, "params": None, "confidence": 0.0,
    }


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@cad_ai_router.get("/actions")
def list_cad_actions(
    _user: dict = Depends(require_role("viewer", "operator", "admin", "owner")),
) -> dict:
    """사용 가능한 CAD 액션 목록."""
    return {"actions": CAD_ACTIONS}


@cad_ai_router.post("/chat")
def cad_chat(
    body: CadChatRequest,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> CadChatResponse:
    """자연어 메시지를 CAD 액션으로 변환하고 로컬 에이전트에 태스크를 등록."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message가 비어있습니다")
    if not body.agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id가 필요합니다")

    # 1. OpenAI로 액션 결정
    ai_result = _call_openai(body.message.strip(), body.conversation)
    ai_used = bool(OPENAI_API_KEY.strip())

    reply = str(ai_result.get("reply", ""))
    action = ai_result.get("action")
    params = ai_result.get("params") or {}
    confidence = float(ai_result.get("confidence", 0.0))

    # 2. 액션이 없으면 AI 응답만 반환
    if not action:
        return CadChatResponse(reply=reply, confidence=confidence, ai_used=ai_used)

    # 3. 태스크 등록
    actor = current_user.get("actor", "ai-cad-chat")
    try:
        task = _reg.enqueue_task(
            agent_id=body.agent_id,
            action=action,
            params=params,
            requested_by=actor,
        )
    except UnknownActionError as e:
        logger.warning("cad_chat: 미등록 액션 %s", action)
        return CadChatResponse(
            reply=f"{reply}\n\n(서버 오류: 액션 '{action}'이 등록되지 않았습니다)",
            action=action,
            confidence=confidence,
            ai_used=ai_used,
        )
    except Exception as e:
        logger.exception("cad_chat: 태스크 등록 실패")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info("cad_chat: task=%s action=%s agent=%s", task.task_id, action, body.agent_id)

    return CadChatResponse(
        reply=reply,
        action=action,
        params=params,
        task_id=task.task_id,
        task_status=task.status,
        confidence=confidence,
        ai_used=ai_used,
    )
