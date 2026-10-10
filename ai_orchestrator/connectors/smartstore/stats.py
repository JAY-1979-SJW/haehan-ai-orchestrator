"""데이터 분석·통계 엔드포인트."""

from __future__ import annotations

import sys
import time as _t

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_page, save_ss

router = APIRouter()


@router.get("/stats")
def api_stats(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_STATS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("stats")


@router.post("/stats/collect")
def api_stats_collect(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from scripts.naver.smartstore import NaverSmartStore

        result = run_with_cdp_page(lambda page: NaverSmartStore(page).stats())
    except Exception as e:  # noqa: BLE001 - 통계 CDP 수집 실패를 {ok: False, error}로 저장 — 읽기 전용 조회
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("stats", result)
    log_event(
        "SMARTSTORE_STATS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result
