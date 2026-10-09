"""주문 목록 엔드포인트."""

from __future__ import annotations

import sys
import time as _t

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_page, save_ss

router = APIRouter()


@router.get("/orders")
def api_orders(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_ORDERS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("orders")


@router.post("/orders/collect")
def api_orders_collect(limit: int = 50, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from scripts.naver.smartstore import NaverSmartStore

        result = run_with_cdp_page(lambda page: NaverSmartStore(page).list_orders(limit=limit))
    except Exception as e:  # noqa: BLE001 - 주문 조회/발송처리 엔드포인트 — 발송(ship) 엔드포인트는 body.confirm 검증이 try 블록 이전에 이미 끝난 뒤에만 실제 처리하며, except는 CDP 브라우저 연결 실패 등을 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("orders", result)
    log_event(
        "SMARTSTORE_ORDERS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result


# ── 발송대기 주문 조회·발송처리 (구 chat.py _run_tool 대체) ──────────────────────


@router.get("/orders/pending")
def api_orders_pending(limit: int = 50, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """미발송(발송대기) 주문 목록 조회(order_shipping.py 재사용)."""
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor

    try:
        result = run_with_cdp_page(lambda page: OrderShippingProcessor(page).get_pending_orders(limit=limit))
    except Exception as e:  # noqa: BLE001 - 주문 조회/발송처리 엔드포인트 — 발송(ship) 엔드포인트는 body.confirm 검증이 try 블록 이전에 이미 끝난 뒤에만 실제 처리하며, except는 CDP 브라우저 연결 실패 등을 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_ORDERS_PENDING",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result


class ProcessShippingRequest(BaseModel):
    order_id: str
    tracking_number: str
    carrier: str = "CJ대한통운"
    dry_run: bool = True
    confirm: bool = False


@router.post("/orders/{order_id}/ship")
def api_orders_ship(
    order_id: str, body: ProcessShippingRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    """주문에 송장번호를 입력하고 발송처리 (쓰기). confirm=true 없이는 거부, dry_run 기본 True."""
    if body.order_id != order_id:
        return {"ok": False, "error": "path의 order_id와 body의 order_id가 다릅니다."}
    if not body.confirm:
        return {"ok": False, "error": "confirm=true 없이는 실행할 수 없습니다."}
    if body.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "note": "dry_run=True — 실제 발송처리 없이 계획만 반환합니다.",
            "order_id": order_id,
            "tracking_number": body.tracking_number,
            "carrier": body.carrier,
        }
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor

    try:
        result = run_with_cdp_page(
            lambda page: OrderShippingProcessor(page).process_order(
                order_id=order_id,
                tracking_number=body.tracking_number,
                carrier=body.carrier,
                confirmed=True,
            )
        )
    except Exception as e:  # noqa: BLE001 - 주문 조회/발송처리 엔드포인트 — 발송(ship) 엔드포인트는 body.confirm 검증이 try 블록 이전에 이미 끝난 뒤에만 실제 처리하며, except는 CDP 브라우저 연결 실패 등을 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_ORDERS_SHIP",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"order_id={order_id}",
    )
    return {**result, "dry_run": False}
