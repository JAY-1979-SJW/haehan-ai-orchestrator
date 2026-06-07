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
import logging
import os
import re
import time
from dataclasses import dataclass
from threading import Lock, Thread

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


# ── (LEGACY 분리) 옛 분류기 라우팅(_route_app_task/_op_*/_resolve_url 등)은
#    agent_ai_legacy_routing.py 로 이동(현재 미사용). 활성 경로는 _run_free_agent_task(free_agent) 단독.


# ── 비동기 브라우저 작업(job) 저장소 ──────────────────────────────
# 로그인 대기로 채팅을 묶지 않도록, 로그인 필요 시 즉시 안내 후 백그라운드로 재개.
_BROWSER_TASKS: dict[str, dict] = {}
_TASK_LOCK = Lock()


# ── 세션 대화 기억 ──────────────────────────────────────────────────
# 채팅창(session_id)별로 최근 대화(user/assistant)를 보관해 멀티턴을 잇는다.
# AI가 "뭘 할까요?" 묻고 사용자가 답하면, 이전 맥락을 에이전트가 함께 보고 이어 진행.
_SESSIONS: dict[str, list[dict]] = {}
_SESSION_AGENT: dict[str, bool] = {}  # 세션의 직전 턴이 에이전트였는지(연속성 라우팅)
_SESS_LOCK = Lock()
_SESS_MAX_MSGS = 12  # 세션당 메시지 보관 수
_SESS_MAX = 300  # 세션 수 상한


def _session_history(sid: str) -> list[dict]:
    with _SESS_LOCK:
        return list(_SESSIONS.get(sid, []))


def _session_is_agent(sid: str) -> bool:
    with _SESS_LOCK:
        return _SESSION_AGENT.get(sid, False)


def _session_record(sid: str, user_msg: str, assistant_msg: str, was_agent: bool) -> None:
    with _SESS_LOCK:
        if len(_SESSIONS) > _SESS_MAX:
            for k in list(_SESSIONS)[:-200]:
                _SESSIONS.pop(k, None)
                _SESSION_AGENT.pop(k, None)
        h = _SESSIONS.setdefault(sid, [])
        h.append({"role": "user", "content": (user_msg or "")[:1500]})
        h.append({"role": "assistant", "content": (assistant_msg or "")[:1500]})
        if len(h) > _SESS_MAX_MSGS:
            del h[: len(h) - _SESS_MAX_MSGS]
        _SESSION_AGENT[sid] = was_agent


# 필요시만 연결: 앱/브라우저/도구가 필요할 법한 신호(사이트·동작·기능 단어, URL)가 있을 때만
# 도구 에이전트를 띄운다. 순수 잡담·일반지식 질문은 None → 빠른 일반 GPT가 바로 답.
# (차단이 아니라 라우팅 — 신호는 넓게 잡아 작업이 일반챗으로 새지 않게 한다)
_NEEDS_AGENT = re.compile(
    r"https?://|\.com|\.kr|"
    r"네이버|스토어|스마트스토어|카페|블로그|유튜브|구글|gmail|지메일|가비아|eum|공제회|하이웍스|카카오|"
    r"나라장터|지원사업|공공데이터|사이트|페이지|"
    r"열어|열기|연결|접속|들어가|이동|로그인|"
    r"분석|수집|크롤|검색|조회|실행|정리|클릭|입력|작성|등록|발송|전송|보내|올려|업로드|다운로드|"
    r"가져와|찾아|보여|만들|생성|새로고침|확인해|"
    r"세션|현황|상태|정산|주문|상품|리뷰|키워드|뉴스|메일|팩스|승인|초안|seo|마케팅|입찰|기능|"
    # 현재 열린 페이지(사용자가 로그인·이동해 둔 화면)에서 바로 시키는 경우
    r"여기|여기서|이 ?페이지|이 ?화면|이 ?사이트|현재 ?페이지|현재 ?화면|지금 ?화면|지금 ?보|지금 ?페이지|이 ?글|이 ?표|이 ?목록|화면에",
    re.IGNORECASE,
)


def _needs_agent(message: str) -> bool:
    return bool(_NEEDS_AGENT.search(message or ""))


def _run_free_agent_task(message: str, model: str | None, history: list[dict] | None = None) -> str | None:
    """자율 도구호출 에이전트로 명령 수행(분류기·고정URL 없이 GPT가 직접).

    라우팅(에이전트 vs 일반챗)은 호출부(agent_ai_chat)가 결정. history 로 멀티턴 맥락 유지.
    CDP 없으면(서버 등) None → 일반 챗 폴백. 로그인 필요 시 비동기 job + 안내 반환.
    """
    try:
        from scripts.browser_agent.free_agent import run_free_agent
    except Exception:
        return None
    r = run_free_agent(message, model=model, login_wait=False, history=history)
    if r.get("no_browser"):
        return None  # 브라우저 없음 → 일반 챗
    if not r.get("needs_login"):
        return r.get("text") or None

    # 로그인 필요 → 비동기: 백그라운드로 로그인 대기+작업 재개, 즉시 안내.
    import uuid

    job_id = uuid.uuid4().hex[:12]
    with _TASK_LOCK:
        if len(_BROWSER_TASKS) > 50:
            for k in list(_BROWSER_TASKS)[:-40]:
                _BROWSER_TASKS.pop(k, None)
        _BROWSER_TASKS[job_id] = {"status": "pending"}

    def _resume() -> None:
        from scripts.browser_agent.free_agent import run_free_agent as _rfa

        try:
            res = _rfa(message, model=model, login_wait=True, history=history)
            txt = res.get("text") or "완료"
        except Exception as e:
            txt = f"⚠ 작업 오류: {str(e)[:150]}"
        with _TASK_LOCK:
            _BROWSER_TASKS[job_id] = {"status": "done", "result": txt}

    Thread(target=_resume, daemon=True).start()
    return (
        "🔐 로그인이 필요합니다 — 화면에 뜬 브라우저에서 로그인해 주세요.\n"
        "로그인하면 작업이 자동으로 이어지고, 잠시 후 결과가 여기에 표시됩니다.\n\n"
        f"[[JOB:{job_id}]]"
    )


# ── endpoints ────────────────────────────────────────────────


@agent_ai_proxy_router.get("/task/{job_id}")
def agent_ai_task(
    job_id: str,
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> dict:
    """비동기 브라우저 작업(job) 상태 조회 — 프론트가 로그인 후 결과를 폴링한다."""
    _authenticate(x_agent_id, authorization, x_device_token)
    with _TASK_LOCK:
        t = _BROWSER_TASKS.get(job_id)
    if not t:
        return {"status": "unknown"}
    return {"status": t.get("status", "pending"), "result": t.get("result", "")}


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

    # ── 세션 기억 + 멀티턴 라우팅 ──
    # 같은 채팅창(session_id)의 이전 대화를 함께 보고 이어 진행. 직전 턴이 에이전트면
    # 짧은 후속 답("쇼핑")도 에이전트로(키워드 없어도 연속). 순수 잡담은 일반 GPT.
    sid = (body.session_id or "default")[:80]
    history = _session_history(sid)
    use_agent = _needs_agent(msg) or _session_is_agent(sid)

    if use_agent:
        try:
            _task = _run_free_agent_task(msg, body.model, history)
        except Exception:
            logger.exception("free_agent error")
            _task = None
        if _task is not None:
            logger.info("agent_ai_chat free-agent agent=%s", _mask_agent_id(agent_id))
            _session_record(sid, msg, _task, was_agent=True)
            return ChatResponse(ok=True, text=_task, model="app-agent")

    # 일반 GPT (대화 맥락 유지) — call_openai_agent(no tools) 로 history 반영
    _sys = {
        "role": "system",
        "content": "당신은 해한 AI 비서입니다. 한국어로 간결·정확하게, 이전 대화 맥락을 이어 답하세요.",
    }
    res = _caller.call_openai_agent(
        messages=[_sys, *history, {"role": "user", "content": msg}], tools=None, model=body.model
    )
    user_raw, msg = msg, ""  # 원문 폐기(세션 기록용으로만 보관)
    if not res.get("ok"):
        ec = res.get("error_code", "PROVIDER_ERROR")
        logger.info("agent_ai_chat plain ok=False ec=%s agent=%s", ec, _mask_agent_id(agent_id))
        return ChatResponse(
            ok=False, error_code=ec, user_message_kr=_USER_MSG.get(ec, "AI 응답 오류"), model=res.get("model", "")
        )
    text = ((res.get("message") or {}).get("content") or "").strip() or "…"
    logger.info("agent_ai_chat plain ok agent=%s len=%d", _mask_agent_id(agent_id), len(text))
    _session_record(sid, user_raw, text, was_agent=False)
    return ChatResponse(
        ok=True, text=text, model=res.get("model", "") or _caller.get_default_model(), external_call_count=1
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
