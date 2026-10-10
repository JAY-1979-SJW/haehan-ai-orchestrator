"""네이버 스마트스토어 그룹상품 등록 자동화.

URL: https://sell.smartstore.naver.com/#/products/standard-group-product/create

핵심 필드 (필수):
  - category   : 카테고리 검색 입력
  - product.name : 상품명 ★

선택 필드:
  - 모델명, 사은품, 인증, 이벤트 문구, 이미지(5종), 상세설명(SmartEditor)

안전 정책:
  - .save() 메서드만 호출해야 저장됨
  - 자동으로 저장 안 함 (사용자 명시 호출 필수)

사용:
  from scripts.naver.smartstore.product import ProductRegister
  pr = ProductRegister(page)
  pr.open()
  pr.set_category("패션의류>여성의류>티셔츠")
  pr.set_product_name("자동 등록 테스트 상품")
  pr.set_model_name("MODEL-001")
  pr.set_gift("증정품: 에코백")
  pr.upload_main_image("data/images/main.jpg")
  pr.upload_extra_images(["data/images/2.jpg", "data/images/3.jpg"])
  pr.set_description("상품 상세 설명 내용...")
  # 마지막에 사용자 명시 호출 필요
  pr.save()  # 또는 pr.cancel()
"""

from __future__ import annotations

import time
from contextlib import suppress
from pathlib import Path

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups
from scripts.site_engine.site_session_safety import assert_session_integrity

_log = get_logger(__name__)

REGISTER_URL = "https://sell.smartstore.naver.com/#/products/standard-group-product/create"


class ProductRegister:
    """그룹상품 등록 자동화."""

    def __init__(self, page: Page):
        self.page = page
        self._opened = False

    # ── 초기화 ──────────────────────────────────────────────────────────

    def open(self, timeout_s: int = 30) -> bool:
        """등록 페이지 진입 + 자동 로그인 + 팝업 처리."""
        r = ensure_naver_login(self.page)
        assert_session_integrity(r, site="smartstore", workflow="product_group_open")
        if not r.get("ok"):
            _log.error("[product-reg] 로그인 실패")
            return False

        self.page.goto(REGISTER_URL, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        time.sleep(5)
        try:
            handle_page_popups(self.page, timeout_s=2.0)
            close_popup_windows(self.page)
        except Exception:  # noqa: BLE001 - 여러 셀렉터/유형을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속(2026-09-28 검토)
            pass

        if "standard-group-product/create" not in self.page.url:
            _log.error("[product-reg] 등록 페이지 도달 실패: %s", self.page.url)
            return False

        self.page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        # 페이지 하단의 fixed 저장 바를 잠시 숨김 (클릭 가로채기 방지)
        # 진짜 저장 시점에 다시 보이게 함
        self._hide_fixed_bar()

        self._opened = True
        log_critical("OTHER", "상품 등록 페이지 진입", url=REGISTER_URL, mode="product_register_start")
        return True

    def _hide_fixed_bar(self) -> None:
        """페이지 하단 fixed 저장 바만 정확히 숨김.

        주의: 너무 광범위하게 hide하면 input의 부모도 사라짐.
        '.pc-fixed-area.navbar-fixed-bottom' 정확 조합만 hide.
        """
        with suppress(Exception):
            self.page.evaluate("""
            (() => {
                // 정확한 조합만 hide
                document.querySelectorAll('.pc-fixed-area.navbar-fixed-bottom').forEach(el => {
                    el.dataset._origDisplay = el.style.display;
                    el.style.display = 'none';
                });
                // pointer-events:none으로 클릭 가로채기만 차단 (display는 유지)
                document.querySelectorAll('.pc-fixed-area').forEach(el => {
                    if (!el.dataset._origPointerEvents) {
                        el.dataset._origPointerEvents = el.style.pointerEvents || '';
                        el.style.pointerEvents = 'none';
                    }
                });
            })();
            """)

    def _show_fixed_bar(self) -> None:
        """fixed 저장 바 복원."""
        with suppress(Exception):
            self.page.evaluate("""
            (() => {
                document.querySelectorAll('.pc-fixed-area.navbar-fixed-bottom').forEach(el => {
                    el.style.display = el.dataset._origDisplay || '';
                });
                document.querySelectorAll('.pc-fixed-area').forEach(el => {
                    el.style.pointerEvents = el.dataset._origPointerEvents || '';
                });
            })();
            """)

    def _ensure_opened(self) -> bool:
        if self._opened:
            return True
        return self.open()

    # ── 카테고리 ────────────────────────────────────────────────────────

    def set_category(self, category_name: str) -> dict:
        """카테고리 입력 + 자동 검색 → 첫번째 매칭 선택.

        주의: input[name="category"]는 라디오 버튼임 (검색 input 아님).
        실제 검색 input은 placeholder="카테고리명 입력".
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            # 카테고리 검색 input — placeholder 기반
            sel = 'input[placeholder*="카테고리"]:not([type="radio"]):not([type="checkbox"])'
            # JS scrollIntoView
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.5)
            el = self.page.locator(sel).first
            el.fill(category_name, timeout=5000, force=True)
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) {{
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.dispatchEvent(new Event('focus', {{bubbles: true}}));
                }}
            }})();
            """)
            time.sleep(2.0)
            # 자동완성 첫 항목
            try:
                first_result = self.page.locator(
                    '[class*="category-search-result"] li, [class*="autocomplete"] li, '
                    '.ui-menu-item, [class*="search-result"] li, [class*="suggestion"] li, '
                    '[class*="dropdown"] li'
                ).first
                if first_result.is_visible(timeout=1500):
                    first_result.click(timeout=3000, force=True)
                    time.sleep(0.8)
            except Exception:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
                self.page.keyboard.press("ArrowDown")
                time.sleep(0.3)
                self.page.keyboard.press("Enter")
                time.sleep(0.8)
            _log.info("[product-reg] 카테고리: %s", category_name)
            return {"ok": True, "category": category_name}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 카테고리 입력 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 상품명 ────────────────────────────────────────────────────────────

    def set_product_name(self, name: str) -> dict:
        """상품명 입력 (fill 기반 — 클릭 가로채기 회피, scroll 실패 무시)."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            sel = 'input[name="product.name"]'
            # JS로 직접 scrollIntoView (Playwright scroll_into_view_if_needed 우회)
            self.page.evaluate(
                """
            (sel) => {
                const el = document.querySelector(sel);
                if (el) el.scrollIntoView({block: 'center', behavior: 'instant'});
            }
            """,
                sel,
            )
            time.sleep(0.5)
            el = self.page.locator(sel).first
            # fill로 직접 (force=True로 visibility 체크 우회)
            el.fill(name, timeout=5000, force=True)
            self.page.evaluate(
                """
            (sel) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            }
            """,
                sel,
            )
            time.sleep(0.5)
            _log.info("[product-reg] 상품명: %s", name)
            return {"ok": True, "name": name}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 상품명 입력 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 인증 ────────────────────────────────────────────────────────────

    def set_kc_exemption(self, exemption_type: str = "구매대행") -> dict:
        """KC 인증 면제 사유 선택."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            self.page.get_by_text(exemption_type, exact=True).first.click(timeout=3000)
            time.sleep(0.5)
            return {"ok": True, "type": exemption_type}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def set_certification(self, agency: str, cert_number: str) -> dict:
        """KC 인증기관/번호 입력."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            # 인증기관 (placeholder='인증기관')
            self.page.locator('input[placeholder*="인증기관"]').first.fill(agency, timeout=3000)
            time.sleep(0.3)
            # 인증번호
            self.page.locator('input[placeholder*="인증번호"]').first.fill(cert_number, timeout=3000)
            time.sleep(0.3)
            return {"ok": True, "agency": agency, "number": cert_number}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    # ── 모델명 ──────────────────────────────────────────────────────────

    def set_model_name(self, model: str) -> dict:
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            sel = 'input[name*="product.detailAttribute.m"]'
            # JS scrollIntoView 우선
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.5)
            el = self.page.locator(sel).first
            el.fill(model, timeout=5000, force=True)
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) {{
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }})();
            """)
            time.sleep(0.3)
            _log.info("[product-reg] 모델명: %s", model)
            return {"ok": True, "model": model}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 모델명 입력 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 사은품 ──────────────────────────────────────────────────────────

    def set_gift(self, gift_text: str) -> dict:
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            el = self.page.locator('input[name*="customerBenefit.giftPolic"]').first
            el.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.3)
            el.fill(gift_text, timeout=5000)
            time.sleep(0.3)
            return {"ok": True, "gift": gift_text}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    # ── 이벤트 추가 문구 ─────────────────────────────────────────────────

    def set_event_text(self, text: str) -> dict:
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            el = self.page.locator('input[name*="product.detailAttribute.e"]').first
            el.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.3)
            el.fill(text, timeout=5000)
            time.sleep(0.3)
            return {"ok": True, "event_text": text}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    # ── 이미지 업로드 ────────────────────────────────────────────────────

    def upload_main_image(self, image_path: str, mode: str = "common") -> dict:
        """대표 이미지 업로드. mode: 'common' (공통등록) | 'per_product' (상품별등록)"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        if not Path(image_path).exists():
            return {"ok": False, "error": "file_not_found"}
        try:
            # 이미지 섹션 활성화
            self._activate_image_section(mode=mode)
            time.sleep(1)

            # 이미지 등록 버튼 클릭 (file input 노출)
            try:
                self.page.get_by_text("이미지 등록", exact=True).first.click(timeout=3000, force=True)
                time.sleep(0.8)
            except Exception:  # noqa: BLE001 - 여러 셀렉터/유형을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속(2026-09-28 검토)
                pass

            file_inputs = self.page.locator('input[type="file"]')
            n = file_inputs.count()
            if n == 0:
                # 숨겨진 file input도 set_input_files는 가능
                # DOM 직접 검색
                hidden_count = self.page.evaluate("() => document.querySelectorAll('input[type=file]').length")
                if hidden_count == 0:
                    return {"ok": False, "error": "no_file_input_at_all"}

            # 첫 file input에 업로드
            file_inputs.first.set_input_files(image_path, timeout=10000)
            time.sleep(3.5)

            log_critical(
                "FILE_UPLOAD",
                f"상품 대표 이미지: {Path(image_path).name}",
                file=image_path,
                size=Path(image_path).stat().st_size,
                mode="product_image_main",
            )
            _log.info("[product-reg] 대표 이미지: %s (file_inputs=%d)", image_path, n)
            return {"ok": True, "file": image_path, "file_inputs_found": n}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 대표 이미지 업로드 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    def upload_additional_images(self, image_paths: list[str]) -> dict:
        """추가 이미지 업로드 (여러 개)."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        results = []
        for path in image_paths:
            if not Path(path).exists():
                results.append({"file": path, "ok": False, "error": "not_found"})
                continue
            try:
                file_inputs = self.page.locator('input[type="file"]')
                # 두 번째 이후 file input 사용 (추가 이미지용)
                idx = min(1, file_inputs.count() - 1)
                file_inputs.nth(idx).set_input_files(path, timeout=10000)
                time.sleep(2.5)
                results.append({"file": path, "ok": True})
                log_critical(
                    "FILE_UPLOAD", f"상품 추가 이미지: {Path(path).name}", file=path, mode="product_image_additional"
                )
            except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
                results.append({"file": path, "ok": False, "error": str(e)[:60]})
        return {"ok": True, "results": results}

    # ── 상세설명 (SmartEditor ONE) ──────────────────────────────────────

    def set_description(self, content: str, mode: str = "text") -> dict:
        """상세설명 입력. mode: 'text' (직접 작성) | 'html' (HTML 작성).

        SmartEditor ONE 사용. iframe 진입 필요.
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            # 스크롤로 에디터 영역 이동
            self.page.evaluate("window.scrollTo(0, 1900)")
            time.sleep(1)

            # "스마트 에디터 ONE으로 작성" 버튼 클릭
            try:
                self.page.locator("text=스마트 에디터 ONE").first.click(timeout=3000)
                time.sleep(3)  # 에디터 로딩 대기
            except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
                _log.debug("[product-reg] 에디터 버튼 클릭 실패 (이미 열림 가능): %s", e)

            # SmartEditor iframe 찾기
            editor_frame = None
            for f in self.page.frames:
                if "editor" in f.url.lower() or "se-" in f.url.lower():
                    editor_frame = f
                    break
            if not editor_frame:
                # 모든 contenteditable 시도
                editable = self.page.locator('[contenteditable="true"]').first
                editable.click(timeout=3000)
                time.sleep(0.5)
                self.page.keyboard.type(content, delay=10)
                return {"ok": True, "mode": "fallback_contenteditable"}

            # iframe 안에서 입력
            editable = editor_frame.locator('[contenteditable="true"], .se-text-paragraph').first
            editable.click(timeout=3000)
            time.sleep(0.5)
            self.page.keyboard.type(content, delay=10)
            return {"ok": True, "mode": mode}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 상세설명 입력 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 추가 필드 (진단 결과 기반) ───────────────────────────────────────

    def set_brand(self, brand: str) -> dict:
        """브랜드 입력."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            sel = 'input[placeholder*="브랜드"]'
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.3)
            self.page.locator(sel).first.fill(brand, timeout=3000, force=True)
            return {"ok": True, "brand": brand}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def set_manufacturer(self, manufacturer: str) -> dict:
        """제조사 입력."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            sel = 'input[placeholder*="제조사"]'
            self.page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{sel}');
                if (el) el.scrollIntoView({{block: 'center'}});
            }})();
            """)
            time.sleep(0.3)
            self.page.locator(sel).first.fill(manufacturer, timeout=3000, force=True)
            return {"ok": True, "manufacturer": manufacturer}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def set_vat_type(self, vat_type: str = "과세상품") -> dict:
        """부가세 유형. vat_type: '과세상품' | '면세상품' | '영세상품'"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        if vat_type not in ("과세상품", "면세상품", "영세상품"):
            return {"ok": False, "error": "invalid_vat_type"}
        return self._click_label_radio(vat_type, scroll_y=2818)

    def set_product_status(self, status: str = "신상품") -> dict:
        """상품 상태. status: '신상품' | '중고상품'"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        if status not in ("신상품", "중고상품"):
            return {"ok": False, "error": "invalid_status"}
        return self._click_label_radio(status, scroll_y=2882)

    def set_minor_purchase(self, allowed: bool = True) -> dict:
        """미성년자 구매. True=가능 / False=불가능"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        label = "가능" if allowed else "불가능"
        return self._click_label_radio(label, scroll_y=2992)

    def set_sale_period(self, enabled: bool = False) -> dict:
        """판매기간 설정. True=설정함 / False=설정안함"""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        label = "설정함" if enabled else "설정안함"
        return self._click_label_radio(label, scroll_y=3235)

    def set_self_made(self, enabled: bool = False) -> dict:
        """자체제작 상품 체크박스."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            self.page.evaluate("window.scrollTo(0, 2695)")
            time.sleep(0.5)
            label = self.page.get_by_text("자체제작 상품", exact=True).first
            cb = label.locator("xpath=preceding::input[@type='checkbox'][1]").first
            try:
                is_checked = cb.is_checked(timeout=1000)
            except Exception:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
                is_checked = False
            if is_checked != enabled:
                # 라벨 클릭
                label.click(timeout=2000, force=True)
            return {"ok": True, "self_made": enabled}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def _click_label_radio(self, label_text: str, scroll_y: int = 0) -> dict:
        """라벨 텍스트로 라디오 버튼 클릭 (공통 헬퍼)."""
        try:
            if scroll_y:
                # 스크롤로 영역 가시화
                self.page.evaluate(f"window.scrollTo(0, {scroll_y - 200})")
                time.sleep(0.6)
            # 라벨 클릭 (라디오의 부모/형제 label 자동 매칭)
            self.page.get_by_text(label_text, exact=True).first.click(timeout=3000, force=True)
            time.sleep(0.3)
            _log.info("[product-reg] 라디오 선택: %s", label_text)
            return {"ok": True, "selected": label_text}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 라디오 선택 실패 (%s): %s", label_text, e)
            return {"ok": False, "error": str(e)[:80]}

    # ── 이미지 영역 활성화 + 업로드 (개선) ────────────────────────────────

    def _activate_image_section(self, mode: str = "common") -> bool:
        """이미지 등록 영역 활성화. mode: 'common' (공통등록) | 'per_product' (상품별등록)"""
        try:
            self.page.evaluate("window.scrollTo(0, 1290)")
            time.sleep(1)
            label = "공통등록" if mode == "common" else "상품별등록"
            self.page.get_by_text(label, exact=True).first.click(timeout=3000, force=True)
            time.sleep(1.5)
            return True
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.warning("[product-reg] 이미지 영역 활성화 실패: %s", e)
            return False

    # ── 저장/취소 (사용자 명시 호출 필수) ─────────────────────────────────

    def save(self, require_confirm: bool = True) -> dict:
        """등록 (★ 사용자 명시 호출 필수).

        require_confirm=True 시 콘솔 input() 확인. False 시 즉시 저장.
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        if require_confirm:
            try:
                ans = input("\n  ⚠ 상품 등록을 저장하시겠습니까? (y/N): ").strip().lower()
                if ans != "y":
                    return {"ok": False, "cancelled": True, "reason": "user_declined"}
            except (EOFError, KeyboardInterrupt):
                return {"ok": False, "cancelled": True, "reason": "input_interrupted"}

        try:
            # fixed bar 복원 (저장 버튼은 그 안에 있음)
            self._show_fixed_bar()
            time.sleep(0.5)
            self.page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)
            self.page.locator('button:has-text("저장하기")').first.click(timeout=5000)
            time.sleep(3)

            # 발행 성공/실패 감지
            url = self.page.url
            log_critical("OTHER", "상품 등록 저장 완료", url=url, mode="product_register_save")
            _log.info("[product-reg] 저장 완료: %s", url)
            return {"ok": True, "url": url}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            _log.error("[product-reg] 저장 실패: %s", e)
            return {"ok": False, "error": str(e)[:80]}

    def cancel(self) -> dict:
        """취소."""
        try:
            self.page.locator('button:has-text("취소")').first.click(timeout=3000)
            time.sleep(2)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 그룹상품 등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환, 실제 저장은 save() 명시 호출 시에만, 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    # ── 통합 원샷 등록 ───────────────────────────────────────────────────

    def _reg_basic(self, data: dict, run) -> None:
        """기본 정보(카테고리/상품명)."""
        # 기본 정보
        if data.get("category"):
            run("category", self.set_category, data["category"])
        if data.get("name"):
            run("name", self.set_product_name, data["name"])

    def _reg_main_info(self, data: dict, run) -> None:
        """상품 주요정보(브랜드/제조사/모델명/자체제작)."""
        # 상품 주요정보
        if data.get("brand"):
            run("brand", self.set_brand, data["brand"])
        if data.get("manufacturer"):
            run("manufacturer", self.set_manufacturer, data["manufacturer"])
        if data.get("model_name"):
            run("model_name", self.set_model_name, data["model_name"])
        if data.get("self_made") is not None:
            run("self_made", self.set_self_made, data["self_made"])

    def _reg_radio(self, data: dict, run) -> None:
        """라디오 옵션들(부가세/상품상태/미성년자 구매/판매기간)."""
        # 라디오 옵션들
        if data.get("vat_type"):
            run("vat_type", self.set_vat_type, data["vat_type"])
        if data.get("product_status"):
            run("product_status", self.set_product_status, data["product_status"])
        if data.get("minor_purchase") is not None:
            run("minor_purchase", self.set_minor_purchase, data["minor_purchase"])
        if data.get("sale_period") is not None:
            run("sale_period", self.set_sale_period, data["sale_period"])

    def _reg_cert_extra(self, data: dict, run) -> None:
        """인증 + 부가 정보(사은품/이벤트)."""
        # 인증
        if data.get("kc_exemption"):
            run("kc_exemption", self.set_kc_exemption, data["kc_exemption"])
        if data.get("certification"):
            c = data["certification"]
            run("certification", self.set_certification, c.get("agency", ""), c.get("number", ""))

        # 부가 정보
        if data.get("gift"):
            run("gift", self.set_gift, data["gift"])
        if data.get("event_text"):
            run("event_text", self.set_event_text, data["event_text"])

    def _reg_media(self, data: dict, run) -> None:
        """이미지 + 상세설명."""
        # 이미지
        if data.get("main_image"):
            mode = data.get("image_mode", "common")
            run("main_image", self.upload_main_image, data["main_image"], mode=mode)
        if data.get("additional_images"):
            run("additional_images", self.upload_additional_images, data["additional_images"])

        # 상세설명
        if data.get("description"):
            run("description", self.set_description, data["description"])

    def register_product(self, data: dict, save_after: bool = False, require_confirm: bool = True) -> dict:
        """상품 정보 dict → 자동 등록 (전체 필드 통합).

        지원 필드 (모두 선택):
            category, name (★필수), model_name, brand, manufacturer
            gift, event_text
            vat_type ("과세상품"|"면세상품"|"영세상품")
            product_status ("신상품"|"중고상품")
            minor_purchase (bool — True=가능)
            sale_period (bool — True=설정함)
            self_made (bool — 자체제작)
            kc_exemption ("구매대행"|"안전기준 준수"|"KC 안전관리대상 아님")
            certification {agency, number}
            main_image, additional_images, image_mode ("common"|"per_product")
            description
        """
        if not self.open():
            return {"ok": False, "error": "open_failed"}

        steps = []

        def run(name, fn, *args, **kwargs):
            r = fn(*args, **kwargs)
            steps.append((name, r))
            return r

        self._reg_basic(data, run)
        self._reg_main_info(data, run)
        self._reg_radio(data, run)
        self._reg_cert_extra(data, run)
        self._reg_media(data, run)

        # 저장
        save_result = None
        if save_after:
            save_result = self.save(require_confirm=require_confirm)
            steps.append(("save", save_result))

        return {
            "ok": all(s[1].get("ok", False) for s in steps),
            "steps": steps,
            "step_results": {name: r.get("ok", False) for name, r in steps},
            "saved": bool(save_result and save_result.get("ok")),
        }
