"""브라우저 자동화 API 라우터 — /browser/v1/"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

router = APIRouter(prefix="/browser/v1")


# ── 공통 모델 ────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    args: list[str] = []


class ActionResponse(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] = {}


def _ok(msg: str, **data) -> ActionResponse:
    return ActionResponse(ok=True, message=msg, data=data)


def _err(msg: str) -> ActionResponse:
    return ActionResponse(ok=False, message=msg)


# ── 네이버 ───────────────────────────────────────────────────────────

@router.get("/naver/session-check")
async def naver_session_check() -> ActionResponse:
    def _check():
        from scripts.naver.base import check_session
        return check_session()
    result = await run_in_threadpool(_check)
    if result.get("error"):
        return _err(f"데몬 연결 실패: {result['error']}")
    if result.get("logged_in"):
        return _ok("로그인 상태 정상")
    return _err("로그인 필요")


@router.post("/naver/blog/write")
async def naver_blog_write(req: ActionRequest) -> ActionResponse:
    def _run():
        from scripts.naver.blog import run
        run("write", req.args)
    try:
        await run_in_threadpool(_run)
        return _ok("블로그 작성 완료")
    except Exception as e:
        return _err(str(e))


# ── 구글 ─────────────────────────────────────────────────────────────

@router.get("/google/session-check")
async def google_session_check() -> ActionResponse:
    def _check():
        from scripts.google.base import check_session
        return check_session()
    result = await run_in_threadpool(_check)
    if result.get("error"):
        return _err(f"데몬 연결 실패: {result['error']}")
    if result.get("logged_in"):
        return _ok("로그인 상태 정상")
    return _err("로그인 필요")


@router.post("/google/mail/list")
async def google_mail_list(req: ActionRequest) -> ActionResponse:
    def _run():
        from scripts.google.gmail import run
        run("list", req.args)
    try:
        await run_in_threadpool(_run)
        return _ok("메일 목록 조회 완료")
    except Exception as e:
        return _err(str(e))


@router.post("/google/mail/compose")
async def google_mail_compose(req: ActionRequest) -> ActionResponse:
    """args: [수신자, 제목, 본문]"""
    def _run():
        from scripts.google.gmail import run
        run("compose", req.args)
    try:
        await run_in_threadpool(_run)
        return _ok("메일 발송 완료")
    except Exception as e:
        return _err(str(e))


@router.post("/google/calendar/today")
async def google_calendar_today(req: ActionRequest) -> ActionResponse:
    def _run():
        from scripts.google.calendar import run
        run("today", req.args)
    try:
        await run_in_threadpool(_run)
        return _ok("캘린더 조회 완료")
    except Exception as e:
        return _err(str(e))


# ── 카카오 ───────────────────────────────────────────────────────────

@router.get("/kakao/session-check")
async def kakao_session_check() -> ActionResponse:
    def _check():
        from scripts.kakao.base import check_session
        return check_session()
    result = await run_in_threadpool(_check)
    if result.get("error"):
        return _err(f"데몬 연결 실패: {result['error']}")
    if result.get("logged_in"):
        return _ok("로그인 상태 정상")
    return _err("로그인 필요")


@router.get("/kakao/dev/list")
async def kakao_dev_list() -> ActionResponse:
    def _run():
        from scripts.kakao.dev_console import _task_list
        _task_list([])
    try:
        await run_in_threadpool(_run)
        return _ok("앱 목록 조회 완료")
    except Exception as e:
        return _err(str(e))


@router.post("/kakao/dev/register")
async def kakao_dev_register(req: ActionRequest) -> ActionResponse:
    """args: [앱이름]"""
    def _run():
        from scripts.kakao.dev_console import _task_register
        _task_register(req.args)
    try:
        await run_in_threadpool(_run)
        return _ok("앱 등록 완료")
    except Exception as e:
        return _err(str(e))


# ── 데몬 상태 ────────────────────────────────────────────────────────

@router.get("/daemon/status")
def daemon_status() -> ActionResponse:
    import json
    state_file = ROOT / "data" / "cdp_daemon_state.json"
    if not state_file.exists():
        return _err("데몬 상태 파일 없음")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    return _ok(
        "데몬 상태 조회 완료",
        running=state.get("running"),
        browser=state.get("browser_context"),
        pid=state.get("pid"),
        chrome_pid=state.get("chrome_pid"),
    )
