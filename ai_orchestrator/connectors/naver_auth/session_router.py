"""네이버 세션 관리 라우터 (L8).

엔드포인트:
  POST /api/v1/naver/session/login   — CDP 시작 + 로그인 파이프라인 실행 (계정 미지정 시 기본 저장 계정)
  GET  /api/v1/naver/session/status  — 저장된 세션 상태 조회(파일)
  GET  /api/v1/naver/session/live    — 실제 상태·계정 확인(읽기 전용, 아무것도 바꾸지 않음)
  POST /api/v1/naver/session/ensure  — 로그아웃(out)일 때만 대상 계정으로 자동 로그인 1회 (기준서 2026-10-01_electron_naver_auto_login)
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tools.gates.auth import require_role

router = APIRouter(prefix="/naver/session", tags=["naver-session"])

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="naver_login")


class SessionStatusResponse(BaseModel):
    logged_in: bool
    user: str | None
    checked_at: str | None
    pending_captcha: bool = False
    browser_session_saved: bool = False
    error: str | None = None


class LoginRequest(BaseModel):
    username: str | None = None  # 계정 ID (없으면 기본 저장 계정 사용)


class LoginResponse(BaseModel):
    ok: bool
    logged_in: bool
    user: str | None
    message: str
    captcha: bool = False


class EnsureRequest(BaseModel):
    username: str = "skyjwsin"  # 대상 블로그 계정(기본 skyjwsin)
    allow_attempt: bool = True  # False 면 상태만 확인하고 로그인은 시도하지 않는다


def get_guard_deps():
    """세션 지킴이의 실제 부품(브라우저·파이프라인·시도 기록). 테스트에서 dependency_overrides 로 바꾼다."""
    from ai_orchestrator.connectors.naver_auth.session_guard import default_deps

    return default_deps()


def _known_targets() -> set[str]:
    from scripts.naver.blog.accounts import BLOG_ACCOUNTS

    return set(BLOG_ACCOUNTS)


def _valid_target_or_400(username: str) -> str:
    if username not in _known_targets():
        raise HTTPException(status_code=400, detail=f"등록되지 않은 블로그 계정: {username}")
    return username


class AccountRequest(BaseModel):
    username: str
    password: str


@router.get("/sessions")
async def get_all_sessions(_: None = Depends(require_role("admin", "owner"))):
    """저장된 네이버 서브도메인 세션 목록을 반환합니다."""
    from ai_orchestrator.connectors.naver_auth.login_pipeline import list_naver_sessions

    return {"sessions": list_naver_sessions()}


@router.get("/status", response_model=SessionStatusResponse)
async def get_session_status(_: None = Depends(require_role("admin", "owner"))):
    """저장된 네이버 세션 상태를 반환합니다."""
    from ai_orchestrator.connectors.naver_auth.login_pipeline import load_session_status

    state = load_session_status()
    from ai_orchestrator.connectors.naver_auth.login_pipeline import has_saved_browser_session

    return SessionStatusResponse(
        logged_in=state.get("logged_in", False),
        user=state.get("user"),
        checked_at=state.get("checked_at"),
        pending_captcha=state.get("pending_captcha", False),
        browser_session_saved=has_saved_browser_session(),
        error=state.get("error"),
    )


@router.get("/accounts")
async def list_accounts(_: None = Depends(require_role("admin", "owner"))):
    """저장된 네이버 계정 목록을 반환합니다."""
    from scripts.auth.credentials import get_cred, list_sites

    accounts = []
    for key in list_sites():
        if key == "naver":
            cred = get_cred("naver")
            accounts.append({"key": key, "username": cred.get("id", "")})
        elif key.startswith("naver:"):
            uid = key.split(":", 1)[1]
            accounts.append({"key": key, "username": uid})
    return {"accounts": accounts}


@router.post("/accounts")
async def add_account(req: AccountRequest, _: None = Depends(require_role("admin", "owner"))):
    """네이버 계정을 추가/갱신합니다."""
    from scripts.auth.credentials import set_cred

    set_cred(f"naver:{req.username}", id=req.username, pw=req.password)
    return {"ok": True, "message": f"계정 저장 완료: naver:{req.username}"}


@router.post("/login", response_model=LoginResponse)
async def trigger_login(req: LoginRequest = LoginRequest(), _: None = Depends(require_role("admin", "owner"))):
    """CDP 브라우저를 시작하고 네이버 로그인 파이프라인을 실행합니다.

    username 지정 시 해당 계정으로 로그인 전환. 없으면 기본 저장 계정 사용.
    동기 playwright 코드를 별도 스레드에서 실행합니다.
    """
    from functools import partial

    from ai_orchestrator.connectors.naver_auth.login_pipeline import run_naver_login_pipeline

    loop = asyncio.get_running_loop()
    fn = partial(run_naver_login_pipeline, naver_id=req.username)
    result = await loop.run_in_executor(_executor, fn)
    return LoginResponse(
        ok=result.get("ok", False),
        logged_in=result.get("logged_in", False),
        user=result.get("user"),
        message=result.get("message", ""),
        captcha=result.get("captcha", False),
    )


@router.get("/live")
async def live_status(
    target: str = "skyjwsin",
    _: None = Depends(require_role("admin", "owner")),
    deps=Depends(get_guard_deps),
):
    """실제 로그인 상태와 계정을 확인한다(읽기 전용 — 로그인·로그아웃·쿠키 변경 없음)."""
    from functools import partial

    from ai_orchestrator.connectors.naver_auth.session_guard import observe

    loop = asyncio.get_running_loop()
    seen = await loop.run_in_executor(_executor, partial(observe, _valid_target_or_400(target), deps))
    return {**seen, "targets": sorted(_known_targets())}  # 화면의 계정 선택 목록


@router.post("/ensure")
async def ensure_session(
    req: EnsureRequest | None = None,
    _: None = Depends(require_role("admin", "owner")),
    deps=Depends(get_guard_deps),
):
    """상태 확인 후 로그아웃(out)으로 확정될 때만 대상 계정으로 자동 로그인 1회.

    이미 로그인·상태 불명확·다른 계정이면 건드리지 않는다. 시도는 직전 시도 후 5분 대기·하루 3회로 제한한다.
    수 분 걸릴 수 있다(로그인 파이프라인). 같은 실행기에서 직렬로 돈다.
    """
    from functools import partial

    from ai_orchestrator.connectors.naver_auth.session_guard import ensure_login

    req = req or EnsureRequest()
    loop = asyncio.get_running_loop()
    fn = partial(ensure_login, _valid_target_or_400(req.username), deps, allow_attempt=req.allow_attempt)
    return await loop.run_in_executor(_executor, fn)
