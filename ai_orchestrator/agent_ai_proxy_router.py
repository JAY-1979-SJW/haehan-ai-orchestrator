"""POST /api/v1/agent-ai/chat — 데스크앱 server proxy 모드 AI 채팅.

흐름:
  데스크앱 → 본 endpoint (agent_id + device_token 인증) → openai_proxy_caller →
  OpenAI API → 응답 → 데스크앱

policy:
  - device_token 원문 로그 0 (인증만 사용, 즉시 폐기)
  - OPENAI_API_KEY 는 서버 env (이 모듈은 호출만, 직접 보유 0)
  - raw chat 본문 / 응답 전문 디스크 저장 0 (메모리 처리만)
  - in-memory rate limit per agent
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import local_agent_registry as _reg
from . import openai_proxy_caller as _caller

# Web UI Basic Auth 우회용 자격증명 (환경변수 또는 기본값)
_WEB_UI_USER = os.environ.get("NEXT_PUBLIC_API_USER", "owner")
_WEB_UI_PASS = os.environ.get("NEXT_PUBLIC_API_PASS", "haehan2024!")

logger = logging.getLogger("haehan_agent_ai_proxy")


agent_ai_proxy_router = APIRouter(prefix="/agent-ai", tags=["agent-ai"])

MAX_MESSAGE_LEN = 8000
PREVIEW_CAP = 80
RATE_LIMIT_PER_MIN = 30  # per agent


# ── in-memory rate limit ─────────────────────────────────────


@dataclass
class _AgentRate:
    last_minute_start: float = 0.0
    count: int = 0


_rate_buckets: dict[str, _AgentRate] = {}
_rate_lock = Lock()


def _check_rate_limit(agent_id: str) -> bool:
    """True if allowed."""
    now = time.time()
    with _rate_lock:
        b = _rate_buckets.get(agent_id)
        if b is None or (now - b.last_minute_start) >= 60.0:
            _rate_buckets[agent_id] = _AgentRate(last_minute_start=now, count=1)
            return True
        if b.count >= RATE_LIMIT_PER_MIN:
            return False
        b.count += 1
        return True


def _reset_rate_limit_for(agent_id: str) -> None:
    """테스트 helper — agent 별 bucket 초기화."""
    with _rate_lock:
        _rate_buckets.pop(agent_id, None)


# ── 인증 ─────────────────────────────────────────────────────


def _authenticate(agent_id: str | None, authorization: str | None, x_device_token: str | None) -> str:
    """헤더에서 토큰 추출 + 검증. 성공 시 agent_id 반환, 실패 시 HTTPException.

    token 변수는 함수 scope 안에서만, 로그에 직접 출력 안 함.
    """
    if not agent_id:
        raise HTTPException(status_code=401, detail={"code": "AGENT_ID_MISSING", "message": "X-Agent-Id 헤더 필요"})

    # Web UI Basic Auth 우회 — agent_id="web-ui" + Basic owner:pass
    if agent_id == "web-ui" and authorization:
        try:
            scheme, encoded = authorization.strip().split(" ", 1)
            if scheme.lower() == "basic":
                decoded = base64.b64decode(encoded).decode("utf-8")
                uname, pwd = decoded.split(":", 1)
                if uname == _WEB_UI_USER and pwd == _WEB_UI_PASS:
                    return "web-ui"
        except Exception:  # noqa: S110 — 헤더 파싱 실패는 무시하고 다음 인증 경로로
            pass

    # 데스크톱 self-contained(owner) 모드: AUTH_ENABLED=false면 web-ui 비번 검증 우회.
    # (앱이 곧 owner — require_role 등과 동일 정책. NEXT_PUBLIC_API_PASS↔API_PASS env
    #  불일치로 데스크앱 AI 비서가 401 나는 문제 해결. 서버는 AUTH_ENABLED=true라 영향 없음.)
    if agent_id == "web-ui":
        try:
            from ai_orchestrator import config as _cfg

            if not getattr(_cfg, "AUTH_ENABLED", True):
                return "web-ui"
        except Exception:  # noqa: S110 — config 미가용 시 우회 안 하고 다음 경로로
            pass

    token = ""
    if authorization:
        a = authorization.strip()
        if a.lower().startswith("bearer "):
            token = a[7:].strip()
    if not token and x_device_token:
        token = x_device_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "device_token 필요"})
    try:
        agent = _reg.authenticate_agent(agent_id, token)
    finally:
        token = ""  # 폐기
    if agent is None:
        raise HTTPException(
            status_code=401, detail={"code": "AUTH_FAILED", "message": "agent_id 또는 device_token 거부"}
        )
    return agent.agent_id


# ── schemas ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LEN)
    session_id: str | None = None
    client_mode: str = "SERVER_PROXY"
    model: str | None = None


class ChatResponse(BaseModel):
    ok: bool
    text: str = ""
    error_code: str = ""
    user_message_kr: str = ""
    model: str = ""
    usage_summary: dict = Field(default_factory=dict)
    external_call_count: int = 0
    duration_ms: int = 0


# 한글 오류 안내
_USER_MSG = {
    "API_KEY_NOT_SET": "서버에 OpenAI API key 가 설정되지 않았습니다. 관리자에게 문의하세요.",
    "API_KEY_INVALID": "서버 API key 가 거부되었습니다. 관리자에게 문의하세요.",
    "API_QUOTA_EXCEEDED": "OpenAI 할당량이 초과되었습니다. 잠시 후 다시 시도하세요.",
    "RATE_LIMITED": "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
    "NETWORK_ERROR": "네트워크 오류가 발생했습니다.",
    "MODEL_NOT_AVAILABLE": "선택된 모델을 사용할 수 없습니다.",
    "REQUEST_TIMEOUT": "요청 시간이 초과되었습니다.",
    "PROVIDER_ERROR": "OpenAI 서비스 응답 오류.",
    "RESPONSE_EMPTY": "응답이 비어 있습니다.",
    "EMPTY_OR_TOO_LONG": "메시지가 비어 있거나 너무 깁니다.",
    "RATE_LIMITED_AGENT": "이 에이전트의 요청 한도(분당)를 초과했습니다.",
}


# ── 총괄 라우팅: 브라우저 작업 위임 ──────────────────────────────
# 메시지가 '웹사이트에서 직접 하는 작업'이면 로컬 CDP 브라우저 에이전트로 실행한다.
# (데스크톱 = 로컬 CDP 있음 / 서버 = CDP 없어 자동 폴백 → 일반 챗)

_TASK_HINT = re.compile(
    r"https?://|\.com|\.kr|사이트|로그인|들어가|접속|조회|정리해|수집|크롤|페이지에서|"
    r"클릭|입력|주문|상품|단말기|연락처|목록|스크랩|추출해|가져와|확인해",
    re.IGNORECASE,
)


def _maybe_run_browser_task(message: str, model: str | None) -> str | None:
    """메시지가 브라우저 작업이면 에이전트 실행 후 결과 텍스트, 아니면 None(→ 일반 챗)."""
    if not _TASK_HINT.search(message):
        return None
    # 1) LLM 의도 분류 + URL/지시 추출
    classify = _caller.call_openai_chat(
        message=(
            "다음 사용자 메시지가 '웹사이트에서 직접 수행하는 브라우저 작업'(로그인·조회·정리·수집·"
            "클릭·입력 등 브라우저 조작)인지 판단해 JSON만 출력(설명 금지).\n"
            '{"is_task": true/false, "url": "시작 URL 또는 빈문자열", "instruction": "수행할 작업 한 줄"}\n'
            "단순 질문·대화·조언·정보검색이면 is_task=false.\n\n"
            f"메시지: {message[:500]}"
        ),
        model=model,
    )
    if not classify.ok:
        return None
    m = re.search(r"\{.*\}", classify.text, re.S)
    if not m:
        return None
    try:
        task = json.loads(m.group(0))
    except Exception:
        return None
    if not task.get("is_task"):
        return None
    # 2) 로컬 브라우저 에이전트 실행
    try:
        from scripts.browser_agent.agent import run_browser_task
        from scripts.web_connector import get_page

        page = get_page()
        r = run_browser_task(
            page,
            instruction=task.get("instruction") or message,
            start_url=(task.get("url") or "").strip() or None,
            max_steps=12,
        )
    except Exception:
        return None  # CDP 없음(서버 등) → 일반 챗 폴백
    if r.get("needs_login"):
        return f"🔐 로그인이 필요합니다.\n{r.get('result', '')}\n로그인하신 뒤 다시 같은 명령을 주세요."
    if r.get("blocked"):
        return f"⛔ 위험 동작이라 멈췄습니다.\n{r.get('result', '')}\n직접 승인이 필요합니다."
    return f"✅ 작업 결과\n{r.get('result', '')}"


# ── endpoints ────────────────────────────────────────────────


@agent_ai_proxy_router.get("/health")
def agent_ai_health(
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> dict:
    """짧은 health check. agent 인증 + OPENAI_API_KEY 존재 boolean.

    OpenAI 호출은 안 함 (비용 0). API key 존재 boolean 만 반환.
    """
    _authenticate(x_agent_id, authorization, x_device_token)
    return {
        "ok": True,
        "openai_key_configured": _caller.has_server_openai_key(),
        "model": _caller.get_default_model(),
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
    }


@agent_ai_proxy_router.post("/chat", response_model=ChatResponse)
def agent_ai_chat(
    body: ChatRequest,
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> ChatResponse:
    """server proxy chat — OpenAI key 는 서버 env 만 사용."""
    agent_id = _authenticate(x_agent_id, authorization, x_device_token)

    # rate limit
    if not _check_rate_limit(agent_id):
        # raw chat history 디스크 저장 0 — 메타만 로그
        logger.info("rate_limit_exceeded agent=%s", _mask_agent_id(agent_id))
        return ChatResponse(
            ok=False,
            error_code="RATE_LIMITED_AGENT",
            user_message_kr=_USER_MSG["RATE_LIMITED_AGENT"],
        )

    # validate
    msg = (body.message or "").strip()
    if not msg:
        return ChatResponse(ok=False, error_code="EMPTY_OR_TOO_LONG", user_message_kr=_USER_MSG["EMPTY_OR_TOO_LONG"])
    if len(msg) > MAX_MESSAGE_LEN:
        return ChatResponse(ok=False, error_code="EMPTY_OR_TOO_LONG", user_message_kr=_USER_MSG["EMPTY_OR_TOO_LONG"])

    # ── 총괄 라우팅: 브라우저 작업이면 로컬 에이전트로 실제 실행 ──
    try:
        _browser = _maybe_run_browser_task(msg, body.model)
    except Exception:
        _browser = None
    if _browser is not None:
        logger.info("agent_ai_chat browser-task agent=%s", _mask_agent_id(agent_id))
        return ChatResponse(ok=True, text=_browser, model="browser-agent")

    # OpenAI 호출
    result = _caller.call_openai_chat(message=msg, model=body.model)
    msg = ""  # 원문 폐기

    # 로그 — preview 만, 원문 0
    log_meta = {
        "agent": _mask_agent_id(agent_id),
        "model": result.model_used or _caller.get_default_model(),
        "ok": result.ok,
        "error_code": result.error_code,
        "duration_ms": result.duration_ms,
        "response_length": len(result.text or ""),
        "preview": (result.text or "")[:PREVIEW_CAP] if result.ok else "",
    }
    logger.info("agent_ai_chat %s", log_meta)

    if not result.ok:
        return ChatResponse(
            ok=False,
            error_code=result.error_code,
            user_message_kr=_USER_MSG.get(result.error_code, "AI 응답 오류"),
            model=result.model_used or "",
            duration_ms=result.duration_ms,
        )
    return ChatResponse(
        ok=True,
        text=result.text,
        finish_reason=result.finish_reason if False else "",  # not in schema
        model=result.model_used or _caller.get_default_model(),
        usage_summary=result.usage_summary or {},
        external_call_count=1,
        duration_ms=result.duration_ms,
        user_message_kr="",
    )


def _mask_agent_id(aid: str) -> str:
    if not aid:
        return ""
    if len(aid) <= 7:
        return aid[:2] + "***"
    return f"{aid[:6]}***{aid[-4:]}"


__all__ = (
    "MAX_MESSAGE_LEN",
    "RATE_LIMIT_PER_MIN",
    "ChatRequest",
    "ChatResponse",
    "_reset_rate_limit_for",
    "agent_ai_proxy_router",
)
