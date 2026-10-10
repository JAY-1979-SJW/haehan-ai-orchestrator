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

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login
from scripts.naver.smartstore.product.postflight import postflight
from scripts.naver.smartstore.product.preflight import preflight
from scripts.site_engine.site_session_safety import assert_session_integrity

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

        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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

        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
            except Exception:  # noqa: BLE001 - 여러 셀렉터/유형을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속하거나 상위에서 재시도(2026-09-28 검토)
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
                except Exception:  # noqa: BLE001 - 여러 셀렉터/유형을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속하거나 상위에서 재시도(2026-09-28 검토)
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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

    def set_origin(
        self,
        origin_type: str,
        continent: str | None = None,
        country: str | None = None,
        importer: str | None = None,
    ) -> dict:
        """원산지 설정.

        2026-08-26 실측 확정: 기본값이 항상 "국산"으로 미리 선택돼 있어서
        수입산 제품인데 그대로 등록하면 원산지 오표기가 된다. 반드시 실제
        제품정보(예: 상품정보제공고시)와 대조해서 명시적으로 채운다.

        Args:
            origin_type: "국산" | "수입산" | "기타"
            continent: origin_type="수입산"일 때만 필요. 예: "아시아"
            country: origin_type="수입산"일 때만 필요. 예: "중국"
            importer: origin_type="수입산"일 때 postflight 필수 항목
                (`vm.viewData.originAreaInfo.importer`). 예: "메종드컨셉(주)"

        드롭다운은 "상품 주요정보" 섹션이 접혀 있으면 안 보이므로, 접혀있으면
        먼저 펼친다. 각 단계는 클릭 직후 "선택한 값이 화면 텍스트에 반영됐는지"로
        검증한다(맹목 클릭 금지 — set_category 와 동일 원칙).
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        self._expand_origin_section()

        err = self._select_origin_type(origin_type)
        if err:
            return err

        if origin_type == "수입산":
            err = self._select_import_origin(continent, country, importer)
            if err:
                return err

        # 검증
        final_txt = self.page.evaluate("document.body.innerText")
        idx = final_txt.find("원산지")
        segment = final_txt[idx : idx + 120] if idx >= 0 else ""
        ok = origin_type in segment and (origin_type != "수입산" or (continent in segment and country in segment))
        if not ok:
            return {"ok": False, "error": "검증 실패", "segment": segment}
        _log.info("[gen-reg] 원산지: %s %s %s", origin_type, continent or "", country or "")
        return {"ok": True, "origin_type": origin_type, "continent": continent, "country": country}

    def _expand_origin_section(self) -> None:
        # "상품 주요정보" 섹션이 접혀 있으면 펼친다.
        # ⚠ 헤더 클릭은 토글이라, 이미 펼쳐진 상태에서 또 누르면 도로 접힌다.
        # 반드시 "원산지" 레이블이 실제로 DOM에 있는지 먼저 확인하고, 없을 때만 클릭한다.
        try:
            has_origin_label = self.page.evaluate("""
                () => !!Array.from(document.querySelectorAll('label,div,span')).find(e =>
                    e.innerText && e.innerText.trim() === '원산지'
                )
            """)
            if not has_origin_label:
                self.page.get_by_text("상품 주요정보", exact=True).first.click(timeout=3000)
                time.sleep(0.8)
        except Exception:  # noqa: BLE001 - 여러 셀렉터/유형을 순차 시도하는 best-effort — 하나 실패해도 다음으로 계속하거나 상위에서 재시도(2026-09-28 검토)
            pass

    def _select_origin_type(self, origin_type: str) -> dict | None:
        """원산지 유형(국산/수입산/기타) 선택. 실패 시 반환할 에러 dict, 성공이면 None."""
        try:
            # 1) 원산지 유형(국산/수입산/기타) 드롭다운.
            # 기본값이 "국산"이지만 재호출 시 이미 다른 값일 수 있으므로 텍스트를
            # 하드코딩하지 않고, "원산지" 레이블 뒤 첫 드롭다운을 좌표로 특정한다.
            trigger = self.page.evaluate("""
                () => {
                    const label = Array.from(document.querySelectorAll('label,div,span')).find(e =>
                        e.innerText && e.innerText.trim() === '원산지'
                    );
                    if (!label) return null;
                    label.scrollIntoView({block: 'center'});
                    const lr = label.getBoundingClientRect();
                    // "원산지" 레이블과 같은 가로줄(±20px) 안에서, 오른쪽에 있고
                    // 값이 국산/수입산/기타 중 하나인 후보를 x좌표 기준 가장 가까운 것으로 선택
                    const candidates = Array.from(document.querySelectorAll('*')).filter(e =>
                        e.children.length === 0 && ['국산', '수입산', '기타'].includes((e.innerText || '').trim())
                    ).map(e => {
                        const r = e.getBoundingClientRect();
                        return {el: e, x: r.x, y: r.y, w: r.width, h: r.height};
                    }).filter(c => c.w > 0 && Math.abs((c.y + c.h/2) - (lr.y + lr.height/2)) < 20 && c.x > lr.x);
                    if (!candidates.length) return null;
                    candidates.sort((a, b) => a.x - b.x);
                    const c = candidates[0];
                    return {x: c.x + c.w/2, y: c.y + c.h/2, rowY: lr.y + lr.height/2};
                }
            """)
            if not trigger:
                return {"ok": False, "error": "원산지 유형 드롭다운 트리거 못찾음"}
            self.page.mouse.click(trigger["x"], trigger["y"])
            time.sleep(0.5)
            self.page.get_by_text(origin_type, exact=True).first.click(timeout=5000)
            time.sleep(0.7)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"origin_type 선택 실패: {str(e)[:100]}"}
        return None

    def _select_import_origin(self, continent, country, importer) -> dict | None:
        """수입산 대륙/국가/수입사 입력. 실패 시 반환할 에러 dict, 성공이면 None."""
        if not continent or not country:
            return {"ok": False, "error": "수입산은 continent/country 필수"}

        err = self._pick_continent_country(continent, country)
        if err:
            return err

        if importer:
            return self._fill_importer(importer)
        return None

    def _origin_row_select_coords(self) -> list[dict]:
        """원산지 라벨과 같은 가로줄(±20px)에 있는 "선택" 드롭다운 좌표.
                인증선택/인증정보 등 다른 "선택" 드롭다운과 섞이지 않게 걸러낸다.

                ⚠ row_y 를 한 번 계산해서 재사용하면 안 된다 — 드롭다운 옵션을
                클릭할 때마다(scrollIntoView 부작용으로) 페이지 스크롤 위치가
                바뀌어서 라벨의 화면상 y좌표도 매번 달라진다(2026-08-26 실측:
                대륙 선택 후 국가 드롭다운을 못 찾던 원인). **매 호출마다
                라벨 위치를 새로 조회**한다."""
        coords = self.page.evaluate(
            """
                    () => {
                        const label = Array.from(document.querySelectorAll('label,div,span')).find(e =>
                            e.innerText && e.innerText.trim() === '원산지'
                        );
                        if (!label) return [];
                        const lr = label.getBoundingClientRect();
                        const rowY = lr.y + lr.height / 2;
                        const els = Array.from(document.querySelectorAll('*')).filter(e =>
                            e.children.length === 0 && e.innerText && e.innerText.trim() === '선택'
                        );
                        return els.map(e => {
                            const r = e.getBoundingClientRect();
                            return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width};
                        }).filter(c => c.w > 0 && Math.abs(c.y - rowY) < 20);
                    }
                    """
        )
        coords.sort(key=lambda c: c["x"])
        return coords

    def _origin_click_option(self, value: str) -> bool:
        """열린 드롭다운에서 정확한 텍스트의 옵션을 클릭.

                2026-08-26 실측 함정 2가지:
                1. `get_by_text(value, exact=True)`가 실제 리스트 항목보다
                   검색어 하이라이트용 `<strong>value</strong>`(화면에 안 보임)를
                   먼저 잡아 timeout 난다 — 반드시 `div.option`으로 좁힌다.
                2. 국가처럼 목록이 길면 항목이 뷰포트 밖(y가 window.innerHeight보다
                   훨씬 큼)에 있다 — 클릭 전 `scrollIntoView({block:'center'})` 필수,
                   안 하면 좌표만 유효해 보이고 클릭이 조용히 실패한다.
                """
        coords = self.page.evaluate(
            """
                    (value) => {
                        const els = Array.from(document.querySelectorAll('div.option')).filter(e =>
                            e.innerText && e.innerText.trim() === value
                        );
                        if (!els.length) return null;
                        els[0].scrollIntoView({block: 'center'});
                        const r = els[0].getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                    """,
            value,
        )
        if not coords:
            return False
        self.page.mouse.click(coords["x"], coords["y"])
        return True

    def _pick_continent_country(self, continent: str, country: str) -> dict | None:
        try:
            # 2) 대륙 드롭다운
            coords = self._origin_row_select_coords()
            if len(coords) < 2:
                return {"ok": False, "error": f"원산지 대륙/국가 드롭다운 못찾음 (같은 줄 후보 {len(coords)}개)"}
            self.page.mouse.click(coords[0]["x"], coords[0]["y"])
            time.sleep(0.6)
            if not self._origin_click_option(continent):
                return {"ok": False, "error": f"대륙 옵션 못찾음: {continent}"}
            time.sleep(0.6)

            # 3) 국가 드롭다운 — 대륙 선택 후 좌표 재조회(레이아웃 변동)
            coords2 = self._origin_row_select_coords()
            if not coords2:
                return {"ok": False, "error": "원산지 국가 드롭다운 못찾음"}
            self.page.mouse.click(coords2[0]["x"], coords2[0]["y"])
            time.sleep(0.6)
            if not self._origin_click_option(country):
                return {"ok": False, "error": f"국가 옵션 못찾음: {country}"}
            time.sleep(0.6)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"대륙/국가 선택 실패: {str(e)[:100]}"}
        return None

    def _fill_importer(self, importer: str) -> dict | None:
        try:
            imp_loc = self.page.locator('input[placeholder="수입사입력"]')
            if imp_loc.count() > 0:
                imp_loc.first.fill(importer)
                time.sleep(0.3)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"수입사 입력 실패: {str(e)[:100]}"}
        return None

    def set_manufacturer(self, name: str) -> dict:
        """제조자(사) 설정 — selectize 자동완성 입력.

        함정: `input[placeholder='제조자(사)를 입력해주세요.']` 에 그냥 fill()
        하면 값이 안 붙는다(selectize가 실제 폼 상태를 별도 hidden 값으로
        관리). 반드시 클릭 → 키보드 타이핑 → Enter(옵션 리스트 생성 트리거)
        → `div.create.active`("직접입력: {name}") 클릭까지 해야 실제
        "선택된 제조자(사) : {name}" 문구로 반영된다.
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        try:
            loc = self.page.locator('input[placeholder="제조자(사)를 입력해주세요."]')
            if loc.count() == 0:
                return {"ok": False, "error": "제조자(사) 입력창 못찾음"}
            loc.first.click(timeout=3000)
            time.sleep(0.3)
            self.page.keyboard.type(name, delay=60)
            time.sleep(0.6)
            self.page.keyboard.press("Enter")
            time.sleep(0.6)

            coords = self.page.evaluate("""
                () => {
                    const el = document.querySelector('div.create.active');
                    if (!el) return null;
                    el.scrollIntoView({block: 'center'});
                    const r = el.getBoundingClientRect();
                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            """)
            if not coords:
                return {"ok": False, "error": "제조자(사) 자동완성 옵션 못찾음"}
            self.page.mouse.click(coords["x"], coords["y"])
            time.sleep(0.6)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"제조자(사) 입력 실패: {str(e)[:100]}"}

        final_txt = self.page.evaluate("document.body.innerText")
        idx = final_txt.find("선택된 제조자(사)")
        segment = final_txt[idx : idx + 60] if idx >= 0 else ""
        if name not in segment:
            return {"ok": False, "error": "검증 실패", "segment": segment}
        _log.info("[gen-reg] 제조자(사): %s", name)
        return {"ok": True, "manufacturer": name}

    def set_customer_service_phone(self, phone: str) -> dict:
        """A/S 책임자 또는 소비자 상담 관련 전화번호 입력.

        라디오 2개("A/S 책임자" / "소비자 상담 관련 전화번호") 중 하나가
        기본 선택돼 있고, 그 아래 공용 텍스트 입력창 하나에 번호를 채우면
        된다(라디오 값에 따라 문구만 바뀌고 입력창은 공유).
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        try:
            coords = self.page.evaluate("""
                () => {
                    const label = Array.from(document.querySelectorAll('*')).find(e =>
                        e.innerText && e.innerText.trim().startsWith('A/S 책임자 또는 소비자')
                    );
                    if (!label) return null;
                    const lr = label.getBoundingClientRect();
                    const inp = Array.from(document.querySelectorAll('input[type=text]')).map(i => {
                        const r = i.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2, dy: r.y - lr.y, w: r.width};
                    }).filter(i => i.dy > 0 && i.dy < 60 && i.w > 0);
                    return inp.length ? inp[0] : null;
                }
            """)
            if not coords:
                return {"ok": False, "error": "A/S 전화번호 입력창 못찾음"}
            self.page.mouse.click(coords["x"], coords["y"])
            time.sleep(0.3)
            self.page.keyboard.type(phone, delay=40)
            time.sleep(0.4)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": f"A/S 전화번호 입력 실패: {str(e)[:100]}"}

        actual = self.page.evaluate(
            """(c) => {
                const el = document.elementFromPoint(c.x, c.y);
                return el && 'value' in el ? el.value : null;
            }""",
            coords,
        )
        if not actual or phone not in actual:
            return {"ok": False, "error": "검증 실패", "value": actual}
        _log.info("[gen-reg] A/S 전화번호: %s", phone)
        return {"ok": True, "phone": phone}

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

            self._fill_category_search(category_name)
            target = self._find_category_option(category_name)
            self._click_category_option(target)
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def _fill_category_search(self, category_name: str) -> None:
        """카테고리 입력창에 검색어를 채우고 input/focus 이벤트를 발생시킨다."""
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

    def _find_category_option(self, category_name: str):
        """원하는 카테고리 경로(마지막 노드 일치)가 뜰 때까지 폴링해 해당 옵션을 반환(없으면 None)."""
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
            except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
                continue
        return target

    def _click_category_option(self, target) -> None:
        """찾은 옵션 클릭, 실패하면 키보드(ArrowDown+Enter) 폴백."""
        try:
            if target is not None:
                target.click(timeout=3000, force=True)
                time.sleep(0.8)
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            self.page.keyboard.press("ArrowDown")
            time.sleep(0.3)
            self.page.keyboard.press("Enter")
            time.sleep(0.8)

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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
                except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
            except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
                return False

        if _has_input():
            return True
        try:
            n = self.page.locator("a.btn-add-img").count()
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return False
        for i in range(min(n, 5)):
            try:
                btn = self.page.locator("a.btn-add-img").nth(i)
                btn.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.4)
                btn.click(timeout=4000)
            except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    def _uploaded_image_count(self) -> int:
        """폼에 반영된 업로드 이미지 개수 (네이버 CDN 경로 기준)."""
        try:
            return self.page.evaluate(
                """() => [...document.querySelectorAll('img')]
                        .filter(e => /phinf|pstatic|blob:/.test(e.src || '')).length"""
            )
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return -1

    # ── 저장 (사용자 명시 호출 필수) ─────────────────────────────────────

    def save(self, require_confirm: bool = True, *, require_ready: bool = False) -> dict:
        """등록 (★ 사용자 명시 호출 필수).

        require_ready=True 면 저장 전에 postflight 를 돌려 **채울 수 있는 필수 항목이
        남아 있거나 위험 설정이 켜져 있으면 저장하지 않는다.**

        기본값이 False 인 이유는 기존 호출부의 동작을 바꾸지 않기 위해서다.
        다만 점검 결과는 기본값에서도 항상 로그로 남긴다 — 조용히 지나가는 것이
        가장 위험하다(실측: 예약구매가 켜진 줄 모르고 저장할 뻔했다).
        """
        if not self._ensure_opened():
            return {"ok": False, "error": "open_failed"}

        report = postflight(self.page)
        for w in report.warnings:
            _log.warning("[postflight] %s", w)
        for m in report.actionable_missing:
            _log.warning("[postflight] 필수 미입력: [%s] %s (%s)", m.section, m.label, m.ng)
        if require_ready and not report.ready:
            _log.error("[postflight] 저장 중단 — %s", report.summary())
            return {
                "ok": False,
                "error": "postflight_not_ready",
                "postflight": report.to_dict(),
            }

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
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 폼 자동화 — 각 단계 실패는 항상 {ok: False, error} 로 반환해 호출부가 확인 후 중단하도록 함(실제 저장은 save() 명시 호출 시에만, log_critical 감사로그 남김), 결제 없음(2026-09-28 검토)
            return {"ok": False, "error": str(e)[:80]}

    # ── 통합 원샷 등록 ───────────────────────────────────────────────────

    def _ordered_steps(self, data: dict) -> list:
        """register_product 단계 목록 (이름, 함수, 인자) — 데이터에 값이 있는 단계만."""
        ordered: list[tuple[str, Any, Any]] = []
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
        return ordered

    def _save_if_ok(self, save_after: bool, failed_at: str | None, require_confirm: bool, steps: list):
        """모든 단계가 성공했을 때만 저장. 실패가 있으면 저장하지 않는다."""
        save_result = None
        if save_after and failed_at is None:
            save_result = self.save(require_confirm=require_confirm)
            steps.append(("save", save_result))
        elif save_after and failed_at:
            _log.error("[gen-reg] '%s' 실패로 저장을 건너뜀", failed_at)
        return save_result

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

        ordered = self._ordered_steps(data)

        for name, fn, arg in ordered:
            if not run(name, fn, arg):
                break

        save_result = self._save_if_ok(save_after, failed_at, require_confirm, steps)

        return {
            "ok": failed_at is None and all(s[1].get("ok", False) for s in steps),
            "failed_at": failed_at,
            "aborted": failed_at is not None,
            "steps": steps,
            "step_results": {n: r.get("ok", False) for n, r in steps},
            "saved": bool(save_result and save_result.get("ok")),
        }
