"""스마트스토어 상품 등록 폼 — 섹션별 모듈 (L3 Connector).

상품 등록 페이지 (#/products/create) 18개 섹션을 각각 클래스로 분리.
각 클래스는 독립적으로 사용하거나 FormRunner를 통해 통합 실행.

사용:
    from scripts.naver.smartstore.product.register_form import (
        CategorySection, ProductNameSection, PriceSection,
        StockSection, ImageSection, DescriptionSection,
    )
    cat  = CategorySection(page)
    cat.set("패션의류 > 상의 > 티셔츠")

    name = ProductNameSection(page)
    name.set("프리미엄 코튼 반팔 티셔츠")
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import Page

from scripts.common.logger import get_logger
from scripts.naver.smartstore.product import page_selectors as SEL

_log = get_logger(__name__)


# ── 공통 베이스 ───────────────────────────────────────────────────────────────


class FormSection:
    """폼 섹션 공통 기반."""

    section_name: str = "unknown"

    def __init__(self, page: Page):
        self.page = page

    def _scroll_to(self, sel: str) -> None:
        try:
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center', behavior: 'smooth'}});
            }})();
            """)
            time.sleep(0.3)
        except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass

    def _fill(self, sels: list[str], value: str, label: str = "") -> dict:
        """input/textarea 안전 입력 — Angular 이벤트 포함."""
        for sel in sels:
            try:
                self._scroll_to(sel)
                el = self.page.locator(sel).first
                if not (el.count() > 0 and el.is_visible(timeout=2000)):
                    continue
                el.click(click_count=3, timeout=3000, force=True)
                el.fill(str(value), timeout=5000, force=True)
                # Angular 이벤트 발생
                self.page.evaluate(f"""
                (() => {{
                    const el = document.querySelector('{sel}');
                    if (!el) return;
                    ['input','change','blur'].forEach(ev =>
                        el.dispatchEvent(new Event(ev, {{bubbles: true}})));
                }})();
                """)
                time.sleep(0.3)
                _log.info("[%s] %s 입력 완료: %s", self.section_name, label or sel, str(value)[:40])
                return {"ok": True, "selector": sel}
            except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
                _log.debug("[%s] %s 입력 시도 실패 (%s): %s", self.section_name, label, sel, e)
        return {"ok": False, "error": f"{label} 입력 필드를 찾지 못했습니다", "tried": sels}

    def _click_radio(self, sel: str, label: str = "") -> dict:
        """라디오 버튼 클릭 — 숨겨진 커스텀 라디오 3단계 fallback.

        1) Playwright 직접 클릭
        2) label[for=id] JS click (table-cell 등 숨겨진 label 처리)
        3) 입력 요소에 JS dispatchEvent (change+click) 직접 발생
        """
        try:
            self._scroll_to(sel)
            el = self.page.locator(sel).first
            if el.count() == 0:
                return {"ok": False, "error": f"{label} 라디오 요소 없음 ({sel})"}

            clicked = False

            # 1) 일반 클릭
            if not clicked:
                clicked = self._radio_click_plain(el)

            # 2) label JS click (table-cell / 숨겨진 label)
            if not clicked:
                clicked = self._radio_click_label(sel)

            # 3) JS dispatchEvent 직접 발생 (최후 수단)
            if not clicked:
                clicked = self._radio_click_js(sel)

            if clicked:
                time.sleep(0.2)
                _log.info("[%s] %s 선택", self.section_name, label or sel)
                return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            _log.debug("[%s] 라디오 클릭 실패 (%s): %s", self.section_name, sel, e)
        return {"ok": False, "error": f"{label} 라디오 선택 실패"}

    def _radio_click_plain(self, el) -> bool:
        """1) Playwright 직접 클릭. 성공 시 True."""
        try:
            if el.is_visible(timeout=500):
                el.click(timeout=2000)
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
        return False

    def _radio_click_label(self, sel: str) -> bool:
        """2) label JS click (table-cell / 숨겨진 label). 성공 시 True."""
        try:
            done = self.page.evaluate(f"""
                    (() => {{
                        const inp = document.querySelector('{sel}');
                        if (!inp) return false;
                        const id = inp.id;
                        // 직접 연결된 label
                        const lbl = id ? document.querySelector('label[for="' + id + '"]') : null;
                        if (lbl) {{ lbl.click(); return true; }}
                        // 부모 label
                        const parentLbl = inp.closest('label');
                        if (parentLbl) {{ parentLbl.click(); return true; }}
                        // .seller-input-toggle 내 같은 위치 label (텍스트 매핑)
                        const wrap = inp.closest('.seller-input-toggle, .radio-group, .toggle-group');
                        if (wrap) {{
                            const labels = wrap.querySelectorAll('label');
                            const idx = [...wrap.querySelectorAll('input[type=radio]')].indexOf(inp);
                            if (idx >= 0 && labels[idx]) {{ labels[idx].click(); return true; }}
                        }}
                        return false;
                    }})()
                    """)
            if done:
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
        return False

    def _radio_click_js(self, sel: str) -> bool:
        """3) JS dispatchEvent 직접 발생 (최후 수단). 성공 시 True."""
        try:
            self.page.evaluate(f"""
                    (() => {{
                        const inp = document.querySelector('{sel}');
                        if (!inp) return;
                        inp.checked = true;
                        ['click','change','input'].forEach(ev =>
                            inp.dispatchEvent(new Event(ev, {{bubbles: true}}))
                        );
                    }})()
                    """)
            return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
        return False

    def _click_btn(self, sels: list[str], label: str = "") -> dict:
        for sel in sels:
            try:
                el = self.page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=2000):
                    el.click(timeout=3000)
                    time.sleep(0.5)
                    _log.info("[%s] 버튼 클릭: %s", self.section_name, label or sel)
                    return {"ok": True, "selector": sel}
            except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
                _log.debug("[%s] 버튼 클릭 실패 (%s): %s", self.section_name, sel, e)
        return {"ok": False, "error": f"{label} 버튼을 찾지 못했습니다"}

    def _is_visible(self, sels: list[str]) -> bool:
        for sel in sels:
            try:
                el = self.page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=500):
                    return True
            except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 1. 카테고리
# ══════════════════════════════════════════════════════════════════════════════


class CategorySection(FormSection):
    """카테고리 선택.

    사용:
        cat = CategorySection(page)
        cat.set("패션의류")               # 검색어로 첫 번째 결과 선택
        cat.set("패션의류", result_idx=2)  # n번째 결과 선택
    """

    section_name = "category"

    def set(self, keyword: str, result_idx: int = 0) -> dict:
        res = self._set_category_from_cache(keyword)
        if res is not None:
            return res

        # 1. 입력란 찾기 (캐시 미스 또는 캐시 없을 때)
        inp_sel = None
        for sel in SEL.CATEGORY_SEARCH_INPUT:
            el = self.page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=1000):
                inp_sel = sel
                break
        if not inp_sel:
            return {"ok": False, "error": "카테고리 검색 입력 필드를 찾지 못했습니다"}

        err = self._enter_category_search(inp_sel, keyword)
        if err is not None:
            return err

        res = self._click_category_result(result_idx)
        if res is not None:
            return res

        res = self._category_keyboard_pick()
        if res is not None:
            return res

        return {"ok": False, "error": "카테고리 결과 항목을 클릭하지 못했습니다"}

    def _set_category_from_cache(self, keyword: str) -> dict | None:
        """0. 캐시에서 ID 조회 → 직접 주입. 성공 시 결과 dict, 아니면 None."""
        # 0. 캐시에서 ID 조회 → 직접 주입 (검색 생략)
        try:
            from scripts.naver.smartstore.product.category_cache import find_id, set_by_id

            cat_id = find_id(keyword)
            if cat_id:
                ok = set_by_id(self.page, cat_id)
                if ok:
                    _log.info("[category] 캐시 직접 선택: %s → id=%s", keyword, cat_id)
                    return {"ok": True, "selected": keyword, "id": cat_id, "method": "cache"}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            _log.debug("[category] 캐시 조회 실패, 검색으로 진행: %s", e)
        return None

    def _enter_category_search(self, inp_sel: str, keyword: str) -> dict | None:
        """2. 검색어 입력. 실패 시 에러 dict, 성공이면 None."""
        # 2. 검색어 입력 (force=True로 Selectize readonly 우회)
        try:
            # JS scrollIntoView로 뷰포트 안으로
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{inp_sel}');
                if (el) el.scrollIntoView({{behavior:'instant', block:'center'}});
            }})()
            """)
            time.sleep(0.3)

            el = self.page.locator(inp_sel).first
            el.fill(keyword, timeout=5000, force=True)

            # Angular + Selectize 이벤트 발생
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{inp_sel}');
                if (!el) return;
                ['input','focus','keyup','change'].forEach(ev =>
                    el.dispatchEvent(new Event(ev, {{bubbles:true}})));
                const sel = el.selectize;
                if (sel) {{ sel.onSearchChange('{keyword}'); }}
            }})()
            """)
            time.sleep(1.2)  # 결과 로드 대기
            _log.info("[category] 카테고리 검색 입력 완료: %s", keyword)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"카테고리 검색 입력 실패: {e}"}
        return None

    def _click_category_result(self, result_idx: int) -> dict | None:
        """3-A. Playwright locator로 결과 클릭. 성공 시 결과 dict, 아니면 None."""
        result_sels = SEL.CATEGORY_RESULT_ITEM

        # 3-A. Playwright locator로 클릭
        for sel in result_sels:
            try:
                items = self.page.locator(sel)
                cnt = items.count()
                if cnt > result_idx:
                    target = items.nth(result_idx)
                    txt = ""
                    # 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                    with contextlib.suppress(Exception):
                        txt = target.inner_text(timeout=500)[:80].strip()
                    if txt and len(txt) < 100:
                        target.click(timeout=3000, force=True)
                        time.sleep(0.5)
                        _log.info("[category] 카테고리 선택 완료: %s", txt[:30])
                        return {"ok": True, "selected": txt}
            except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        return None

    def _category_keyboard_pick(self) -> dict | None:
        """3-B. 키보드 탐색 fallback (ArrowDown + Enter). 성공 시 결과 dict, 아니면 None."""
        try:
            self.page.keyboard.press("ArrowDown")
            time.sleep(0.3)
            self.page.keyboard.press("Enter")
            time.sleep(0.8)
            _log.info("[category] 카테고리 ArrowDown+Enter 선택")
            return {"ok": True, "selected": "(ArrowDown)"}
        except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
        return None

    def get_selected(self) -> str | None:
        for sel in SEL.CATEGORY_PATH_DISPLAY:
            try:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    return el.inner_text(timeout=2000).strip()
            except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 3. 예약구매
# ══════════════════════════════════════════════════════════════════════════════


class PreOrderSection(FormSection):
    """예약구매 설정."""

    section_name = "pre_order"

    def disable(self) -> dict:
        return self._click_radio(SEL.PRE_ORDER_OFF, "예약구매 설정안함")

    def enable(self, start: str = "", end: str = "") -> dict:
        r = self._click_radio(SEL.PRE_ORDER_ON, "예약구매 설정함")
        if not r["ok"]:
            return r
        if start:
            self._fill([SEL.PRE_ORDER_START], start, "예약구매 시작일")
        if end:
            self._fill([SEL.PRE_ORDER_END], end, "예약구매 종료일")
        return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 4. 상품명
# ══════════════════════════════════════════════════════════════════════════════


class ProductNameSection(FormSection):
    """상품명 입력 (최대 100자)."""

    section_name = "product_name"

    def set(self, name: str) -> dict:
        if len(name) > 100:
            return {"ok": False, "error": f"상품명 100자 초과: {len(name)}자"}
        return self._fill(SEL.PRODUCT_NAME, name, "상품명")

    def get(self) -> str | None:
        for sel in SEL.PRODUCT_NAME:
            try:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    return el.input_value(timeout=2000).strip() or None
            except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 5. 판매가
# ══════════════════════════════════════════════════════════════════════════════


class PriceSection(FormSection):
    """판매가 / 정가 설정."""

    section_name = "price"

    def set_sale_price(self, price: int) -> dict:
        if price < 10:
            return {"ok": False, "error": f"판매가 최소 10원: {price}"}
        return self._fill(SEL.SALE_PRICE, str(price), "판매가")

    def set_original_price(self, price: int) -> dict:
        return self._fill(SEL.ORIGINAL_PRICE, str(price), "정가")

    def set(self, sale_price: int, original_price: int | None = None) -> dict:
        r = self.set_sale_price(sale_price)
        if not r["ok"]:
            return r
        if original_price is not None:
            self.set_original_price(original_price)
        return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 6. 즉시할인
# ══════════════════════════════════════════════════════════════════════════════


class DiscountSection(FormSection):
    """즉시할인 설정."""

    section_name = "discount"

    def enable(self) -> dict:
        return self._click_radio(SEL.DISCOUNT_ON, "즉시할인 설정함")

    def disable(self) -> dict:
        return self._click_radio(SEL.DISCOUNT_OFF, "즉시할인 설정안함")


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 7. 부가세
# ══════════════════════════════════════════════════════════════════════════════


class TaxSection(FormSection):
    """부가세 설정."""

    section_name = "tax"

    TAX_MAP: ClassVar[dict] = {
        "과세": SEL.TAX_TAXABLE,
        "TAX": SEL.TAX_TAXABLE,
        "면세": SEL.TAX_EXEMPT,
        "FREE": SEL.TAX_EXEMPT,
        "영세": SEL.TAX_ZERO,
        "SMALL": SEL.TAX_ZERO,
    }

    def set(self, tax_type: str = "과세") -> dict:
        sel = self.TAX_MAP.get(tax_type)
        if not sel:
            return {"ok": False, "error": f"알 수 없는 부가세 유형: {tax_type}"}
        return self._click_radio(sel, f"부가세 {tax_type}")


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 8. 재고수량
# ══════════════════════════════════════════════════════════════════════════════


class StockSection(FormSection):
    """재고수량 / 최소·최대 구매수량."""

    section_name = "stock"

    def set_stock(self, qty: int) -> dict:
        if qty < 0:
            return {"ok": False, "error": "재고는 0 이상"}
        return self._fill(SEL.STOCK, str(qty), "재고수량")

    def set_min_purchase(self, qty: int) -> dict:
        return self._fill(SEL.MIN_PURCHASE, str(qty), "최소구매수량")

    def set_max_purchase(self, qty: int) -> dict:
        return self._fill(SEL.MAX_PURCHASE, str(qty), "최대구매수량")

    def set(self, stock: int, min_purchase: int = 1, max_purchase: int | None = None) -> dict:
        r = self.set_stock(stock)
        if not r["ok"]:
            return r
        self.set_min_purchase(min_purchase)
        if max_purchase is not None:
            self.set_max_purchase(max_purchase)
        return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 9. 옵션
# ══════════════════════════════════════════════════════════════════════════════


class OptionSection(FormSection):
    """판매옵션 설정 (단독형 기준).

    사용:
        opt = OptionSection(page)
        opt.disable()                         # 옵션 없음
        opt.add_single({"색상": ["블랙", "화이트"]})
    """

    section_name = "option"

    def disable(self) -> dict:
        return self._click_radio(SEL.OPTION_USE_OFF, "옵션 설정안함")

    def enable_single(self) -> dict:
        r = self._click_radio(SEL.OPTION_USE_ON, "옵션 설정함")
        if not r["ok"]:
            return r
        return self._click_radio(SEL.OPTION_SINGLE_TYPE, "단독형 옵션")

    def add_single(self, options: dict[str, list[str]]) -> dict:
        """단독형 옵션 추가.

        Args:
            options: {"옵션명": ["값1", "값2", ...]} 형태
        """
        r = self.enable_single()
        if not r["ok"]:
            return r

        results = []
        for opt_name, values in options.items():
            # 옵션명 입력
            r_name = self._fill([SEL.OPTION_NAME_INPUT], opt_name, "옵션명")
            if not r_name["ok"]:
                results.append({"name": opt_name, "ok": False, "error": r_name["error"]})
                continue

            for val in values:
                r_val = self._fill([SEL.OPTION_VALUE_INPUT], val, "옵션값")  # noqa: F841
                # Enter로 값 추가
                try:
                    self.page.locator(SEL.OPTION_VALUE_INPUT).first.press("Enter")
                    time.sleep(0.3)
                except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                    pass

            results.append({"name": opt_name, "values": values, "ok": True})

        # 옵션 적용 버튼
        self._click_btn(SEL.OPTION_APPLY_BTN, "옵션 적용")
        return {"ok": True, "options": results}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 10. 대표이미지 / 섹션 11. 추가이미지
# ══════════════════════════════════════════════════════════════════════════════


class ImageSection(FormSection):
    """이미지 업로드 (대표이미지 / 추가이미지).

    사용:
        img = ImageSection(page)
        img.upload_main("C:/images/product_main.jpg")
        img.upload_additional(["C:/images/extra1.jpg", "C:/images/extra2.jpg"])
    """

    section_name = "image"

    def upload_main(self, image_path: str) -> dict:
        return self._upload_file(image_path, label="대표이미지", context_hint="representative")

    def upload_additional(self, image_paths: list[str]) -> dict:
        results = []
        for path in image_paths:
            r = self._upload_file(path, label="추가이미지", context_hint="additional")
            results.append({"path": path, **r})
            time.sleep(1)
        ok_count = sum(1 for r in results if r.get("ok"))
        return {"ok": ok_count > 0, "uploaded": ok_count, "results": results}

    def _upload_file(self, image_path: str, label: str = "이미지", context_hint: str = "") -> dict:
        p = Path(image_path)
        if not p.exists():
            return {"ok": False, "error": f"파일 없음: {image_path}"}

        # 파일 input 탐색 (context_hint 주변에서 우선 탐색)
        file_inputs = self.page.locator('input[type="file"]')
        count = file_inputs.count()
        if count == 0:
            return {"ok": False, "error": "파일 업로드 input 없음"}

        # 대표이미지는 첫 번째, 추가이미지는 두 번째 파일 input
        idx = 0 if context_hint == "representative" else (1 if count > 1 else 0)
        try:
            file_inputs.nth(idx).set_input_files(str(p), timeout=10000)
            time.sleep(2)
            _log.info("[image] %s 업로드: %s", label, p.name)
            return {"ok": True, "filename": p.name}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            _log.warning("[image] %s 업로드 실패: %s", label, e)
            return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 12. 동영상
# ══════════════════════════════════════════════════════════════════════════════


class VideoSection(FormSection):
    """동영상 타이틀 / URL 입력."""

    section_name = "video"

    def set(self, title: str = "", url: str = "") -> dict:
        results = {}
        if title:
            results["title"] = self._fill(SEL.VIDEO_TITLE, title, "동영상 타이틀")
        if url:
            results["url"] = self._fill(SEL.VIDEO_URL, url, "동영상 URL")
        return {"ok": True, **results}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 13. 상세설명
# ══════════════════════════════════════════════════════════════════════════════


class DescriptionSection(FormSection):
    """상세설명 — SmartEditorSession 연결 진입점.

    모드:
      - "smart_editor": SmartEditorSession 전체 기능 사용
      - "ai":           네이버 AI 상품설명 자동 생성
      - "direct":       textarea 직접 입력 (fallback)

    에디터 전체 기능은 SmartEditorSession 을 직접 사용:
        from scripts.naver.smartstore.product.description_editor import SmartEditorSession
        ed = SmartEditorSession(page)
        ed.open()
        ed.block.insert_image_file("/tmp/main.jpg")
        ed.text.bold()
        ed.write_text("상품 특징...")
        ed.submit()
    """

    section_name = "description"

    @property
    def editor(self):
        """SmartEditorSession 인스턴스 (lazy)."""
        if not hasattr(self, "_editor"):
            from scripts.naver.smartstore.product.description_editor import SmartEditorSession

            self._editor = SmartEditorSession(self.page)
        return self._editor

    def open_smart_editor(self) -> dict:
        """스마트에디터 ONE 열기 → SmartEditorSession 진입."""
        ok = self.editor.open(from_register_form=True)
        return {"ok": ok}

    def open_ai_writer(self) -> dict:
        """AI 상품설명 작성하기 열기."""
        return self.editor.ai.open()

    def write_direct(self, text: str) -> dict:
        """직접 텍스트 입력 (에디터 미사용, fallback)."""
        return self._fill(SEL.DESCRIPTION_TEXT, text, "상세설명")

    def write_via_editor(self, content: str) -> dict:
        """스마트에디터로 텍스트 입력 (단순 텍스트)."""
        r = self.open_smart_editor()
        if not r["ok"]:
            return self.write_direct(content)
        return self.editor.write_text(content)

    def write_html(self, html: str) -> dict:
        """HTML 블록으로 상세설명 입력."""
        r = self.open_smart_editor()
        if not r["ok"]:
            return r
        return self.editor.block.insert_html(html)

    def write_with_images(self, text: str, image_paths: list[str]) -> dict:
        """텍스트 + 이미지 혼합 입력."""
        r = self.open_smart_editor()
        if not r["ok"]:
            return r
        results = {}
        results["text"] = self.editor.write_paragraph(text)
        for path in image_paths:
            results[f"img_{path}"] = self.editor.block.insert_image_file(path)
        return {"ok": True, **results}

    def write_ai(self, keywords: list[str]) -> dict:
        """네이버 자체 AI로 상품설명 자동 생성 + 적용 (Beta)."""
        return self.editor.ai.generate_and_apply(keywords)

    def write_claude(self, product: dict, image_paths: list[str] | None = None) -> dict:
        """Claude API로 HTML 상세설명 자동 생성 + SmartEditor 입력.

        Args:
            product: {name, category, features, keywords, target,
                      brand, price, specs, notice, style}
            image_paths: 에디터에 함께 삽입할 이미지 경로 목록

        Returns:
            {"ok": bool, "html": str, "inserted": bool}
        """
        from scripts.naver.smartstore.product.ai_description_writer import AIDescriptionWriter

        writer = AIDescriptionWriter(page=self.page)
        return writer.write(product, image_paths=image_paths)


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 14. 상품 주요정보
# ══════════════════════════════════════════════════════════════════════════════


class ProductInfoSection(FormSection):
    """원산지, 브랜드, 제조사, 상품 상태."""

    section_name = "product_info"

    def set_brand(self, brand: str) -> dict:
        return self._fill(SEL.BRAND_INPUT, brand, "브랜드")

    def set_manufacturer(self, manufacturer: str) -> dict:
        return self._fill(SEL.MANUFACTURER_INPUT, manufacturer, "제조사")

    def set_origin(self, origin: str) -> dict:
        return self._fill(SEL.ORIGIN_INPUT, origin, "원산지")

    def set_new(self) -> dict:
        return self._click_radio(SEL.PRODUCT_TYPE_NEW, "신상품")

    def set_used(self) -> dict:
        return self._click_radio(SEL.PRODUCT_TYPE_USED, "중고상품")

    def set_self_made(self, enabled: bool = True) -> dict:
        try:
            el = self.page.locator(SEL.PRODUCT_SELF_MADE).first
            if el.count() > 0:
                checked = el.is_checked(timeout=1000)
                if checked != enabled:
                    el.click(timeout=2000)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}

    def set(
        self,
        brand: str = "",
        manufacturer: str = "",
        origin: str = "",
        product_type: str = "신상품",
        self_made: bool = False,
    ) -> dict:
        if brand:
            self.set_brand(brand)
        if manufacturer:
            self.set_manufacturer(manufacturer)
        if origin:
            self.set_origin(origin)
        if product_type == "중고상품":
            self.set_used()
        else:
            self.set_new()
        if self_made:
            self.set_self_made(True)
        return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 15. 사이즈
# ══════════════════════════════════════════════════════════════════════════════


class SizeSection(FormSection):
    """사이즈 설정."""

    section_name = "size"

    def disable(self) -> dict:
        return self._click_radio(SEL.SIZE_OFF, "사이즈 설정안함")

    def enable(self) -> dict:
        return self._click_radio(SEL.SIZE_ON, "사이즈 설정함")


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 17. 검색설정 (키워드 태그)
# ══════════════════════════════════════════════════════════════════════════════


class SearchTagSection(FormSection):
    """검색 태그 / 키워드 설정.

    사용:
        tag = SearchTagSection(page)
        tag.set(["LED 조명", "무드등", "침실 조명"])
    """

    section_name = "search_tag"

    def set(self, keywords: list[str]) -> dict:
        results = []
        for kw in keywords[:20]:  # 네이버 최대 20개
            r = self._fill(SEL.SEARCH_KEYWORD_INPUT, kw, "키워드")
            if r["ok"]:
                try:
                    self.page.locator(SEL.SEARCH_KEYWORD_INPUT[0]).first.press("Enter")
                    time.sleep(0.3)
                except Exception:  # noqa: BLE001 - 여러 셀렉터/클릭 방법을 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                    pass
            results.append({"keyword": kw, "ok": r["ok"]})
        ok_count = sum(1 for r in results if r["ok"])
        return {"ok": ok_count > 0, "added": ok_count, "results": results}


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 18. 노출채널
# ══════════════════════════════════════════════════════════════════════════════


class ChannelSection(FormSection):
    """노출채널 설정 (스마트스토어 / 네이버쇼핑)."""

    section_name = "channel"

    def set_display_on(self) -> dict:
        return self._click_radio(SEL.CHANNEL_DISPLAY_ON, "전시중")

    def set_display_off(self) -> dict:
        return self._click_radio(SEL.CHANNEL_DISPLAY_OFF, "전시중지")

    def enable_naver_shopping(self) -> dict:
        try:
            el = self.page.locator(SEL.CHANNEL_NAVER_SHOP).first
            if el.count() > 0 and not el.is_checked(timeout=1000):
                el.click(timeout=2000)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 필드 공용 헬퍼 — 여러 셀렉터/입력값을 순차 시도하고 실패는 {ok: False, error} 로 반환, 결제·삭제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)}

    def set(self, display: bool = True, naver_shopping: bool = True) -> dict:
        if display:
            self.set_display_on()
        else:
            self.set_display_off()
        if naver_shopping:
            self.enable_naver_shopping()
        return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 저장 / 임시저장
# ══════════════════════════════════════════════════════════════════════════════


class SaveSection(FormSection):
    """저장 / 임시저장 / 미리보기."""

    section_name = "save"

    def temp_save(self) -> dict:
        return self._click_btn(SEL.BTN_TEMP_SAVE, "임시저장")

    def save(self, require_confirm: bool = True) -> dict:
        if require_confirm:
            answer = input("[SaveSection] 실제 저장하시겠습니까? (yes 입력): ").strip()
            if answer.lower() != "yes":
                return {"ok": False, "reason": "사용자 취소"}
        return self._click_btn(SEL.BTN_SAVE, "저장하기")

    def preview(self) -> dict:
        return self._click_btn(SEL.BTN_PREVIEW, "미리보기")

    def cancel(self) -> dict:
        return self._click_btn(SEL.BTN_CANCEL, "취소")
