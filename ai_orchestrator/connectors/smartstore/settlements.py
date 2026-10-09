"""정산 내역 엔드포인트."""

from __future__ import annotations

import contextlib
import sys
import time as _t

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_page, save_ss

router = APIRouter()


@router.get("/settlements")
def api_settlements(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event(
        "SMARTSTORE_SETTLEMENTS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note=""
    )
    return load_ss("settlements")


@router.post("/settlements/collect")
def api_settlements_collect(limit: int = 30, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from scripts.naver.smartstore import NaverSmartStore

        result = run_with_cdp_page(lambda page: NaverSmartStore(page).list_settlements(limit=limit))
    except Exception as e:  # noqa: BLE001 - 정산 내역 CDP 수집 실패를 {ok: False, error}로 저장 — 읽기 전용 조회
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("settlements", result)
    log_event(
        "SMARTSTORE_SETTLEMENTS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result


@router.get("/settlements/summary")
def api_settlements_summary(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """정산 요약 — 이번달 예상 정산액 합산."""
    data = load_ss("settlements")
    if not data.get("ok"):
        return {"ok": False, "error": "정산 데이터 없음. /settlements/collect 먼저 실행하세요."}
    rows = data.get("rows", [])
    headers = data.get("headers", [])

    def col(row: list, name: str) -> str:
        try:
            idx = next(i for i, h in enumerate(headers) if name in h)
            return row[idx] if idx < len(row) else ""
        except StopIteration:
            return ""

    total = 0
    for row in rows:
        raw = col(row, "정산금액") or col(row, "금액") or col(row, "amount")
        with contextlib.suppress(ValueError):
            total += int(str(raw).replace(",", "").replace("원", "").strip() or "0")
    return {
        "ok": True,
        "total_rows": len(rows),
        "total_amount": total,
        "total_amount_str": f"{total:,}원",
        "collected_at": data.get("collected_at"),
        "headers": headers,
    }
