"""마케팅·프로모션 엔드포인트."""

from __future__ import annotations

import sys
import time as _t

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_page, save_ss

router = APIRouter()


@router.get("/marketing")
def api_marketing(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_MARKETING_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("marketing")


@router.post("/marketing/collect")
def api_marketing_collect(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()

    def _collect(page):
        from scripts.naver.smartstore import NaverSmartStore

        ss = NaverSmartStore(page)
        return {"ok": True, "promotions": ss.list_promotions(), "marketing": ss.list_marketing()}

    try:
        result = run_with_cdp_page(_collect)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 마케팅 현황 CDP 수집 실패를 {ok: False, error}로 저장 — 읽기 전용 수집
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("marketing", result)
    log_event(
        "SMARTSTORE_MARKETING_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result
