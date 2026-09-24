"""리뷰·문의 엔드포인트."""

from __future__ import annotations

import sys
import time as _t

from fastapi import APIRouter, Depends

from ai_orchestrator.gates.auth import require_role

from ...audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, save_ss

router = APIRouter()
_CDP = "http://127.0.0.1:9222"


@router.get("/reviews")
def api_reviews(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_REVIEWS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("reviews")


@router.post("/reviews/collect")
def api_reviews_collect(limit: int = 30, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            page = pw.chromium.connect_over_cdp(_CDP).contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore

            result = NaverSmartStore(page).list_reviews(limit=limit)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("reviews", result)
    log_event(
        "SMARTSTORE_REVIEWS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result
