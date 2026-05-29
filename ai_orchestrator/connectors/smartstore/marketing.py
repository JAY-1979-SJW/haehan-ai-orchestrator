"""마케팅·프로모션 엔드포인트."""
from __future__ import annotations
import sys, time as _t
from fastapi import APIRouter, Depends
from ...auth import require_role
from ...audit_logger import log_event
from ._helpers import ROOT, load_ss, save_ss, now_iso, elapsed_ms

router = APIRouter()
_CDP = "http://127.0.0.1:9222"


@router.get("/marketing")
def api_marketing(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_MARKETING_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("marketing")


@router.post("/marketing/collect")
def api_marketing_collect(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            page = pw.chromium.connect_over_cdp(_CDP).contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = {"ok": True, "promotions": ss.list_promotions(), "marketing": ss.list_marketing()}
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("marketing", result)
    log_event("SMARTSTORE_MARKETING_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result
