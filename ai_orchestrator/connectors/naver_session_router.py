"""네이버 세션 관리 라우터 (L8).

엔드포인트:
  POST /api/v1/naver/session/login   — CDP 시작 + 로그인 파이프라인 실행
  GET  /api/v1/naver/session/status  — 저장된 세션 상태 조회
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_orchestrator.auth import require_role

router = APIRouter(prefix="/naver/session", tags=["naver-session"])

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="naver_login")


class SessionStatusResponse(BaseModel):
    logged_in: bool
    user: str | None
    checked_at: str | None
    pending_captcha: bool = False
    browser_session_saved: bool = False
    error: str | None = None


class LoginResponse(BaseModel):
    ok: bool
    logged_in: bool
    user: str | None
    message: str
    captcha: bool = False


@router.get("/sessions")
async def get_all_sessions(_: None = Depends(require_role("admin", "owner"))):
    """저장된 네이버 서브도메인 세션 목록을 반환합니다."""
    from ai_orchestrator.workflows.naver_login_pipeline import list_naver_sessions
    return {"sessions": list_naver_sessions()}


@router.get("/status", response_model=SessionStatusResponse)
async def get_session_status(_: None = Depends(require_role("admin", "owner"))):
    """저장된 네이버 세션 상태를 반환합니다."""
    from ai_orchestrator.workflows.naver_login_pipeline import load_session_status
    state = load_session_status()
    from ai_orchestrator.workflows.naver_login_pipeline import has_saved_browser_session
    return SessionStatusResponse(
        logged_in=state.get("logged_in", False),
        user=state.get("user"),
        checked_at=state.get("checked_at"),
        pending_captcha=state.get("pending_captcha", False),
        browser_session_saved=has_saved_browser_session(),
        error=state.get("error"),
    )


@router.post("/login", response_model=LoginResponse)
async def trigger_login(_: None = Depends(require_role("admin", "owner"))):
    """CDP 브라우저를 시작하고 네이버 로그인 파이프라인을 실행합니다.

    동기 playwright 코드를 별도 스레드에서 실행합니다.
    """
    from ai_orchestrator.workflows.naver_login_pipeline import run_naver_login_pipeline
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, run_naver_login_pipeline)
    return LoginResponse(
        ok=result.get("ok", False),
        logged_in=result.get("logged_in", False),
        user=result.get("user"),
        message=result.get("message", ""),
        captcha=result.get("captcha", False),
    )
