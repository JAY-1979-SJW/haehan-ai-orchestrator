"""브라우저 자동화 API 라우터 — /browser/v1/"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
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
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(str(e))


# ── 구글 ─────────────────────────────────────────────────────────────


@router.get("/google/session-check")
async def google_session_check() -> ActionResponse:
    def _check():
        from scripts.google.common.base import check_session

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
        from scripts.google.common.gmail import run

        run("list", req.args)

    try:
        await run_in_threadpool(_run)
        return _ok("메일 목록 조회 완료")
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(str(e))


@router.post("/google/mail/compose")
async def google_mail_compose(req: ActionRequest) -> ActionResponse:
    """args: [수신자, 제목, 본문]"""

    def _run():
        from scripts.google.common.gmail import run

        run("compose", req.args)

    try:
        await run_in_threadpool(_run)
        return _ok("메일 발송 완료")
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(str(e))


@router.post("/google/calendar/today")
async def google_calendar_today(req: ActionRequest) -> ActionResponse:
    def _run():
        from scripts.google.common.calendar_tasks import run

        run("today", req.args)

    try:
        await run_in_threadpool(_run)
        return _ok("캘린더 조회 완료")
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
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
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
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
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(str(e))


# ── 범용 페이지 조회 (site-agnostic — 2026-09-01 g2b 검증용으로 추가) ────────
# 네이버/구글/카카오처럼 특정 사이트 로그인 세션이 필요 없는, 임의 URL의
# 렌더링된 텍스트/제목만 읽어오는 용도. web_connector.browser_session()이
# 잡고 있는 데몬 Chrome(CDP)을 그대로 재사용한다 — 새 브라우저 인스턴스를
# 안 띄운다.


class FetchTextRequest(BaseModel):
    url: str
    wait_selector: str | None = None
    wait_ms: int = 800


@router.post("/generic/fetch-text")
async def generic_fetch_text(req: FetchTextRequest) -> ActionResponse:
    def _run():
        import time

        from scripts.browser.page.page_helper import page_goto
        from scripts.browser.page.web_connector import browser_session

        with browser_session() as page:
            page_goto(page, req.url)
            if req.wait_selector:
                page.wait_for_selector(req.wait_selector, timeout=10_000)
            else:
                time.sleep(req.wait_ms / 1000)
            return {
                "title": page.title(),
                "url": page.url,
                "text": page.inner_text("body"),
            }

    try:
        from scripts.browser.cdp.connection import run_on_browser_thread

        result = await run_in_threadpool(lambda: run_on_browser_thread(_run))
        return _ok("페이지 조회 완료", **result)
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(f"{type(e).__name__}: {e}")


@router.post("/generic/screenshot")
async def generic_screenshot(req: FetchTextRequest) -> ActionResponse:
    import base64

    def _run():
        import time

        from scripts.browser.page.page_helper import page_goto
        from scripts.browser.page.web_connector import browser_session

        with browser_session() as page:
            page_goto(page, req.url)
            if req.wait_selector:
                page.wait_for_selector(req.wait_selector, timeout=10_000)
            else:
                time.sleep(req.wait_ms / 1000)
            png = page.screenshot(full_page=True)
            return {
                "title": page.title(),
                "url": page.url,
                "png_base64": base64.b64encode(png).decode("ascii"),
            }

    try:
        from scripts.browser.cdp.connection import run_on_browser_thread

        result = await run_in_threadpool(lambda: run_on_browser_thread(_run))
        return _ok("스크린샷 완료", **result)
    except Exception as e:  # noqa: BLE001 - 액션 실행 FastAPI 라우터(블로그/Gmail/캘린더/카카오/범용 조회) - 모든 except 가 _err(str(e)) 로 실패 응답 반환, 판정 로직 없음
        return _err(f"{type(e).__name__}: {e}")


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
