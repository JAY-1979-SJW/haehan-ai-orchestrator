"""상품 목록·상세·등록·수정·카테고리 엔드포인트."""

from __future__ import annotations

import logging
import sys
import time as _t

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_context, run_with_cdp_page, save_ss

logger = logging.getLogger(__name__)

router = APIRouter()

_REGISTER_URL = "https://sell.smartstore.naver.com/#/products/create"


def _notify_collect(rows: list, ok: bool) -> None:
    try:
        from scripts.naver.smartstore.navigation.cdp_popup_manager import PopupEvent, get_manager

        ev = PopupEvent("collect", {"note": f"상품 {len(rows)}개 수집 {'완료' if ok else '실패'}", "ok": ok})
        ev.handled = True
        mgr = get_manager()
        with mgr._lock:
            mgr._events.append(ev)
    except Exception as exc:  # noqa: BLE001
        logger.debug("상품 이벤트 매니저 기록 실패(무시): %s", type(exc).__name__)
        pass


# ── 상품 목록 ─────────────────────────────────────────────────────────────────


@router.get("/products")
def api_products(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_PRODUCTS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("products")


@router.post("/products/collect")
def api_products_collect(limit: int = 50, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from scripts.naver.smartstore import NaverSmartStore

        result = run_with_cdp_page(lambda page: NaverSmartStore(page).list_products(limit=limit))
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("products", result)
    log_event(
        "SMARTSTORE_PRODUCTS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"rows={len(result.get('rows', []))}",
    )
    _notify_collect(result.get("rows", []), bool(result.get("ok")))
    return result


# ── 상품 상세 ─────────────────────────────────────────────────────────────────


@router.get("/products/{product_id}")
def api_product_detail(
    product_id: str, refresh: bool = False, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.detail_collector import collect_product_detail, load_product_detail

    if not refresh:
        result = load_product_detail(product_id)
        log_event(
            "SMARTSTORE_PRODUCT_DETAIL_READ",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok" if result.get("ok") else "miss",
            note=f"product_id={product_id} source=cache",
        )
        return result
    t0 = _t.monotonic()
    try:
        result = run_with_cdp_page(lambda page: collect_product_detail(page, product_id))
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        result = {"ok": False, "error": str(e), "product_id": product_id}
    result["duration_ms"] = elapsed_ms(t0)
    log_event(
        "SMARTSTORE_PRODUCT_DETAIL_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"product_id={product_id}",
    )
    return result


@router.post("/products/{product_id}/collect")
def api_product_detail_collect(product_id: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.detail_collector import collect_product_detail

    t0 = _t.monotonic()
    try:
        result = run_with_cdp_page(lambda page: collect_product_detail(page, product_id))
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        result = {"ok": False, "error": str(e), "product_id": product_id}
    result["duration_ms"] = elapsed_ms(t0)
    log_event(
        "SMARTSTORE_PRODUCT_DETAIL_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"product_id={product_id}",
    )
    return result


# ── 상품 수정 ─────────────────────────────────────────────────────────────────


class ProductEditRequest(BaseModel):
    fields: dict
    dry_run: bool = True


@router.post("/products/{product_id}/edit")
def api_product_edit(
    product_id: str, body: ProductEditRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict:
    if not body.dry_run:
        return {"ok": False, "error": "실제저장(dry_run=False)은 비활성화 상태입니다."}
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.form_runner import ProductFormRunner

    edit_fields = {**body.fields, "save": False}

    def _edit(ctx):
        page = next((p for p in ctx.pages if f"products/{product_id}" in p.url), None) or ctx.new_page()
        page.bring_to_front()
        return ProductFormRunner(page).edit(product_id, edit_fields)

    try:
        result = run_with_cdp_context(_edit)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_PRODUCT_EDIT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "fail",
        note=f"product_id={product_id} fields={list(body.fields.keys())}",
    )
    return {**result, "dry_run": body.dry_run}


# ── 상품 자동 등록 ────────────────────────────────────────────────────────────


class AutoRegisterRequest(BaseModel):
    data: dict
    dry_run: bool = True
    skip_open: bool = False


@router.post("/products/auto-register")
def api_products_auto_register(body: AutoRegisterRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    if not body.dry_run:
        return {
            "ok": False,
            "error": "실제 저장(dry_run=False)은 비활성화 상태입니다.",
            "hint": "CDP 브라우저에서 직접 최종 저장 버튼을 눌러주세요.",
        }
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.form_runner import ProductFormRunner

    register_data = {**body.data, "save": False, "require_confirm": False}

    def _register(ctx):
        page = next((p for p in ctx.pages if "products/create" in p.url or "products/register" in p.url), None)
        skip = body.skip_open
        if page is None:
            page = ctx.new_page()
            page.goto(_REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
            skip = True
        page.bring_to_front()
        return ProductFormRunner(page).run(register_data, skip_open=skip)

    try:
        result = run_with_cdp_context(_register)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_AUTO_REGISTER",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "fail",
        note=f"dry_run={body.dry_run} name={body.data.get('name', '')[:20]}",
    )
    return {**result, "dry_run": body.dry_run}


# ── 카테고리 캐시 ─────────────────────────────────────────────────────────────


@router.get("/categories/cache")
def api_categories_cache_info(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.category_cache import cache_info, load_cache

    info = cache_info()
    sample = load_cache()[:5] if info.get("exists") else []
    return {"ok": True, **info, "sample": sample}


@router.post("/categories/cache/build")
def api_categories_cache_build(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    import time

    from scripts.naver.smartstore.product.category_cache import build_cache

    def _build(ctx):
        page = next((p for p in ctx.pages if "products/create" in p.url), None)
        if not page:
            page = ctx.new_page()
            page.goto(
                "https://sell.smartstore.naver.com/#/products/create", timeout=20000, wait_until="domcontentloaded"
            )
            time.sleep(3)
        page.bring_to_front()
        return build_cache(page)

    try:
        result = run_with_cdp_context(_build)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    if result.get("ok"):
        log_event(
            "SMARTSTORE_CATEGORY_CACHE_BUILD",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"count={result.get('count')}",
        )
    return result


# ── 상품 삭제 (구 chat.py _run_tool 대체, 비가역) ────────────────────────────────


class DeleteProductRequest(BaseModel):
    product_id: str | None = None
    product_ids: list[str] | None = None
    dry_run: bool = True
    confirm: bool = False


@router.post("/products/delete")
def api_products_delete(body: DeleteProductRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상품 삭제 (쓰기, 비가역). confirm=true 없이는 거부, dry_run 기본 True."""
    if not body.product_id and not body.product_ids:
        return {"ok": False, "error": "product_id 또는 product_ids 필요"}
    if not body.confirm:
        return {"ok": False, "error": "confirm=true 없이는 실행할 수 없습니다."}
    if body.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "note": "dry_run=True — 실제 삭제 없이 계획만 반환합니다.",
            "product_id": body.product_id,
            "product_ids": body.product_ids,
        }
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.product_delete import ProductDeleter

    def _delete(page):
        deleter = ProductDeleter(page)
        if body.product_ids:
            return deleter.delete_bulk(body.product_ids, confirmed=True)
        return deleter.delete(body.product_id, confirmed=True)

    try:
        result = run_with_cdp_page(_delete)
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 CRUD API 라우터 - 상품삭제는 상위 로직에서 confirm=true, dry_run 게이트와 admin/owner 권한검증을 통과해야만 도달, except 는 CDP 연결 실패 등을 ok:False,error 로 반환할 뿐 승인 로직 우회 없음
        result = {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_PRODUCT_DELETE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"product_id={body.product_id} product_ids={body.product_ids}",
    )
    return {**result, "dry_run": False}


@router.get("/categories/search")
def api_categories_search(q: str = "", user: dict = Depends(require_role("admin", "owner"))) -> dict:
    if not q:
        return {"ok": False, "error": "q 파라미터 필요"}
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.category_cache import load_cache

    cats = load_cache()
    ql = q.lower()
    matches = [c for c in cats if ql in c.get("name", "").lower() or ql in c.get("path", "").lower()]
    matches.sort(key=lambda c: (-c.get("level", 0), len(c.get("path", ""))))
    return {"ok": True, "query": q, "count": len(matches), "results": matches[:20]}
