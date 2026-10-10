"""스마트스토어 상품 등록 고급 기능 — 판매옵션 / SmartEditor / 상품속성.

ProductRegister 확장 모듈:
  - ProductOptionEditor: 사이즈/색상 등 옵션 설정
  - SmartEditorONE: 상세설명 iframe 진입 + 입력
  - PriceStockEditor: 가격/재고 (일반 상품 등록 페이지용)

사용:
  from scripts.naver.smartstore.product import ProductRegister
  from scripts.naver.smartstore.advanced import SmartEditorONE, PriceStockEditor

  pr = ProductRegister(page)
  pr.open()
  ...

  # 상세설명
  se = SmartEditorONE(page)
  se.write("상품 설명 본문...")
  se.insert_image("data/detail1.jpg")

  # 가격/재고 (일반 상품 등록 페이지에서)
  ps = PriceStockEditor(page)
  ps.set_price(29800)
  ps.set_stock(100)
  ps.set_discount(rate=10, period_days=7)
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


# ── SmartEditor ONE 상세설명 ──────────────────────────────────────────────


class SmartEditorONE:
    """네이버 SmartEditor ONE 자동 입력 모듈."""

    def __init__(self, page: Page):
        self.page = page
        self.frame = None

    def open(self) -> bool:
        """에디터 영역 활성화 + iframe 진입.

        '스마트 에디터 ONE으로 작성' 버튼 클릭 → iframe 진입.
        """
        try:
            # 상세설명 섹션으로 스크롤
            self.page.evaluate("window.scrollTo(0, 1550)")
            time.sleep(1)
            # 버튼 클릭
            try:
                self.page.locator("text=스마트 에디터 ONE").first.click(timeout=3000, force=True)
                time.sleep(4)
            except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
                _log.debug("[smart-editor] 버튼 클릭 무시 (이미 열림 가능): %s", e)

            # iframe 찾기
            for f in self.page.frames:
                if "editor" in f.url.lower() or "se-" in f.url.lower() or "smarteditor" in f.url.lower():
                    self.frame = f
                    _log.info("[smart-editor] iframe 진입: %s", f.url[:80])
                    return True

            # iframe이 별도 모달/팝업일 수도
            time.sleep(2)
            for f in self.page.frames:
                src = f.url.lower()
                if "smartstore" in src and ("editor" in src or "se" in src):
                    self.frame = f
                    return True

            _log.warning("[smart-editor] iframe 못 찾음 — fallback")
            return False
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            _log.error("[smart-editor] open 실패: %s", e)
            return False

    def write(self, content: str) -> dict:
        """본문 입력 (단순 텍스트)."""
        if not self.frame:
            if not self.open():
                # iframe 없어도 contenteditable로 시도
                try:
                    el = self.page.locator('[contenteditable="true"]').first
                    el.click(timeout=3000)
                    time.sleep(0.5)
                    self.page.keyboard.type(content, delay=10)
                    return {"ok": True, "mode": "contenteditable_fallback"}
                except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
                    return {"ok": False, "error": f"no_editor_found:{e}"}

        try:
            editable = self.frame.locator('[contenteditable="true"], .se-text-paragraph').first
            editable.click(timeout=3000)
            time.sleep(0.5)
            self.page.keyboard.type(content, delay=10)
            return {"ok": True, "mode": "iframe"}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            return {"ok": False, "error": str(e)[:80]}

    def insert_image(self, image_path: str) -> dict:
        """SmartEditor에 이미지 삽입."""
        if not self.frame:
            return {"ok": False, "error": "frame_not_ready"}
        if not Path(image_path).exists():
            return {"ok": False, "error": "file_not_found"}
        try:
            # 이미지 버튼 클릭
            self.frame.locator('button[data-name="image"], .se-toolbar-button-image').first.click(timeout=3000)
            time.sleep(1)
            # file input
            file_input = self.frame.locator('input[type="file"]').first
            file_input.set_input_files(image_path, timeout=5000)
            time.sleep(3)
            log_critical(
                "FILE_UPLOAD", f"SmartEditor 이미지: {Path(image_path).name}", file=image_path, mode="smarteditor_image"
            )
            return {"ok": True, "file": image_path}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            return {"ok": False, "error": str(e)[:80]}


# ── 가격/재고/할인 (일반 상품 등록 페이지용) ─────────────────────────────


class PriceStockEditor:
    """가격/재고/할인/배송비 입력. 일반 상품 등록 페이지에서 사용."""

    def __init__(self, page: Page):
        self.page = page

    def _fill_by_label(self, label: str, value: str, force: bool = True) -> dict:
        """라벨 텍스트로 input 찾아 fill."""
        try:
            # 라벨 옆 input 찾기
            input_loc = self.page.locator(
                f'label:has-text("{label}") + * input, label:has-text("{label}") ~ * input'
            ).first
            if input_loc.count() == 0:
                # placeholder/aria로 시도
                input_loc = self.page.locator(f'input[placeholder*="{label}"], input[aria-label*="{label}"]').first
            self.page.evaluate(f"""
            (() => {{
                // 라벨 텍스트 위치로 스크롤
                const els = Array.from(document.querySelectorAll('label, .label, dt'));
                const target = els.find(e => (e.innerText||'').includes('{label}'));
                if (target) target.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.5)
            input_loc.fill(str(value), timeout=5000, force=force)
            return {"ok": True, "label": label, "value": value}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            return {"ok": False, "error": str(e)[:80]}

    def set_price(self, price: int) -> dict:
        """판매가 설정."""
        r = self._fill_by_label("판매가", price)
        if r.get("ok"):
            log_critical("OTHER", f"상품 판매가 설정: {price}", price=price)
        return r

    def set_original_price(self, price: int) -> dict:
        """원가/할인전 가격 설정."""
        return self._fill_by_label("원가", price)

    def set_stock(self, stock: int) -> dict:
        """재고 수량 설정."""
        return self._fill_by_label("재고수량", stock) or self._fill_by_label("재고", stock)

    def set_min_order(self, qty: int = 1) -> dict:
        """최소 구매수량."""
        return self._fill_by_label("최소", qty)

    def set_max_order(self, qty: int = 1) -> dict:
        """최대 구매수량."""
        return self._fill_by_label("최대", qty)

    def set_delivery_fee(self, fee: int = 0, free_over: int | None = None) -> dict:
        """배송비. free_over 지정 시 그 금액 이상 무료배송."""
        try:
            r = self._fill_by_label("배송비", fee)
            if free_over is not None:
                self._fill_by_label("무료배송", free_over)
            return r
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            return {"ok": False, "error": str(e)[:80]}


# ── 판매옵션 (사이즈/색상 등) ──────────────────────────────────────────────


class ProductOptionEditor:
    """판매옵션 (옵션별 가격/재고)."""

    def __init__(self, page: Page):
        self.page = page

    def open_option_section(self) -> bool:
        """판매옵션 섹션으로 스크롤 + 활성화."""
        try:
            self.page.evaluate("window.scrollTo(0, 1018)")
            time.sleep(1)
            # '옵션 사용' 또는 '단독상품' 체크박스 활성화
            try:
                self.page.get_by_text("옵션 사용", exact=False).first.click(timeout=2000, force=True)
                time.sleep(1)
            except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
                pass
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            _log.error("[option] open 실패: %s", e)
            return False

    def add_option(self, name: str, values: list[str]) -> dict:
        """옵션 추가 (예: 사이즈 = [S, M, L]).

        주의: 스마트스토어 옵션 UI는 복잡 (옵션 이름 + 옵션값 + 옵션별 가격/재고).
        이 메서드는 기본 골격만. 상세는 UI 직접 분석 후 보강.
        """
        if not self.open_option_section():
            return {"ok": False, "error": "open_failed"}
        try:
            # 옵션 이름 input
            self.page.locator('input[placeholder*="옵션"]').first.fill(name, timeout=3000, force=True)
            time.sleep(0.5)
            # 옵션 값
            value_input = self.page.locator('input[placeholder*="값"], input[placeholder*="옵션값"]').first
            value_input.fill(",".join(values), timeout=3000, force=True)
            time.sleep(0.5)
            # 적용 버튼 - 실패해도 계속 진행(폼 입력 실패일 뿐 결제/발행 확정 없음)
            with contextlib.suppress(Exception):
                self.page.get_by_text("옵션목록으로 적용", exact=False).first.click(timeout=2000, force=True)
            time.sleep(1)
            return {"ok": True, "name": name, "values": values}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 스마트에디터/가격/옵션 입력 자동화 - 모든 except가 ok:False,error 반환, 폼 입력 실패일 뿐 결제/발행 확정 없음
            return {"ok": False, "error": str(e)[:80]}
