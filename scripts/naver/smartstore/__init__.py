"""네이버 스마트스토어 셀러센터 자동화 (SPA 해시 라우팅 대응).

URL: https://sell.smartstore.naver.com/

13개 좌측 메뉴 영역:
  상품관리 / 판매관리 / 정산관리 / 문의·리뷰관리 / 스토어관리 / 혜택·마케팅
  N배송관리 / 커머스솔루션 / 데이터분석 / 광고관리(접근불가) / 프로모션관리
  쇼핑커넥트 / 판매자정보

사용:
  from scripts.naver import NaverServices
  n = NaverServices(page)
  n.login()
  n.smartstore.open_dashboard()                 # 대시보드
  n.smartstore.list_products(limit=30)          # 상품 목록
  n.smartstore.list_orders(status="결제완료")     # 주문 목록
  n.smartstore.list_reviews(limit=20)           # 리뷰
  n.smartstore.list_inquiries()                 # 문의
  n.smartstore.list_settlements()               # 정산
  n.smartstore.stats(period="today")            # 통계
"""
from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical
from scripts.popup_detector import handle_page_popups, close_popup_windows
from scripts.naver.auth import ensure_naver_login
from scripts.site_session_safety import assert_session_integrity

_log = get_logger(__name__)

SELLER_BASE = "https://sell.smartstore.naver.com"
DASHBOARD_URL = f"{SELLER_BASE}/#/home/dashboard"


# ── 좌측 사이드바 메뉴 라벨 ─────────────────────────────────────────────────
MENU_LABELS = {
    "products": "상품관리",
    "orders": "판매관리",
    "settlement": "정산관리",
    "reviews": "문의/리뷰관리",
    "store": "스토어관리",
    "marketing": "혜택/마케팅",
    "delivery": "N배송 관리",
    "solution": "커머스솔루션",
    "stats": "데이터분석",
    "ads": "광고관리",
    "promo": "프로모션 관리",
    "connect": "쇼핑 커넥트",
    "seller": "판매자 정보",
}


class NaverSmartStore:
    """스마트스토어 셀러센터 통합 API."""

    def __init__(self, page: Page):
        self.page = page

    # ── 초기화 ──────────────────────────────────────────────────────────

    def open_dashboard(self) -> bool:
        """셀러센터 대시보드 진입."""
        r = ensure_naver_login(self.page, return_url=DASHBOARD_URL)
        assert_session_integrity(r, site="smartstore", workflow="dashboard")
        if not r.get("ok"):
            return False
        self.page.goto(DASHBOARD_URL, timeout=20000, wait_until="domcontentloaded")
        time.sleep(4)
        try:
            handle_page_popups(self.page, timeout_s=2.0)
            close_popup_windows(self.page)
        except Exception:
            pass
        return True

    # ── 메뉴 클릭 (SPA) ──────────────────────────────────────────────────

    def _click_menu(self, label: str, wait_s: float = 3.0) -> bool:
        """좌측 사이드바 메뉴 클릭 → 페이지 변화 대기."""
        before_url = self.page.url
        try:
            clicked = self.page.evaluate(r"""
            (label) => {
                const isVisible = (el) => {
                    const s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                // 좌측 영역(x<280) 메뉴 우선
                for (const el of document.querySelectorAll('a, button, li, [role=menuitem]')) {
                    if (!isVisible(el)) continue;
                    const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                    if (t === label) {
                        const r = el.getBoundingClientRect();
                        if (r.x < 280) { el.click(); return true; }
                    }
                }
                // fallback
                for (const el of document.querySelectorAll('a, button, li')) {
                    if (!isVisible(el)) continue;
                    const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
                    if (t === label) { el.click(); return true; }
                }
                return false;
            }
            """, label)
            if not clicked:
                return False
            deadline = time.time() + wait_s
            while time.time() < deadline:
                if self.page.url != before_url:
                    break
                time.sleep(0.3)
            time.sleep(1.5)
            return True
        except Exception as e:
            _log.debug("[smartstore] 메뉴 클릭 실패 (%s): %s", label, e)
            return False

    def _ensure_section(self, section_key: str) -> bool:
        """대시보드에서 시작 → 메뉴 클릭 → 해당 섹션 진입."""
        if not self.open_dashboard():
            return False
        label = MENU_LABELS.get(section_key)
        if not label:
            return False
        return self._click_menu(label)

    # ── 데이터 추출 공통 ─────────────────────────────────────────────────

    EXTRACT_TABLE_JS = r"""
    (limit) => {
        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        // 표시된 모든 테이블 중 행이 가장 많은 것
        let best = null;
        let bestRows = 0;
        document.querySelectorAll('table').forEach(t => {
            if (!isVisible(t)) return;
            const rows = t.querySelectorAll('tbody tr').length;
            if (rows > bestRows) { bestRows = rows; best = t; }
        });
        if (!best) return {headers: [], rows: []};

        const headers = Array.from(best.querySelectorAll('thead th, thead td'))
            .map(h => (h.innerText || '').trim().substring(0, 30));
        const rows = [];
        const trs = best.querySelectorAll('tbody tr');
        for (let i = 0; i < Math.min(trs.length, limit); i++) {
            const cells = Array.from(trs[i].querySelectorAll('td'))
                .map(c => (c.innerText || '').trim().substring(0, 200));
            if (cells.length) rows.push(cells);
        }
        return {headers, rows};
    }
    """

    def _extract_visible_table(self, limit: int = 50) -> dict:
        """현재 페이지의 가장 큰 테이블 추출."""
        try:
            return self.page.evaluate(self.EXTRACT_TABLE_JS, limit)
        except Exception as e:
            _log.error("[smartstore] 테이블 추출 실패: %s", e)
            return {"headers": [], "rows": []}

    # ── 상품 관리 ────────────────────────────────────────────────────────

    def list_products(self, limit: int = 50) -> dict:
        """판매 상품 목록."""
        if not self._ensure_section("products"):
            return {"ok": False, "error": "section_open_failed"}
        log_critical("OTHER", "스마트스토어 상품 목록 조회", limit=limit)
        return {"ok": True, **self._extract_visible_table(limit)}

    def open_product_register(self) -> bool:
        """상품 등록 페이지 진입 (작성은 사용자가 직접)."""
        if not self._ensure_section("products"):
            return False
        for label in ["상품 등록", "상품등록", "신규 상품"]:
            if self._click_menu(label):
                _log.info("[smartstore] 상품 등록 페이지 진입")
                return True
        return False

    @property
    def product_register(self):
        """ProductRegister (그룹상품) 인스턴스."""
        if not hasattr(self, "_product_register") or self._product_register is None:
            from scripts.naver.smartstore.product import ProductRegister
            self._product_register = ProductRegister(self.page)
        return self._product_register

    @property
    def general_product(self):
        """GeneralProductRegister (일반 상품, 가격/재고 포함) 인스턴스."""
        if not hasattr(self, "_general_product") or self._general_product is None:
            from scripts.naver.smartstore.general_product import GeneralProductRegister
            self._general_product = GeneralProductRegister(self.page)
        return self._general_product

    def register_general_product(self, data: dict, save_after: bool = False,
                                 require_confirm: bool = True) -> dict:
        """원샷 일반 상품 등록 (가격/재고 포함).

        data: {name, price, stock, category, main_image, ...}
        """
        return self.general_product.register_product(
            data, save_after=save_after, require_confirm=require_confirm
        )

    @property
    def bulk_register(self):
        """일괄 등록 인스턴스 (재시도 + DB 기록 + 진행 보고)."""
        if not hasattr(self, "_bulk_register") or self._bulk_register is None:
            from scripts.naver.smartstore.bulk import BulkRegister
            self._bulk_register = BulkRegister(self.page)
        return self._bulk_register

    def register_bulk(self, products: list[dict], product_type: str = "general",
                      save_after: bool = False, require_confirm: bool = False,
                      max_retries: int = 2, stop_on_error: bool = False,
                      on_progress=None) -> dict:
        """일괄 상품 등록.

        Args:
            products: 상품 dict 리스트
            product_type: "general" / "group"
            save_after: 등록 후 저장
            require_confirm: 저장 전 확인
            max_retries: 재시도 횟수
            stop_on_error: 첫 실패시 중단
            on_progress: callable(i, total, result) 진행 콜백
        """
        return self.bulk_register.register_all(
            products, product_type=product_type, save_after=save_after,
            require_confirm=require_confirm, max_retries=max_retries,
            stop_on_error=stop_on_error, on_progress=on_progress,
        )

    def register_history(self, limit: int = 50, ok_only: bool = False) -> list[dict]:
        """DB에서 등록 이력 조회."""
        from scripts.naver.smartstore.bulk import get_register_history
        return get_register_history(limit=limit, ok_only=ok_only)

    @property
    def smart_editor(self):
        """SmartEditor ONE wrapper."""
        if not hasattr(self, "_smart_editor") or self._smart_editor is None:
            from scripts.naver.smartstore.advanced import SmartEditorONE
            self._smart_editor = SmartEditorONE(self.page)
        return self._smart_editor

    @property
    def price_stock(self):
        """가격/재고/배송 wrapper."""
        if not hasattr(self, "_price_stock") or self._price_stock is None:
            from scripts.naver.smartstore.advanced import PriceStockEditor
            self._price_stock = PriceStockEditor(self.page)
        return self._price_stock

    @property
    def product_option(self):
        """판매옵션 wrapper."""
        if not hasattr(self, "_product_option") or self._product_option is None:
            from scripts.naver.smartstore.advanced import ProductOptionEditor
            self._product_option = ProductOptionEditor(self.page)
        return self._product_option

    def register_product(self, data: dict, save_after: bool = False,
                         require_confirm: bool = True) -> dict:
        """원샷 상품 등록.

        Args:
            data: 상품 정보 dict (smartstore_product.ProductRegister.register_product 참조)
            save_after: True면 마지막에 저장 시도
            require_confirm: 저장 전 input() 확인
        """
        return self.product_register.register_product(
            data, save_after=save_after, require_confirm=require_confirm
        )

    # ── 판매 관리 (주문) ─────────────────────────────────────────────────

    def list_orders(self, limit: int = 50) -> dict:
        """주문 목록."""
        if not self._ensure_section("orders"):
            return {"ok": False, "error": "section_open_failed"}
        log_critical("OTHER", "스마트스토어 주문 목록 조회", limit=limit)
        return {"ok": True, **self._extract_visible_table(limit)}

    # ── 정산 관리 ────────────────────────────────────────────────────────

    def list_settlements(self, limit: int = 50) -> dict:
        """정산 내역."""
        if not self._ensure_section("settlement"):
            return {"ok": False, "error": "section_open_failed"}
        log_critical("OTHER", "스마트스토어 정산 내역 조회", limit=limit)
        return {"ok": True, **self._extract_visible_table(limit)}

    # ── 문의/리뷰 ────────────────────────────────────────────────────────

    def list_reviews(self, limit: int = 50) -> dict:
        """고객 리뷰."""
        if not self._ensure_section("reviews"):
            return {"ok": False, "error": "section_open_failed"}
        log_critical("OTHER", "스마트스토어 리뷰 조회", limit=limit)
        return {"ok": True, **self._extract_visible_table(limit)}

    def list_inquiries(self, limit: int = 50) -> dict:
        """고객 문의."""
        if not self._ensure_section("reviews"):
            return {"ok": False, "error": "section_open_failed"}
        # 리뷰관리 안에서 '문의' 하위 클릭 시도
        for label in ["문의 관리", "고객 문의", "1:1 문의"]:
            if self._click_menu(label):
                break
        return {"ok": True, **self._extract_visible_table(limit)}

    # ── 스토어 관리 ──────────────────────────────────────────────────────

    def store_info(self) -> dict:
        """스토어 기본 정보."""
        if not self._ensure_section("store"):
            return {"ok": False, "error": "section_open_failed"}
        try:
            info = self.page.evaluate("""
            () => {
                const txt = document.body?.innerText || '';
                return {
                    store_name: /스토어\\s*명\\s*[:\\s]\\s*([가-힣A-Za-z0-9_\\s]+)/.exec(txt)?.[1]?.trim() || '',
                    intro: /소개\\s*[:\\s]\\s*(.+)/.exec(txt)?.[1]?.trim().substring(0, 200) || '',
                    body_sample: txt.substring(0, 500),
                };
            }
            """)
            return {"ok": True, **info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 통계/분석 ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """매출/방문/구매 통계."""
        if not self._ensure_section("stats"):
            return {"ok": False, "error": "section_open_failed"}
        log_critical("OTHER", "스마트스토어 통계 조회")
        try:
            stats = self.page.evaluate("""
            () => {
                const out = {};
                const txt = document.body?.innerText || '';
                // 매출/방문/구매 등 숫자 추출
                const patterns = {
                    sales_today: /오늘\\s*매출\\s*[:\\s]*([\\d,]+)/,
                    sales_week:  /이번주\\s*매출\\s*[:\\s]*([\\d,]+)/,
                    sales_month: /이번달\\s*매출\\s*[:\\s]*([\\d,]+)/,
                    visitors_today: /오늘\\s*방문[\\s자]*[:\\s]*([\\d,]+)/,
                    orders_today: /오늘\\s*주문\\s*[:\\s]*([\\d,]+)/,
                };
                for (const k in patterns) {
                    const m = patterns[k].exec(txt);
                    if (m) out[k] = parseInt(m[1].replace(/,/g, ''));
                }
                return out;
            }
            """)
            return {"ok": True, **stats}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 마케팅/프로모션 ──────────────────────────────────────────────────

    def list_promotions(self, limit: int = 30) -> dict:
        """진행 중인 프로모션."""
        if not self._ensure_section("promo"):
            return {"ok": False, "error": "section_open_failed"}
        return {"ok": True, **self._extract_visible_table(limit)}

    def list_marketing(self, limit: int = 30) -> dict:
        """혜택/마케팅 (쿠폰/할인 등)."""
        if not self._ensure_section("marketing"):
            return {"ok": False, "error": "section_open_failed"}
        return {"ok": True, **self._extract_visible_table(limit)}

    # ── 판매자 정보 ──────────────────────────────────────────────────────

    def seller_info(self) -> dict:
        """판매자 기본 정보."""
        if not self._ensure_section("seller"):
            return {"ok": False, "error": "section_open_failed"}
        try:
            info = self.page.evaluate("""
            () => {
                const txt = document.body?.innerText || '';
                return {
                    body_sample: txt.substring(0, 1000),
                };
            }
            """)
            return {"ok": True, **info}
        except Exception as e:
            return {"ok": False, "error": str(e)}
