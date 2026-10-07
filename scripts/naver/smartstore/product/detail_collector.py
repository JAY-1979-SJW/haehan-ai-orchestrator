"""스마트스토어 상품 상세 CDP 수집 (L3 Connector).

사용:
    from scripts.naver.smartstore.product.detail_collector import collect_product_detail
    result = collect_product_detail(page, product_id="12345678")
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.logger import get_logger
from scripts.naver.smartstore.product import page_selectors as SEL

log = get_logger(__name__)

PRODUCTS_DIR = data_dir() / "smartstore" / "products"
SMARTSTORE_BASE = "https://sell.smartstore.naver.com"


# ── 공개 인터페이스 ──────────────────────────────────────────────────────────


def collect_product_detail(page: Page, product_id: str) -> dict:
    """상품 상세 페이지를 CDP로 수집해 캐시에 저장.

    Args:
        page: 현재 로그인된 Playwright Page
        product_id: 스마트스토어 상품 번호

    Returns:
        {"ok": bool, "product": dict, "source": "cdp", "collected_at": str}
    """
    log.info("[detail_collector] 시작: product_id=%s", product_id)

    # 1. 상세 페이지 진입
    nav = _navigate_to_detail(page, product_id)
    if not nav["ok"]:
        return {"ok": False, "error": nav["error"], "product_id": product_id}

    # 2. 필드 추출
    product = _extract_all_fields(page, product_id)

    # 3. 캐시 저장
    _save_cache(product_id, product)

    log.info("[detail_collector] 완료: product_id=%s name=%s", product_id, product.get("name"))
    return {
        "ok": True,
        "product": product,
        "source": "cdp",
        "collected_at": product["collected_at"],
    }


def load_product_detail(product_id: str) -> dict:
    """캐시에서 상품 상세 로드."""
    p = PRODUCTS_DIR / f"{product_id}.json"
    if not p.exists():
        return {
            "ok": False,
            "error": "no_cache",
            "product_id": product_id,
            "hint": "POST /smartstore/products/{product_id}/collect 로 수집하세요",
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {"ok": True, "product": data, "source": "cache", "collected_at": data.get("collected_at")}
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
        return {"ok": False, "error": str(e), "product_id": product_id}


# ── 내부: 페이지 진입 ────────────────────────────────────────────────────────


def _navigate_to_detail(page: Page, product_id: str) -> dict:
    """상품 상세 URL로 직접 진입."""
    url = f"{SMARTSTORE_BASE}/#/products/{product_id}/edit"
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2)

        # SPA 렌더링 대기 — 상품명 input 또는 에러 메시지 출현 기다림
        deadline = time.time() + 10
        while time.time() < deadline:
            if _try_sel(page, SEL.PRODUCT_NAME):
                return {"ok": True}
            if "not found" in page.url.lower() or "error" in page.url.lower():
                return {"ok": False, "error": "page_not_found"}
            time.sleep(0.5)

        # fallback: 목록에서 클릭
        return _navigate_via_list(page, product_id)

    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
        log.warning("[detail_collector] 직접 진입 실패: %s", e)
        return _navigate_via_list(page, product_id)


def _navigate_via_list(page: Page, product_id: str) -> dict:
    """상품 목록에서 product_id 행 클릭으로 진입."""
    try:
        list_url = f"{SMARTSTORE_BASE}/#/products/list"
        page.goto(list_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)

        # 상품번호가 포함된 링크 탐색
        clicked = page.evaluate(
            """
        (pid) => {
            const links = document.querySelectorAll('a[href]');
            for (const a of links) {
                if ((a.href || '').includes(pid) || (a.textContent || '').includes(pid)) {
                    a.click();
                    return true;
                }
            }
            const trs = document.querySelectorAll('tbody tr');
            for (const tr of trs) {
                if ((tr.textContent || '').includes(pid)) {
                    tr.click();
                    return true;
                }
            }
            return false;
        }
        """,
            product_id,
        )

        if clicked:
            time.sleep(2)
            if _try_sel(page, SEL.PRODUCT_NAME):
                return {"ok": True}

        return {"ok": False, "error": f"product_id {product_id} 를 목록에서 찾지 못했습니다"}

    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
        return {"ok": False, "error": f"목록 진입 실패: {e}"}


# ── 내부: 필드 추출 ─────────────────────────────────────────────────────────


def _extract_all_fields(page: Page, product_id: str) -> dict:
    """현재 상세 페이지에서 모든 필드를 추출."""
    product: dict[str, Any] = {"product_id": product_id}

    product["name"] = _get_input_value(page, SEL.PRODUCT_NAME)
    product["status"] = _get_text(page, SEL.PRODUCT_STATUS) or "UNKNOWN"
    # SEL.CATEGORY/MAIN_IMAGE/ADDITIONAL_IMAGES 는 존재한 적 없는 이름 — 셀렉터 리네임 후
    # 이 호출부만 갱신 안 됐던 것으로 보임(2026-09-29 defect_index #39, 각 셀렉터의 실제
    # CSS 값·한글 주석·용도가 아래 이름과 정확히 일치함을 selectors.py 에서 직접 확인).
    product["category"] = _get_text(page, SEL.CATEGORY_PATH_DISPLAY) or _get_input_value(
        page, SEL.CATEGORY_PATH_DISPLAY
    )
    product["channel_product_id"] = _get_text(page, SEL.CHANNEL_PRODUCT_ID)

    # 가격·재고
    product["price"] = _parse_int(_get_input_value(page, SEL.SALE_PRICE))
    product["original_price"] = _parse_int(_get_input_value(page, SEL.ORIGINAL_PRICE))
    product["stock"] = _parse_int(_get_input_value(page, SEL.STOCK))
    product["min_purchase"] = _parse_int(_get_input_value(page, SEL.MIN_PURCHASE)) or 1
    product["max_purchase"] = _parse_int(_get_input_value(page, SEL.MAX_PURCHASE))

    # 이미지
    product["main_image_url"] = _get_img_src(page, SEL.MAIN_IMAGE_PREVIEW)
    product["images"] = _get_img_src_list(page, SEL.ADDITIONAL_IMAGES_PREVIEW)

    # 옵션
    options = _extract_options(page)
    product["has_options"] = len(options) > 0
    product["options"] = options

    # 배송
    product["delivery_fee"] = _parse_int(_get_input_value(page, SEL.DELIVERY_FEE)) or 0

    # 통계 (없으면 None)
    product["view_count"] = _parse_int(_get_text(page, SEL.VIEW_COUNT))
    product["order_count"] = _parse_int(_get_text(page, SEL.ORDER_COUNT))
    product["review_count"] = _parse_int(_get_text(page, SEL.REVIEW_COUNT))
    product["review_score"] = _parse_float(_get_text(page, SEL.REVIEW_SCORE))

    # 현재 URL
    product["detail_url"] = page.url
    product["collected_at"] = datetime.now().isoformat(timespec="seconds")
    product["source"] = "cdp"

    # 누락 필드 목록
    missing = [k for k, v in product.items() if v is None and k in ("name", "price", "stock")]
    if missing:
        product["_missing_fields"] = missing
        log.warning("[detail_collector] 누락 필드: %s", missing)

    return product


def _extract_options(page: Page) -> list[dict]:
    """옵션 테이블에서 옵션 목록 추출."""
    try:
        rows = page.evaluate("""
        () => {
            const tbl = document.querySelector(
                'table.option-management-table, table[class*="optionTable"]'
            );
            if (!tbl) return [];
            const out = [];
            tbl.querySelectorAll('tbody tr').forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td'))
                    .map(td => (td.innerText || '').trim());
                if (cells.length >= 2) out.push(cells);
            });
            return out;
        }
        """)
        options = []
        for cells in rows or []:
            if len(cells) >= 2:
                options.append(
                    {
                        "option_name": cells[0] if len(cells) > 0 else "",
                        "option_value": cells[1] if len(cells) > 1 else "",
                        "price_diff": _parse_int(cells[2]) or 0 if len(cells) > 2 else 0,
                        "stock": _parse_int(cells[3]) or 0 if len(cells) > 3 else 0,
                    }
                )
        return options
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
        log.debug("[detail_collector] 옵션 추출 실패: %s", e)
        return []


# ── 내부: 셀렉터 헬퍼 ────────────────────────────────────────────────────────


def _try_sel(page: Page, sels: list[str]) -> bool:
    for sel in sels:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
            pass
    return False


def _get_text(page: Page, sels: list[str]) -> str | None:
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                txt = el.inner_text(timeout=2000).strip()
                if txt:
                    return txt
        except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
            pass
    return None


def _get_input_value(page: Page, sels: list[str]) -> str | None:
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                val = el.input_value(timeout=2000).strip()
                if val:
                    return val
        except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
            pass
    return None


def _get_img_src(page: Page, sels: list[str]) -> str | None:
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                src = el.get_attribute("src", timeout=2000)
                if src:
                    return src
        except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
            pass
    return None


def _get_img_src_list(page: Page, sels: list[str]) -> list[str]:
    for sel in sels:
        try:
            els = page.locator(sel).all()
            srcs = [el.get_attribute("src") or "" for el in els]
            srcs = [s for s in srcs if s]
            if srcs:
                return srcs
        except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
            pass
    return []


def _parse_int(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = re.sub(r"[^\d]", "", str(val))
    return int(cleaned) if cleaned else None


def _parse_float(val: str | None) -> float | None:
    if not val:
        return None
    m = re.search(r"[\d.]+", str(val))
    try:
        return float(m.group()) if m else None
    except Exception:  # noqa: BLE001 - 스마트스토어 상품 상세 읽기전용 수집기(캐시 포함) - 실패시 error dict, None 또는 빈 리스트를 반환, 쓰기 없음
        return None


# ── 캐시 저장 ────────────────────────────────────────────────────────────────


def _save_cache(product_id: str, product: dict) -> None:
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    p = PRODUCTS_DIR / f"{product_id}.json"
    p.write_text(json.dumps(product, ensure_ascii=False, indent=2), encoding="utf-8")
