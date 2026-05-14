"""네이버 스마트스토어 일반 상품 등록 자동화 (가격/재고 포함).

URL: 사이드바 '상품관리 > 상품 등록' 클릭으로 진입 (직접 URL 진입 불가).

검증된 셀렉터:
  - product.salePrice (판매가) ★
  - product.stockQuantity (재고)
  - product.name (상품명)
  - category (카테고리)
  - _hidden_uploaded_* (이미지 5종)

사용:
  from scripts.naver.smartstore.general_product import GeneralProductRegister
  pr = GeneralProductRegister(page)
  pr.open()
  pr.set_product_name("자동 등록")
  pr.set_category("디지털/가전")
  pr.set_price(29800)
  pr.set_stock(100)
  pr.save()  # 사용자 명시 호출 필수
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical
from scripts.popup_detector import handle_page_popups, close_popup_windows
from scripts.naver.auth import ensure_naver_login
from scripts.site_session_safety import assert_session_integrity

_log = get_logger(__name__)

DASHBOARD = "https://sell.smartstore.naver.com/#/home/dashboard"


class GeneralProductRegister:
    """일반 상품 등록 자동화 (가격/재고 포함)."""

    def __init__(self, page: Page):
        self.page = page
        self._opened = False

    # ── 초기화: 사이드바 클릭으로 진입 ──────────────────────────────────

    def open(self, timeout_s: int = 30) -> bool:
        """대시보드 → '상품관리' → '상품 등록' 자동 클릭으로 진입."""
        r = ensure_naver_login(self.page)
        assert_session_integrity(r, site="smartstore", workflow="product_general_open")
        if not r.get("ok"):
            return False

        # 대시보드 진입
        self.page.goto(DASHBOARD, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        time.sleep(5)
        try:
            handle_page_popups(self.page, timeout_s=2.0)
            close_popup_windows(self.page)
        except Exception:
            pass

        # 사이드바 '상품관리' 클릭
        if not self._click_sidebar_text("상품관리"):
            _log.error("[gen-reg] '상품관리' 클릭 실패")
            return False
        time.sleep(2)

        # '상품 등록' 클릭 (사이드바 펼쳐진 후)
        if not self._click_sidebar_text("상품 등록"):
            _log.error("[gen-reg] '상품 등록' 클릭 실패")
            return False
        time.sleep(4)  # 동적 페이지 로드 대기

        # 가격 input 존재로 진입 검증
        try:
            self.page.locator('input[name="product.salePrice"]').first.wait_for(
                state="attached", timeout=10000
            )
            _log.info("[gen-reg] 일반 상품 등록 페이지 진입 완료")
            self._opened = True
            log_critical("OTHER", "일반 상품 등록 페이지 진입", mode="general_register_start")
            return True
        except Exception as e:
            _log.error("[gen-reg] 페이지 검증 실패: %s", e)
            return False

    def _click_sidebar_text(self, text: str, x_max: int = 280) -> bool:
        """사이드바 메뉴 텍스트로 좌표 찾아 마우스 클릭."""
        coords = self.page.evaluate(r"""
        ({text, xMax}) => {
            for (const el of document.querySelectorAll('a, li, button, span')) {
                const s = window.getComputedStyle(el);
                if (s.display === 'none') continue;
                const t = (el.innerText || '').trim();
                if (t === text) {
                    const r = el.getBoundingClientRect();
                    if (r.x < xMax && r.y > 0 && r.width > 0) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
            }
            return null;
        }
        """, {"text": text, "xMax": x_max})
        if not coords:
            return False
        self.page.mouse.move(coords["x"], coords["y"])
        time.sleep(0.4)
        self.page.mouse.click(coords["x"], coords["y"])
        return True

    def _ensure_opened(self) -> bool:
        return self._opened or self.open()

    # ── 안전 입력 헬퍼 ──────────────────────────────────────────────────

    def _fill_field(self, selector: str, value: str, label: str = "") -> dict:
        """필드 입력 (scroll + fill + Angular 이벤트)."""
        try:
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.4)
            el = self.page.locator(selector).first
            el.fill(str(value), timeout=5000, force=True)
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                }}
            }})();
            """)
            time.sleep(0.3)
            _log.info("[gen-reg] %s: %s", label or selector, value)
            return {"ok": True, "value": value}
        except Exception as e:
            _log.error("[gen-reg] %s 입력 실패: %s", label, e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 필수 필드 ───────────────────────────────────────────────────────

    def set_product_name(self, name: str) -> dict:
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        return self._fill_field('input[name="product.name"]', name, label="상품명")

    def set_price(self, price: int) -> dict:
        """판매가 (원)"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        r = self._fill_field('input[name="product.salePrice"]', str(price), label="판매가")
        if r.get("ok"):
            log_critical("OTHER", f"상품 판매가: {price}원", price=price, mode="set_price")
        return r

    def set_stock(self, stock: int) -> dict:
        """재고 수량"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        return self._fill_field('input[name="product.stockQuantity"]', str(stock), label="재고")

    def set_category(self, category_name: str) -> dict:
        """카테고리 검색 + 첫 항목 선택."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            sel = 'input[placeholder*="카테고리"]:not([type="radio"]):not([type="checkbox"])'
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.4)
            el = self.page.locator(sel).first
            el.fill(category_name, timeout=5000, force=True)
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) {{
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('focus', {{bubbles: true}}));
                }}
            }})();
            """)
            time.sleep(2)
            # 자동완성 첫 항목 선택
            try:
                first = self.page.locator(
                    '[class*="category-search-result"] li, [class*="autocomplete"] li, '
                    '.ui-menu-item, [class*="suggestion"] li'
                ).first
                if first.is_visible(timeout=1500):
                    first.click(timeout=3000, force=True)
                    time.sleep(0.8)
            except Exception:
                self.page.keyboard.press("ArrowDown")
                time.sleep(0.3)
                self.page.keyboard.press("Enter")
                time.sleep(0.8)
            _log.info("[gen-reg] 카테고리: %s", category_name)
            return {"ok": True, "category": category_name}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}

    # ── 이미지 ──────────────────────────────────────────────────────────

    def upload_main_image(self, image_path: str) -> dict:
        """대표 이미지 업로드."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        if not Path(image_path).exists():
            return {"ok": False, "error": "file_not_found"}
        try:
            # 이미지 영역으로 스크롤
            self.page.evaluate("""
            (() => {
                const el = document.querySelector('input[name*="uploaded"]');
                if (el) el.scrollIntoView({block: 'center'});
            })();
            """)
            time.sleep(1)
            file_input = self.page.locator('input[type="file"]').first
            file_input.set_input_files(image_path, timeout=10000)
            time.sleep(3.5)
            log_critical("FILE_UPLOAD", f"일반 상품 대표 이미지: {Path(image_path).name}",
                         file=image_path, mode="general_product_image_main")
            return {"ok": True, "file": image_path}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}

    # ── 저장 (사용자 명시 호출 필수) ─────────────────────────────────────

    def save(self, require_confirm: bool = True) -> dict:
        """등록 (★ 사용자 명시 호출 필수)."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        if require_confirm:
            try:
                ans = input("\n  ⚠ 일반 상품 등록을 저장하시겠습니까? (y/N): ").strip().lower()
                if ans != "y":
                    return {"ok": False, "cancelled": True, "reason": "user_declined"}
            except (EOFError, KeyboardInterrupt):
                return {"ok": False, "cancelled": True}

        try:
            # 페이지 하단으로 스크롤 (저장 버튼이 보통 하단)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            # 저장 버튼 클릭
            self.page.locator('button:has-text("저장"), button:has-text("등록")').first.click(timeout=5000, force=True)
            time.sleep(5)
            log_critical("OTHER", "일반 상품 등록 저장", url=self.page.url, mode="general_save")
            return {"ok": True, "url": self.page.url}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}

    # ── 통합 원샷 등록 ───────────────────────────────────────────────────

    def register_product(self, data: dict, save_after: bool = False,
                         require_confirm: bool = True) -> dict:
        """원샷 등록.

        data:
            name (필수), price (필수), stock (필수),
            category, main_image
        """
        if not self.open():
            return {"ok": False, "error": "open_failed"}

        steps = []
        def run(name, fn, *a, **kw):
            r = fn(*a, **kw)
            steps.append((name, r))
            return r

        if data.get("category"):
            run("category", self.set_category, data["category"])
        if data.get("name"):
            run("name", self.set_product_name, data["name"])
        if data.get("price") is not None:
            run("price", self.set_price, data["price"])
        if data.get("stock") is not None:
            run("stock", self.set_stock, data["stock"])
        if data.get("main_image"):
            run("main_image", self.upload_main_image, data["main_image"])

        save_result = None
        if save_after:
            save_result = self.save(require_confirm=require_confirm)
            steps.append(("save", save_result))

        return {
            "ok": all(s[1].get("ok", False) for s in steps),
            "steps": steps,
            "step_results": {n: r.get("ok", False) for n, r in steps},
            "saved": bool(save_result and save_result.get("ok")),
        }
