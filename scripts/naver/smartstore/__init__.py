"""네이버 스마트스토어 셀러센터 자동화 (SPA 해시 라우팅 대응).
# scripts/smartstore/ 통합 내용 포함 (scripts.smartstore.SmartStore 클래스)
#
# 서브모듈 구조:
#   product/      — models, product, general_product, advanced, bulk
#   registration/ — find_register_url, find_v2, product_analyzer, general_analyzer,
#                   general_full_analyze, diagnose, test_register
#   navigation/   — sidebar_expand, sidebar_v3, sitemap
#   api/          — actions, router

URL: https://sell.smartstore.naver.com/

13개 좌측 메뉴 영역:
  상품관리 / 판매관리 / 정산관리 / 문의·리뷰관리 / 스토어관리 / 혜택·마케팅
  N배송관리 / 커머스솔루션 / 데이터분석 / 광고관리(접근불가) / 프로모션관리
  쇼핑커넥트 / 판매자정보

사용:
  from scripts.naver.services import NaverServices
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

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups
from scripts.site_engine.site_session_safety import assert_session_integrity

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

    def _section_open_failed(self) -> dict:
        """섹션 진입 실패 응답 — 인증 게이트 사유(2FA/캡차 등)가 있으면 첨부해 표면화."""
        err = {"ok": False, "error": "section_open_failed"}
        la = getattr(self, "_last_auth", None)
        if isinstance(la, dict) and la.get("reason"):
            err["auth_reason"] = la.get("reason")
            err["needs_user"] = bool(la.get("needs_user"))
            if la.get("hint"):
                err["hint"] = la.get("hint")
        return err

    def open_dashboard(self) -> bool:
        """셀러센터 대시보드 진입."""
        r = ensure_naver_login(self.page, return_url=DASHBOARD_URL)
        assert_session_integrity(r, site="smartstore", workflow="dashboard")
        # 인증 게이트 사유(2FA/캡차 등)를 보관 → 섹션 실패 응답에 표면화
        self._last_auth = r if not r.get("ok") else None
        if not r.get("ok"):
            return False
        self.page.goto(DASHBOARD_URL, timeout=20000, wait_until="domcontentloaded")
        time.sleep(4)
        try:
            handle_page_popups(self.page, timeout_s=2.0)
            close_popup_windows(self.page)
        except Exception:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            pass
        return True

    # ── 메뉴 클릭 (SPA) ──────────────────────────────────────────────────

    def _click_menu(self, label: str, wait_s: float = 3.0) -> bool:
        """좌측 사이드바 메뉴 클릭 → 페이지 변화 대기."""
        before_url = self.page.url
        try:
            clicked = self.page.evaluate(
                r"""
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
            """,
                label,
            )
            if not clicked:
                return False
            deadline = time.time() + wait_s
            while time.time() < deadline:
                if self.page.url != before_url:
                    break
                time.sleep(0.3)
            time.sleep(1.5)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            _log.error("[smartstore] 테이블 추출 실패: %s", e)
            return {"headers": [], "rows": []}

    # 상품 목록은 <table> 이 아니라 ARIA 그리드(role=row/gridcell) — 표준 table 추출이 못 잡음.
    ARIA_GRID_JS = r"""
    (limit) => {
        const rows = [...document.querySelectorAll('[role=row]')];
        // 헤더: columnheader 가 가장 많은 행
        let headers = [];
        for (const r of rows) {
            const hs = [...r.querySelectorAll('[role=columnheader]')]
                .map(c => (c.innerText || '').replace(/\s+/g, ' ').trim().substring(0, 30)).filter(Boolean);
            if (hs.length > headers.length) headers = hs;
        }
        // 데이터 행: gridcell 중 8자리+ 숫자(상품번호) 포함하는 행
        const out = [];
        for (const r of rows) {
            const cells = [...r.querySelectorAll('[role=gridcell]')]
                .map(c => (c.innerText || '').replace(/\s+/g, ' ').trim().substring(0, 200)).filter(Boolean);
            if (!cells.length) continue;
            if (cells.some(c => /^\d{8,}$/.test(c))) {
                out.push(cells);
                if (out.length >= limit) break;
            }
        }
        return { headers, rows: out };
    }
    """

    def _extract_aria_grid(self, limit: int = 50) -> dict:
        """ag-Grid(가상스크롤) ARIA 그리드 — 뷰포트를 스크롤하며 상품 행을 누적 수집.

        ag-Grid 는 보이는 행만 DOM 렌더(virtualization)하므로, .ag-body-viewport 를
        내려가며 매 렌더 상태에서 role=gridcell 행을 모아 상품번호로 dedup 한다.
        """
        headers: list = []
        seen: dict = {}
        try:
            self.page.evaluate(
                "() => { const v = document.querySelector('.ag-body-viewport'); if (v) v.scrollTop = 0; }"
            )
            time.sleep(0.4)
            for _ in range(40):  # 스크롤 안전장치
                chunk = self.page.evaluate(self.ARIA_GRID_JS, 200) or {}
                if chunk.get("headers") and not headers:
                    headers = chunk["headers"]
                new = 0
                for row in chunk.get("rows", []):
                    pid = next((c for c in row if isinstance(c, str) and c.isdigit() and len(c) >= 8), None)
                    if pid and pid not in seen:
                        seen[pid] = row
                        new += 1
                if len(seen) >= limit:
                    break
                at_bottom = self.page.evaluate("""() => {
                    const v = document.querySelector('.ag-body-viewport');
                    if (!v) return true;
                    const b = v.scrollTop; v.scrollTop = b + v.clientHeight * 0.8;
                    return v.scrollTop <= b + 2;
                }""")
                time.sleep(0.55)
                if at_bottom and new == 0:
                    break
            return {"headers": headers, "rows": list(seen.values())[:limit]}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            _log.error("[smartstore] ARIA 그리드 스크롤 추출 실패: %s", e)
            return {"headers": headers, "rows": list(seen.values())[:limit]}

    def _open_products_list(self) -> bool:
        """상품 조회/수정 목록(origin-list) 진입 + 팝업 닫기 + 검색.

        상위 '상품관리' 메뉴 클릭은 서브메뉴만 펼치고 대시보드에 머무르므로,
        실제 목록 라우트(#/products/origin-list)로 직접 이동한다.
        """
        try:
            self.page.goto(
                "https://sell.smartstore.naver.com/#/products/origin-list", timeout=20000, wait_until="domcontentloaded"
            )
            time.sleep(4)
            try:
                handle_page_popups(self.page, timeout_s=2.0)
                close_popup_windows(self.page)
            except Exception:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
                pass
            # 잔여 안내 팝업(상품 등록 한도 등) 닫기
            self.page.evaluate(r"""(() => {
                document.querySelectorAll('button,a,span').forEach(e => {
                    const t = (e.textContent || '').trim();
                    if (/^(닫기|확인|오늘 하루 보지 않기)$/.test(t)) { try { e.click(); } catch (_) {} }
                });
            })()""")
            time.sleep(1)
            # 필터 보정: 검색 버튼 위쪽의 '전체'(판매상태·기간)를 모두 선택 → 일부만 보이던 문제 해결
            self.page.evaluate(r"""(() => {
                const sb = [...document.querySelectorAll('button,a')].find(e => (e.innerText || '').trim() === '검색');
                const limitY = sb ? sb.getBoundingClientRect().top : 99999;
                document.querySelectorAll('label,button,a,span').forEach(e => {
                    const t = (e.innerText || '').trim();
                    const r = e.getBoundingClientRect();
                    if (t === '전체' && r.top < limitY && r.width > 0 && r.height > 0) { try { e.click(); } catch (_) {} }
                });
            })()""")
            time.sleep(1)
            # 검색 → 목록 로드
            self.page.evaluate(r"""(() => {
                const b = [...document.querySelectorAll('button,a')]
                    .find(e => (e.innerText || '').trim() === '검색' && e.getBoundingClientRect().width > 0);
                if (b) b.click();
            })()""")
            time.sleep(3)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            _log.error("[smartstore] 상품목록 진입 실패: %s", e)
            return False

    # ── 상품 관리 ────────────────────────────────────────────────────────

    def list_products(self, limit: int = 50) -> dict:
        """판매 상품 목록 (origin-list, 전체 필터, ag-Grid 가상스크롤 수집)."""
        if not self.open_dashboard():  # 로그인 보장(+ 인증 게이트 사유 보관)
            return self._section_open_failed()
        if not self._open_products_list():
            return self._section_open_failed()
        log_critical("OTHER", "스마트스토어 상품 목록 조회", limit=limit)
        grid = self._extract_aria_grid(limit)  # 뷰포트 스크롤하며 전체 누적
        if not grid.get("rows"):
            grid = self._extract_visible_table(limit)  # 폴백(table 형 페이지)
        return {"ok": True, **grid}

    def open_product_register(self) -> bool:
        """상품 등록 페이지 진입.

        전략 1: GeneralProductRegister.open() (직접 URL + 사이드바 fallback)
        전략 2: #/products/new 직접 이동 후 팝업 처리
        """
        try:
            from scripts.naver.smartstore.product.general_product import GeneralProductRegister

            reg = GeneralProductRegister(self.page)
            if reg.open():
                _log.info("[smartstore] 상품 등록 페이지 진입 완료")
                return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            _log.warning("[smartstore] GeneralProductRegister.open 실패: %s — 직접 URL 시도", e)

        # 최후 fallback: 직접 URL 이동만
        try:
            from scripts.naver.smartstore.navigation.popup_handler import dismiss_all_popups

            self.page.goto(
                "https://sell.smartstore.naver.com/#/products/new", timeout=20000, wait_until="domcontentloaded"
            )
            time.sleep(4)
            dismiss_all_popups(self.page)
            _log.info("[smartstore] 상품 등록 URL 직접 이동: %s", self.page.url)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            _log.error("[smartstore] 상품 등록 진입 최종 실패: %s", e)
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

    def register_general_product(self, data: dict, save_after: bool = False, require_confirm: bool = True) -> dict:
        """원샷 일반 상품 등록 (가격/재고 포함).

        data: {name, price, stock, category, main_image, ...}
        """
        return self.general_product.register_product(data, save_after=save_after, require_confirm=require_confirm)

    @property
    def bulk_register(self):
        """일괄 등록 인스턴스 (재시도 + DB 기록 + 진행 보고)."""
        if not hasattr(self, "_bulk_register") or self._bulk_register is None:
            from scripts.naver.smartstore.bulk import BulkRegister

            self._bulk_register = BulkRegister(self.page)
        return self._bulk_register

    def register_bulk(  # noqa: PLR0913 - 공개 API 시그니처 유지(호출부 다수)
        self,
        products: list[dict],
        product_type: str = "general",
        save_after: bool = False,
        require_confirm: bool = False,
        max_retries: int = 2,
        stop_on_error: bool = False,
        on_progress=None,
    ) -> dict:
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
            products,
            product_type=product_type,
            save_after=save_after,
            require_confirm=require_confirm,
            max_retries=max_retries,
            stop_on_error=stop_on_error,
            on_progress=on_progress,
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

    def register_product(self, data: dict, save_after: bool = False, require_confirm: bool = True) -> dict:
        """원샷 상품 등록.

        Args:
            data: 상품 정보 dict (smartstore_product.ProductRegister.register_product 참조)
            save_after: True면 마지막에 저장 시도
            require_confirm: 저장 전 input() 확인
        """
        return self.product_register.register_product(data, save_after=save_after, require_confirm=require_confirm)

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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 화면 자동화 클래스 - 메뉴클릭/테이블추출/상품등록진입 등 UI 조작 헬퍼, 실패시 False 또는 빈 결과로 fail-closed 반환. 결제/삭제 없음
            return {"ok": False, "error": str(e)}


# ── SmartStore 통합 래퍼 (scripts/smartstore/ 통합) ──────────────────────────


class SmartStore:
    """스마트스토어 통합 진입점 — 모든 기능 하나의 객체로 접근.

    scripts/smartstore/__init__.py 에서 통합됨.
    기존 코드 호환성을 위해 이 클래스를 유지합니다.
    """

    def __init__(self, page):
        self.page = page
        self._store = None
        self._products = None
        self._general = None
        self._bulk = None
        self._orders = None
        self._inventory = None
        self._analytics = None
        self._csv = None
        self._ai = None
        self._seo = None
        self._competitor = None
        self._reviews = None
        self._image = None
        self._scheduler = None
        self._notifier = None
        self._error_recovery = None
        self._session = None

    @property
    def store(self):
        """대시보드/메뉴 조회 (NaverSmartStore)."""
        if self._store is None:
            self._store = NaverSmartStore(self.page)
        return self._store

    @property
    def products(self):
        """그룹상품 등록."""
        if self._products is None:
            from scripts.naver.smartstore.product import ProductRegister

            self._products = ProductRegister(self.page)
        return self._products

    @property
    def general(self):
        """일반 상품 등록 (가격/재고)."""
        if self._general is None:
            from scripts.naver.smartstore.general_product import GeneralProductRegister

            self._general = GeneralProductRegister(self.page)
        return self._general

    @property
    def bulk(self):
        """일괄 등록."""
        if self._bulk is None:
            from scripts.naver.smartstore.bulk import BulkRegister

            self._bulk = BulkRegister(self.page)
        return self._bulk

    @property
    def orders(self):
        """주문 자동 처리."""
        if self._orders is None:
            from .automation.order_automation import OrderAutomation

            self._orders = OrderAutomation(self.page)
        return self._orders

    @property
    def inventory(self):
        """재고 모니터링."""
        if self._inventory is None:
            from .automation.inventory_monitor import InventoryMonitor

            self._inventory = InventoryMonitor(self.page)
        return self._inventory

    @property
    def analytics(self):
        """매출/방문 분석 대시보드."""
        if self._analytics is None:
            from .automation.analytics_dashboard import AnalyticsDashboard

            self._analytics = AnalyticsDashboard(self.page)
        return self._analytics

    @property
    def csv(self):
        """CSV/Excel 일괄 가져오기."""
        if self._csv is None:
            from .automation.csv_import import CSVImporter

            self._csv = CSVImporter(self.page)
        return self._csv

    @property
    def reviews(self):
        """리뷰 자동 응답."""
        if self._reviews is None:
            from .automation.review_automation import ReviewAutoResponder

            self._reviews = ReviewAutoResponder(self.page)
        return self._reviews

    @property
    def ai(self):
        """AI 기반 응답/생성 (Claude/OpenAI)."""
        if self._ai is None:
            from scripts.naver.automation.integration.ai_responder import AIResponder

            self._ai = AIResponder()
        return self._ai

    @property
    def seo(self):
        """SEO 최적화."""
        if self._seo is None:
            from scripts.naver.automation.content.seo_optimizer import SEOOptimizer

            self._seo = SEOOptimizer(self.page)
        return self._seo

    @property
    def competitor(self):
        """경쟁사 분석."""
        if self._competitor is None:
            from .automation.competitor_analysis import CompetitorAnalysis

            self._competitor = CompetitorAnalysis(self.page)
        return self._competitor

    @property
    def image(self):
        """이미지 일괄 처리."""
        if self._image is None:
            from scripts.naver.automation.image_processor import ImageProcessor

            self._image = ImageProcessor()
        return self._image

    @property
    def notifier(self):
        """다중 채널 알림."""
        if self._notifier is None:
            from scripts.naver.automation.integration.notification_hub import (
                NotificationHub,
            )

            self._notifier = NotificationHub(self.page)
        return self._notifier

    @property
    def error_recovery(self):
        """에러 자동 복구."""
        if self._error_recovery is None:
            from scripts.naver.automation.error_recovery import ErrorRecovery

            self._error_recovery = ErrorRecovery(self.page)
        return self._error_recovery

    @property
    def scheduler(self):
        """정기 실행 스케줄러."""
        if self._scheduler is None:
            from scripts.naver.automation.scheduler import Scheduler

            self._scheduler = Scheduler()
        return self._scheduler

    @property
    def session(self):
        """세션 자동 관리."""
        if self._session is None:
            from scripts.naver.automation.session_manager import SessionManager

            self._session = SessionManager(self.page)
        return self._session
