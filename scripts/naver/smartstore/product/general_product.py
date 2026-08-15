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

from playwright.sync_api import Page

from scripts.critical_logger import log_critical
from scripts.logger import get_logger
from scripts.naver.auth import ensure_naver_login
from scripts.naver.smartstore.product.preflight import preflight
from scripts.site_session_safety import assert_session_integrity

_log = get_logger(__name__)

DASHBOARD = "https://sell.smartstore.naver.com/#/home/dashboard"
PRODUCTS_NEW_URL = "https://sell.smartstore.naver.com/#/products/new"

# 폼 렌더링 확인용 셀렉터 (하나라도 나타나면 진입 성공)
_FORM_READY_SELS = [
    'input[name="product.salePrice"]',
    'input[name="product.name"]',
    'input[name="product.stockQuantity"]',
    'input[placeholder*="상품명"]',
    'input[placeholder*="판매가"]',
]

# 상품 유형 선택 모달 — "일반상품" 버튼 후보
_PRODUCT_TYPE_BTN = [
    "일반 상품",
    "일반상품",
    "단일 상품",
]


def _normalize_field_value(v: str) -> str:
    """입력값 대조용 정규화 — 콤마·공백·통화기호 차이를 무시.

    판매가는 화면에서 '55,000' 처럼 콤마가 붙어 되돌아오므로 그대로 비교하면
    항상 불일치로 잡힌다.
    """
    return (v or "").replace(",", "").replace(" ", "").replace("원", "").strip()


class GeneralProductRegister:
    """일반 상품 등록 자동화 (가격/재고 포함)."""

    def __init__(self, page: Page):
        self.page = page
        self._opened = False

    # ── 초기화: 사이드바 클릭으로 진입 ──────────────────────────────────

    def open(self, timeout_s: int = 30) -> bool:
        """상품 등록 페이지 진입.

        전략 1 (기본): 직접 URL 이동 (#/products/new) → 팝업 처리 → 폼 렌더링 대기
        전략 2 (fallback): 사이드바 클릭 방식
        """
        r = ensure_naver_login(self.page)
        assert_session_integrity(r, site="smartstore", workflow="product_general_open")
        if not r.get("ok"):
            return False

        # ── 전략 1: 직접 URL 이동 ──────────────────────────────────────
        if self._open_via_url(timeout_s):
            return True

        _log.warning("[gen-reg] 직접 URL 진입 실패 — 사이드바 클릭 방식으로 재시도")

        # ── 전략 2: 사이드바 클릭 (fallback) ───────────────────────────
        return self._open_via_sidebar(timeout_s)

    def _open_via_url(self, timeout_s: int = 30) -> bool:
        """#/products/new 직접 이동 → 팝업 처리 → 폼 렌더링 대기."""
        try:
            from scripts.naver.smartstore.navigation.popup_handler import dismiss_all_popups

            self.page.goto(PRODUCTS_NEW_URL, timeout=timeout_s * 1000, wait_until="domcontentloaded")
            time.sleep(3)

            # 팝업/공지 처리
            dismiss_all_popups(self.page)
            time.sleep(1)

            # 상품 유형 선택 모달 처리 ("일반상품" 선택)
            self._select_product_type()
            time.sleep(2)

            # 폼 렌더링 대기 (최대 timeout_s 초)
            if self._wait_for_form(timeout_s=15):
                _log.info("[gen-reg] 직접 URL 진입 성공: %s", self.page.url)
                self._opened = True
                log_critical("OTHER", "일반 상품 등록 페이지 진입", mode="url_direct")
                return True

            return False

        except Exception as e:
            _log.warning("[gen-reg] 직접 URL 진입 오류: %s", e)
            return False

    def _open_via_sidebar(self, timeout_s: int = 30) -> bool:
        """대시보드 → 사이드바 클릭 방식 (fallback)."""
        try:
            from scripts.naver.smartstore.navigation.popup_handler import dismiss_all_popups

            self.page.goto(DASHBOARD, timeout=timeout_s * 1000, wait_until="domcontentloaded")
            time.sleep(4)
            dismiss_all_popups(self.page)

            # '상품관리' 클릭
            if not self._click_sidebar_text("상품관리"):
                _log.error("[gen-reg] 사이드바 '상품관리' 클릭 실패")
                return False
            time.sleep(3)

            # '상품 등록' 탐색 — 사이드바(x<280) + 콘텐츠 영역(x<600) 모두 탐색
            for x_max in [280, 600]:
                if self._click_sidebar_text("상품 등록", x_max=x_max):
                    time.sleep(4)
                    self._select_product_type()
                    time.sleep(2)
                    if self._wait_for_form(timeout_s=15):
                        _log.info("[gen-reg] 사이드바 방식 진입 성공")
                        self._opened = True
                        log_critical("OTHER", "일반 상품 등록 페이지 진입", mode="sidebar_click")
                        return True

            _log.error("[gen-reg] 사이드바 방식 실패")
            return False

        except Exception as e:
            _log.error("[gen-reg] 사이드바 방식 오류: %s", e)
            return False

    def _select_product_type(self) -> None:
        """상품 유형 선택 모달이 뜨면 '일반 상품' 선택."""
        for btn_txt in _PRODUCT_TYPE_BTN:
            try:
                btn = self.page.get_by_text(btn_txt, exact=True).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=3000)
                    time.sleep(1)
                    _log.info("[gen-reg] 상품 유형 선택: '%s'", btn_txt)
                    return
            except Exception:
                pass

    def _wait_for_form(self, timeout_s: int = 15) -> bool:
        """폼 렌더링 대기 — 하나라도 나타나면 True."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for sel in _FORM_READY_SELS:
                try:
                    el = self.page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=500):
                        return True
                except Exception:
                    pass
            time.sleep(0.8)
        return False

    def _click_sidebar_text(self, text: str, x_max: int = 280) -> bool:
        """사이드바 메뉴 텍스트로 좌표 찾아 마우스 클릭."""
        coords = self.page.evaluate(
            r"""
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
        """,
            {"text": text, "xMax": x_max},
        )
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

            # 입력 직후 실제 값 대조 — fill 이 성공해도 Angular 가 되돌리거나
            # 마스킹/포맷팅으로 값이 달라질 수 있다. "ok:True 인데 실제로는 안 들어감"
            # 을 막기 위해 반드시 읽어서 확인한다(2026-08-15 추가).
            actual = el.input_value(timeout=3000)
            if _normalize_field_value(actual) != _normalize_field_value(str(value)):
                _log.error(
                    "[gen-reg] %s 입력 검증 실패 — 요청 %r vs 실제 %r",
                    label or selector,
                    str(value),
                    actual,
                )
                return {"ok": False, "error": "verify_mismatch", "requested": str(value), "actual": actual}

            _log.info("[gen-reg] %s: %s", label or selector, value)
            return {"ok": True, "value": value, "actual": actual}
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
        """카테고리 검색 + **원하는 항목 지정 선택** (첫 항목 맹목 클릭 금지).

        2026-08-15 실측으로 확인한 함정:
          - "인테리어조명" 검색 시 자동완성 1순위가 'LED모듈' 이다.
            첫 항목을 무조건 클릭하면 엉뚱한 카테고리가 선택된다.
          - 이전 검색의 잔상이 남아 있어 즉시 클릭하면 이전 결과를 고른다.
            → 원하는 문자열이 후보에 나타날 때까지 폴링한 뒤 그 항목을 클릭한다.
          - 선택된 경로는 `.info-result.text-info` 에 "선택한 카테고리 : <경로>" 로 표시된다.
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        try:
            # 이전 동작에서 뜬 모달(KC인증 안내 등)이 남아 있으면 이후 클릭을 전부
            # 가로챈다("intercepts pointer events"). 먼저 정리한다(2026-08-15).
            self._dismiss_blocking_modals()

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
            # 원하는 카테고리 경로가 뜰 때까지 폴링 (이전 검색 잔상 회피)
            #
            # ⚠ has_text=category_name 만 쓰면 안 된다. 드롭다운에는 카테고리 경로 외에
            #   상품명 자동완성('헤이그 ... 인테리어조명(등 미포함)')도 섞여 나오고,
            #   그게 먼저 잡히면 보이지도 않아 클릭이 타임아웃된다(2026-08-15 실측).
            #   → '>' 로 시작하는 경로형이면서, 마지막 노드가 요청값인 것만 고른다.
            target = None
            for _ in range(12):
                time.sleep(0.8)
                try:
                    opts = self.page.locator(".selectize-dropdown .option")
                    n = min(opts.count(), 20)
                    for i in range(n):
                        o = opts.nth(i)
                        if not o.is_visible(timeout=400):
                            continue
                        txt = (o.inner_text(timeout=400) or "").strip()
                        if ">" not in txt:
                            continue  # 상품명 자동완성 제외
                        if txt.rsplit(">", 1)[-1].strip() == category_name:
                            target = o
                            break
                    if target is not None:
                        break
                except Exception:
                    continue

            try:
                if target is not None:
                    target.click(timeout=3000, force=True)
                    time.sleep(0.8)
            except Exception:
                self.page.keyboard.press("ArrowDown")
                time.sleep(0.3)
                self.page.keyboard.press("Enter")
                time.sleep(0.8)
            # 카테고리 선택 시 'KC인증 필수 카테고리' 모달이 뜬다 → 닫아야 다음 단계가 산다
            self._dismiss_blocking_modals()

            # 클릭 선택이 반영되지 않았으면 위젯 API 로 재시도 (확실한 경로)
            if category_name not in self.get_selected_category():
                w = self._set_category_via_widget(category_name)
                if w.get("ok"):
                    time.sleep(2.0)
                    self._dismiss_blocking_modals()
                    _log.info("[gen-reg] 카테고리 위젯 API 로 설정: %s (id=%s)", category_name, w.get("key"))

            # 선택 결과 검증 — 자동완성 첫 항목을 무조건 클릭하는 구조라
            # 엉뚱한 카테고리가 잡혀도 그대로 진행되던 문제를 막는다(2026-08-15 추가).
            selected = self.get_selected_category()
            if category_name not in selected:
                _log.error(
                    "[gen-reg] 카테고리 검증 실패 — 요청 %r 인데 선택된 값 %r",
                    category_name,
                    selected[:80],
                )
                return {
                    "ok": False,
                    "error": "category_mismatch",
                    "requested": category_name,
                    "selected": selected[:120],
                }

            _log.info("[gen-reg] 카테고리: %s (선택됨: %s)", category_name, selected[:60])
            return {"ok": True, "category": category_name, "selected": selected[:120]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}

    _SELECTIZE_SET_JS = r"""
    (wantText) => {
      const inp = document.querySelector('input[placeholder*="카테고리"]:not([type=radio]):not([type=checkbox])');
      const ctrl = inp ? inp.closest('.selectize-control') : null;
      if (!ctrl) return {ok:false, why:'no_ctrl'};
      const cands = [...ctrl.parentElement.querySelectorAll('input.selectized')].filter(e => e.selectize);
      if (!cands.length) return {ok:false, why:'no_instance'};
      const s = cands[0].selectize;
      const entry = Object.entries(s.options).find(([k,v]) =>
          String(v.text||v.name||v.label||'').trim() === wantText);
      if (!entry) return {ok:false, why:'option_not_found'};
      const [key] = entry;
      if (typeof s.setValue === 'function') { s.setValue(key, false); return {ok:true, key:key}; }
      return {ok:false, why:'no_setter'};
    }
    """

    def _set_category_via_widget(self, category_name: str) -> dict:
        """Selectize 위젯 인스턴스 API 로 카테고리 직접 설정.

        DOM 클릭 방식이 통하지 않는 경우의 확실한 경로(2026-08-15 실측 확립).
        배경: 카테고리 드롭다운의 `.option` 은 페이지 전역에서 204개가 잡히고
        (상단 검색위젯 '수취인명', 상품명 자동완성 등이 섞임), 좁혀도 이전 검색
        잔상 때문에 재검색이 트리거되지 않아 클릭 선택이 실패했다.
        위젯 인스턴스(input.selectized 의 .selectize)의 setValue() 는 확실히 동작한다.
        """
        try:
            return self.page.evaluate(self._SELECTIZE_SET_JS, category_name)
        except Exception as e:
            return {"ok": False, "why": type(e).__name__, "error": str(e)[:80]}

    _SELECTIZE_GENERIC_JS = r"""
    (args) => {
      const el = document.querySelector(args.selector);
      if (!el) return {ok:false, why:'no_element'};
      if (!el.selectize) return {ok:false, why:'no_selectize_instance'};
      const s = el.selectize;
      if (args.byValue) { s.setValue(args.byValue, false); return {ok:true, set:args.byValue}; }
      const entry = Object.entries(s.options).find(([k,v]) =>
          String(v.text || v.name || v.label || '').trim() === args.byLabel);
      if (!entry) return {ok:false, why:'label_not_found',
                          have: Object.values(s.options).map(v=>String(v.text||v.name||'').slice(0,20)).slice(0,15)};
      s.setValue(entry[0], false);
      return {ok:true, set:entry[0]};
    }
    """

    def set_selectize(self, selector: str, *, label: str | None = None, value: str | None = None) -> dict:
        """Selectize 위젯 값 설정 (이 폼 드롭다운의 표준 조작 방법).

        2026-08-15 실측으로 확립:
          스마트스토어 상품등록 폼의 드롭다운(카테고리·원산지 등)은 전부 Selectize 위젯이다.
          원본 <select> 는 화면 밖(x≈-9764)에 숨겨져 있어서 Playwright 의 select_option()
          이나 클릭이 통하지 않는다. 반드시 위젯 인스턴스의 setValue() 를 써야 한다.

        label: 화면에 보이는 텍스트(예: "국산")  /  value: 내부 코드(예: "LOCAL")
        """
        if not label and not value:
            return {"ok": False, "why": "label_or_value_required"}
        try:
            return self.page.evaluate(
                self._SELECTIZE_GENERIC_JS,
                {"selector": selector, "byLabel": label, "byValue": value},
            )
        except Exception as e:
            return {"ok": False, "why": type(e).__name__, "error": str(e)[:80]}

    def _dismiss_blocking_modals(self, rounds: int = 4) -> int:
        """클릭을 가로막는 모달/레이어 닫기.

        스마트스토어는 카테고리 선택(KC인증 안내), 공지 등으로 모달을 자주 띄우고,
        열려 있는 동안 다른 요소 클릭이 전부 실패한다("intercepts pointer events").
        저장/발행 버튼은 절대 누르지 않고 닫기/확인만 클릭한다.
        """
        closed = 0
        for _ in range(rounds):
            hit = False
            for sel in (
                '[class*="modal"] button[class*="close"]',
                '[class*="modal"] a[class*="close"]',
                'button:has-text("닫기")',
                'button:has-text("확인")',
            ):
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=700):
                        el.click(timeout=2000)
                        time.sleep(0.7)
                        closed += 1
                        hit = True
                        break
                except Exception:
                    continue
            if not hit:
                break
        return closed

    def get_selected_category(self) -> str:
        """현재 폼에 선택된 카테고리 경로 텍스트.

        2026-08-15 실측: 경로는 하단 안내문 `.info-result.text-info strong` 에만
        정확히 표시된다. body 전체 정규식이나 `.selectize-input .item` 은
        페이지 검색위젯('수취인명' 등)까지 잡혀 오탐이 난다.
        """
        try:
            loc = self.page.locator(".info-result.text-info").first
            raw = (loc.inner_text(timeout=2500) or "").strip()
        except Exception as e:
            _log.debug("[gen-reg] 카테고리 조회 실패: %s", e)
            return ""
        # "선택한 카테고리 : 가구/인테리어>..." → 라벨 제거
        if ":" in raw:
            raw = raw.split(":", 1)[1]
        return raw.strip()

    # ── 이미지 ──────────────────────────────────────────────────────────

    def _open_image_modal(self) -> bool:
        """'내 사진 불러오기' 모달 열기 — file input 은 이 모달 안에만 생성된다.

        2026-08-15 실측: 상품등록 폼에는 input[type=file] 이 아예 없다.
        `a.btn-add-img` 를 눌러야 모달과 함께 생성된다. 또한 **이미 이미지가 채워진
        슬롯은 눌러도 모달이 안 열리므로** 빈 슬롯을 만날 때까지 순회해야 한다.
        """

        def _has_input() -> bool:
            try:
                return self.page.locator("input[type=file]").count() > 0
            except Exception:
                return False

        if _has_input():
            return True
        try:
            n = self.page.locator("a.btn-add-img").count()
        except Exception:
            return False
        for i in range(min(n, 5)):
            try:
                btn = self.page.locator("a.btn-add-img").nth(i)
                btn.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.4)
                btn.click(timeout=4000)
            except Exception:
                continue
            time.sleep(2.0)
            if _has_input():
                return True
        return False

    def upload_main_image(self, image_path: str) -> dict:
        """대표 이미지 업로드 (모달 경유) + 업로드 반영 검증."""
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}
        if not Path(image_path).exists():
            return {"ok": False, "error": "file_not_found"}

        before = self._uploaded_image_count()
        if not self._open_image_modal():
            _log.error("[gen-reg] 대표이미지 모달을 열 수 없음 — a.btn-add-img 확인 필요")
            return {"ok": False, "error": "image_modal_not_opened"}
        try:
            self.page.locator("input[type=file]").first.set_input_files(image_path, timeout=15000)
            time.sleep(5.0)

            after = self._uploaded_image_count()
            if after <= before:
                _log.error(
                    "[gen-reg] 대표이미지 검증 실패 — 업로드 전 %d장, 후 %d장 (증가 없음)",
                    before,
                    after,
                )
                return {"ok": False, "error": "upload_not_reflected", "before": before, "after": after}

            log_critical(
                "FILE_UPLOAD",
                f"일반 상품 대표 이미지: {Path(image_path).name}",
                file=image_path,
                mode="general_product_image_main",
            )
            return {"ok": True, "file": image_path, "before": before, "after": after}
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}

    def _uploaded_image_count(self) -> int:
        """폼에 반영된 업로드 이미지 개수 (네이버 CDN 경로 기준)."""
        try:
            return self.page.evaluate(
                """() => [...document.querySelectorAll('img')]
                        .filter(e => /phinf|pstatic|blob:/.test(e.src || '')).length"""
            )
        except Exception:
            return -1

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

    def register_product(
        self,
        data: dict,
        save_after: bool = False,
        require_confirm: bool = True,
        publish: bool = False,
        skip_preflight: bool = False,
    ) -> dict:
        """원샷 등록.

        data:
            name (필수), price (필수), stock (필수),
            category, main_image
            kc_cert / origin_area / delivery_fee_policy / as_phone (판매개시 시 필수)

        publish=True 는 판매개시 의도를 뜻한다. 판매 필수값이 비어 있으면
        브라우저를 열기 전에 거부한다.
        """
        # ── 관문 0: 사전 검증 (브라우저 열기 전) ──────────────────────────
        # 로컬에서 판정 가능한 실패로 60초짜리 브라우저 왕복을 낭비하지 않는다.
        # 실패는 후보를 포함한 구조화된 형태로 돌려줘 스스로 고칠 수 있게 한다.
        if not skip_preflight:
            rep = preflight(data)
            for issue in rep.issues:
                _log.warning("[preflight] %s | %s | %s", issue.severity, issue.field, issue.message)
            if not rep.can_fill:
                _log.error("[preflight] 진행 불가 — 브라우저를 열지 않음: %s", rep.summary())
                return {
                    "ok": False,
                    "aborted": True,
                    "failed_at": "preflight",
                    "issues": rep.as_dicts(),
                    "steps": [],
                    "step_results": {},
                    "saved": False,
                }
            if publish and not rep.can_publish:
                _log.error("[preflight] 판매개시 거부 — 필수값 누락: %s", rep.summary())
                return {
                    "ok": False,
                    "aborted": True,
                    "failed_at": "preflight_publish",
                    "issues": rep.as_dicts(),
                    "steps": [],
                    "step_results": {},
                    "saved": False,
                }

        if not self.open():
            return {"ok": False, "error": "open_failed"}

        steps: list[tuple[str, dict]] = []
        failed_at: str | None = None

        def run(name, fn, *a, **kw) -> bool:
            """단계 실행. 실패하면 즉시 중단 신호를 반환한다.

            이전에는 실패해도 계속 진행하고 마지막에 save 까지 했다. 그러면
            상품명이나 카테고리가 안 들어간 채로 저장되는 사고가 난다.
            → 첫 실패에서 멈추고, 실패 시 저장은 절대 하지 않는다(2026-08-15).
            """
            nonlocal failed_at
            r = fn(*a, **kw)
            steps.append((name, r))
            if not r.get("ok", False):
                failed_at = name
                _log.error("[gen-reg] '%s' 단계 실패 — 이후 단계와 저장을 중단: %s", name, str(r.get("error"))[:100])
                return False
            return True

        ordered = []
        if data.get("category"):
            ordered.append(("category", self.set_category, data["category"]))
        if data.get("name"):
            ordered.append(("name", self.set_product_name, data["name"]))
        if data.get("price") is not None:
            ordered.append(("price", self.set_price, data["price"]))
        if data.get("stock") is not None:
            ordered.append(("stock", self.set_stock, data["stock"]))
        if data.get("main_image"):
            ordered.append(("main_image", self.upload_main_image, data["main_image"]))

        for name, fn, arg in ordered:
            if not run(name, fn, arg):
                break

        save_result = None
        if save_after and failed_at is None:
            save_result = self.save(require_confirm=require_confirm)
            steps.append(("save", save_result))
        elif save_after and failed_at:
            _log.error("[gen-reg] '%s' 실패로 저장을 건너뜀", failed_at)

        return {
            "ok": failed_at is None and all(s[1].get("ok", False) for s in steps),
            "failed_at": failed_at,
            "aborted": failed_at is not None,
            "steps": steps,
            "step_results": {n: r.get("ok", False) for n, r in steps},
            "saved": bool(save_result and save_result.get("ok")),
        }
