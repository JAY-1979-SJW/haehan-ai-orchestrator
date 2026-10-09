"""CDP 팝업 관리 엔드포인트."""

from __future__ import annotations

import sys

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, run_with_cdp_context

router = APIRouter()
_SS_ORIGIN = "https://sell.smartstore.naver.com"


def _active_page(ctx):
    return (
        next((p for p in ctx.pages if "products/create" in p.url), None)
        or next((p for p in ctx.pages if "smartstore.naver.com" in p.url), None)
        or ctx.pages[0]
    )


@router.post("/popup/unblock")
def api_popup_unblock(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

    try:
        result = run_with_cdp_context(lambda ctx: CdpPopupManager().unblock(ctx, origin=_SS_ORIGIN))
    except Exception as e:  # noqa: BLE001 - 스마트스토어 CDP 팝업 관리(모달 닫기/배너 스캔) — 모든 except가 {ok: False, error}를 반환, 데이터 삭제나 승인 우회와 무관한 UI 팝업 정리 기능.
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event("SMARTSTORE_POPUP_UNBLOCK", task_id="-", actor=user["actor"], role=user["role"], decision="ok")
    return result


@router.get("/popup/status")
def api_popup_status(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import get_manager

    return {"ok": True, **get_manager().status()}


@router.post("/popup/scan")
def api_popup_scan(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

    def _scan(ctx):
        page = _active_page(ctx)
        mgr = CdpPopupManager()
        modals = mgr.scan_page(page)
        banners = mgr.scan_banners(page)
        return {"ok": True, "url": page.url, **modals, "banners_found": banners["found"], "banners": banners["banners"]}

    try:
        return run_with_cdp_context(_scan)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 CDP 팝업 관리(모달 닫기/배너 스캔) — 모든 except가 {ok: False, error}를 반환, 데이터 삭제나 승인 우회와 무관한 UI 팝업 정리 기능.
        return {"ok": False, "error": str(e)}


@router.get("/popup/poller")
def api_popup_poller_status(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import poller_status

    return {"ok": True, **poller_status()}


@router.post("/popup/poller/start")
def api_popup_poller_start(interval: int = 5, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import start_poller

    p = start_poller(interval=interval)
    return {"ok": True, "running": p.running, "interval": interval}


@router.post("/popup/poller/stop")
def api_popup_poller_stop(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import stop_poller

    stop_poller()
    return {"ok": True, "running": False}


@router.post("/popup/handle")
def api_popup_handle(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

    def _handle(ctx):
        page = _active_page(ctx)
        mgr = CdpPopupManager()
        mgr.unblock(ctx, origin=_SS_ORIGIN)
        result = mgr.handle_page(page, auto_confirm=True)
        return {"ok": True, "url": page.url, **result}

    try:
        result = run_with_cdp_context(_handle)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 CDP 팝업 관리(모달 닫기/배너 스캔) — 모든 except가 {ok: False, error}를 반환, 데이터 삭제나 승인 우회와 무관한 UI 팝업 정리 기능.
        return {"ok": False, "error": str(e)}
    log_event(
        "SMARTSTORE_POPUP_HANDLE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"closed={result.get('closed')} clean={result.get('page_clean')}",
    )
    return result
