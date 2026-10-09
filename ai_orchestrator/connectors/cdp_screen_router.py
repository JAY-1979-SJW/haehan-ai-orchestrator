"""CDP 라이브 화면 + 연결 상태 — Playwright 직접 연결 방식.

읽기 전용. AI가 CDP에서 작업하는 실제 브라우저 화면을 앱 콘솔 옆에 라이브로 보여주기 위함.
L3 Connectors. 업무 로직 없음(스크린샷·상태 조회만).
"""

from __future__ import annotations

import logging
import urllib.request

from fastapi import APIRouter, Depends, Response

from tools.gates.auth import require_role

cdp_screen_router = APIRouter(prefix="/cdp", tags=["cdp"])
logger = logging.getLogger(__name__)

_CDP_URL = "http://127.0.0.1:9222"


def _cdp_alive() -> bool:
    """9222 포트에 CDP 브라우저가 응답하는지 HTTP로 확인 (Playwright 불필요)."""
    try:
        with urllib.request.urlopen(f"{_CDP_URL}/json/version", timeout=2) as r:  # noqa: S310
            return r.status == 200
    except Exception:  # noqa: BLE001 - CDP 상태 확인/스크린샷 조회 -- 읽기 전용 best-effort, 실패 시 False/None 반환
        return False


def _take_screenshot() -> bytes | None:
    """Playwright로 CDP에 연결해 현재 탭 스크린샷 반환. 실패 시 None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(_CDP_URL, timeout=5000)
            if not browser.contexts:
                return None
            pages = browser.contexts[0].pages
            if not pages:
                return None
            return pages[-1].screenshot(type="jpeg", quality=55)
    except Exception as e:  # noqa: BLE001 - CDP 상태 확인/스크린샷 조회 -- 읽기 전용 best-effort, 실패 시 False/None 반환
        logger.debug("CDP 스크린샷 실패: %s", e)
        return None


@cdp_screen_router.get("/status")
def cdp_status(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """CDP 연결 여부를 실시간으로 반환. Playwright 없이 HTTP 체크만."""
    alive = _cdp_alive()
    return {"connected": alive, "url": _CDP_URL if alive else None}


@cdp_screen_router.get("/screen.jpg")
def cdp_screen(user: dict = Depends(require_role("admin", "owner"))) -> Response:
    """현재 CDP 페이지를 JPEG로 캡처. CDP 미연결/탭 없음이면 204(No Content)."""
    if not _cdp_alive():
        return Response(status_code=204)

    img = _take_screenshot()
    if not img:
        return Response(status_code=204)
    return Response(content=img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
