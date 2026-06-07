"""CDP 라이브 화면 — 현재 CDP 브라우저 페이지를 JPEG로 캡처해 반환.

읽기 전용. AI가 CDP에서 작업하는 실제 브라우저 화면을 앱 콘솔 옆에 라이브로 보여주기 위함.
L3 Connectors. 업무 로직 없음(스크린샷만).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response

from ..auth import require_role

cdp_screen_router = APIRouter(prefix="/cdp", tags=["cdp"])
logger = logging.getLogger(__name__)


@cdp_screen_router.get("/screen.jpg")
def cdp_screen(user: dict = Depends(require_role("admin", "owner"))) -> Response:
    """현재 CDP 페이지를 JPEG로 캡처. CDP 미연결/탭 없음이면 204(No Content)."""
    from scripts.web_connector import run_on_browser_thread

    def _shot() -> bytes | None:
        from scripts.web_connector import get_page

        page = get_page()
        # 저화질 JPEG — 라이브 폴링이라 속도 우선. viewport 영역만(full_page=False 기본).
        return page.screenshot(type="jpeg", quality=55)

    try:
        img = run_on_browser_thread(_shot, timeout=20)
    except Exception as e:
        logger.debug("CDP 화면 캡처 실패(미연결 가능): %s", e)
        img = None

    if not img:
        return Response(status_code=204)
    return Response(content=img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
