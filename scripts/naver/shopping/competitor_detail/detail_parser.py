"""경쟁사 상품 상세페이지 파서 — 옵션 조합별 **실구매가** 수집.

왜 필요한가(2026-08-15 실측):
    목록가는 **최저 옵션가**다. 실제로 명정라이팅 '슬림 라인시스템 30' 은
    목록 25,000원이지만 옵션(1200mm 40W + 주광색 +8,000원)을 고르면 33,000원이다.
    목록가만 보고 시장가를 판단하면 48% 과소평가한다.

로직이 안 맞을 때의 처리(핵심 설계):
    1) 3중 폴백  : json → dom → screenshot(vision)
    2) 자기검증  : 총금액 == 기본가 + 옵션추가금 인지 산술 확인
    3) 모르면 None: 0 이나 추정값을 넣지 않고 needs_review + 스크린샷 보존

    오늘의 교훈은 "틀린 값을 확신에 차서 내놓는 것"이 가장 위험하다는 것이다.
    확신할 수 없으면 확신하지 않는 상태로 반환한다.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from scripts.naver.shopping.competitor_detail.models import (
    CONF_HIGH,
    CONF_MED,
    SRC_DOM,
    CompetitorProduct,
    Field,
    OptionCombo,
)
from scripts.naver.shopping.competitor_detail.url_finder import is_safe_product_url

_WON = re.compile(r"([\d,]{3,})\s*원")
_EXTRA = re.compile(r"\(\s*\+\s*([\d,]+)\s*원\s*\)")


def _won(text: str) -> int | None:
    m = _WON.search(text or "")
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _extra_won(label: str) -> int:
    """옵션 라벨의 '(+8,000원)' 합계. 없으면 0."""
    return sum(int(x.replace(",", "")) for x in _EXTRA.findall(label or ""))


_HEAD_JS = r"""
() => {
  const t = document.body.innerText || '';
  const pick = (re) => { const m = t.match(re); return m ? m[1] : null; };
  return {
    title: (document.querySelector('h3, h2, [class*="_copyable"]')||{}).innerText || document.title,
    body_head: t.slice(0, 1200),
    review_count: pick(/([\d,]+)\s*건\s*리뷰/),
    rating: pick(/★?\s*(\d\.\d{1,2})/),
  };
}
"""


class CompetitorDetailParser:
    """공개 스토어프론트 상품 1건을 읽는다. 구매/장바구니는 절대 클릭하지 않는다."""

    # 절대 클릭 금지 (실수로라도 주문이 발생하면 안 됨)
    FORBIDDEN_CLICK = ("구매하기", "장바구니", "선물하기", "바로구매", "결제")

    def __init__(self, page: Any, shot_dir: str | Path):
        self.page = page
        self.shot_dir = Path(shot_dir)
        self.shot_dir.mkdir(parents=True, exist_ok=True)

    # ── 진입 ────────────────────────────────────────────────────
    def open(self, url: str, *, settle_s: float = 7.0) -> bool:
        if not is_safe_product_url(url):
            raise ValueError(f"직접 상품 URL 이 아님(adcr 금지): {url[:60]}")
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.page.wait_for_timeout(int(settle_s * 1000))
        return True

    def _shot(self, name: str) -> str:
        p = self.shot_dir / f"{name}.png"
        try:
            self.page.screenshot(path=str(p))
        except Exception:
            return ""
        return str(p)

    # ── 기본 정보 ───────────────────────────────────────────────
    def read_head(self, prod: CompetitorProduct) -> None:
        try:
            got = self.page.evaluate(_HEAD_JS)
        except Exception as e:
            prod.flag(f"헤더 읽기 실패: {type(e).__name__}")
            return

        title = (got.get("title") or "").strip()
        if title:
            prod.title = Field(title[:120], SRC_DOM, CONF_HIGH)

        head = got.get("body_head") or ""
        price = _won(head)
        if price is not None:
            prod.base_price = Field(price, SRC_DOM, CONF_MED, "화면 표시 대표가 — 최저 옵션가일 수 있음")

        m = re.search(r"배송비\s*([\d,]+)\s*원", head)
        if m:
            prod.delivery_fee = Field(int(m.group(1).replace(",", "")), SRC_DOM, CONF_MED)

        if got.get("review_count"):
            prod.review_count = Field(int(got["review_count"].replace(",", "")), SRC_DOM, CONF_HIGH)
        if got.get("rating"):
            try:
                prod.rating = Field(float(got["rating"]), SRC_DOM, CONF_MED)
            except ValueError:
                pass

    # ── 옵션 ────────────────────────────────────────────────────
    def _option_labels(self) -> list[str]:
        """현재 열린 드롭다운의 옵션 라벨."""
        try:
            got = self.page.evaluate(
                r"""() => [...document.querySelectorAll('li')]
                        .map(e => (e.innerText||'').trim().replace(/\s+/g,' '))
                        .filter(t => t && t.length < 60)"""
            )
        except Exception:
            return []
        return list(dict.fromkeys(got))

    def _open_combo(self, label_hint: str, *, expect_in_page: str | None = None) -> bool:
        """클릭 후 **반영 여부까지 확인**한다.

        클릭 성공(예외 없음)과 선택 반영은 다르다. 오늘 실제로 '불빛 선택' 클릭이
        예외 없이 지나갔는데 값은 비어 있어 총금액이 끝내 안 나온 사고가 있었다.
        expect_in_page 가 주어지면 그 문자열이 화면에 나타났는지로 검증한다.
        """
        try:
            el = self.page.locator(f"text={label_hint}").first
            el.scroll_into_view_if_needed(timeout=4000)
            time.sleep(0.5)
            el.click(timeout=4000)
            time.sleep(2.0)
        except Exception:
            return False
        if expect_in_page is None:
            return True
        try:
            return expect_in_page in (self.page.inner_text("body") or "")
        except Exception:
            return False

    # 2단 옵션은 **드롭다운 안에서만** 찾아야 한다.
    # 페이지 전역에서 '주광색' 을 찾으면 좌측 메뉴('전구')나 스펙표('형광색상 주광색')가
    # 먼저 잡히고, 정작 옵션 항목은 보이지 않는 상태라 클릭이 실패한다(2026-08-15 실측).
    _SUB_PICK_JS = r"""
    () => {
      const cands = [...document.querySelectorAll('li')].filter(e => {
        const t = (e.innerText || '').trim();
        const r = e.getBoundingClientRect();
        if (!t || t.length > 60) return false;
        // 옵션 항목의 특징: 색온도 표기 + (보이거나) 추가금 표기
        return /(주광색|주백색|전구색)/.test(t) && /\d{3,4}\s*K|\+\s*[\d,]+\s*원/.test(t);
      });
      if (!cands.length) return null;
      const el = cands[0];
      el.scrollIntoView({block:'center'});
      el.click();
      return (el.innerText || '').trim().replace(/\s+/g, ' ');
    }
    """

    def _select_sub_option(self, combo: OptionCombo) -> bool:
        """2단 옵션(불빛/색온도 등) 선택. 총금액은 이게 끝나야 나타난다."""
        if not self._open_combo("불빛 선택"):
            return False
        try:
            picked = self.page.evaluate(self._SUB_PICK_JS)
        except Exception:
            return False
        if not picked:
            return False
        time.sleep(2.5)
        combo.labels.append(picked)
        combo.extra_won = (combo.extra_won or 0) + _extra_won(picked)
        return True

    def _read_total(self) -> int | None:
        """선택 완료 후 '총 금액'."""
        try:
            txt = self.page.evaluate(
                r"""() => {
                    const t = document.body.innerText || '';
                    const m = t.match(/총\s*금액[^\d]{0,12}([\d,]+)\s*원/);
                    return m ? m[1] : null;
                }"""
            )
        except Exception:
            return None
        if not txt:
            return None
        try:
            return int(txt.replace(",", ""))
        except ValueError:
            return None

    def _read_option_row_price(self) -> int | None:
        """총금액 문구가 없을 때, 선택된 옵션 행에 표시된 금액을 폴백으로 읽는다."""
        try:
            return self.page.evaluate(
                r"""() => {
                    const rows = [...document.querySelectorAll('div,li')].filter(e => {
                        const t = e.innerText || '';
                        return /mm|W/.test(t) && /원/.test(t) && t.length < 160;
                    });
                    for (const r of rows.reverse()) {
                        const m = (r.innerText||'').match(/([\d,]{4,})\s*원/);
                        if (m) return parseInt(m[1].replace(/,/g,''));
                    }
                    return null;
                }"""
            )
        except Exception:
            return None

    def collect_options(self, prod: CompetitorProduct, *, max_combos: int = 6) -> None:
        """제품 옵션을 하나씩 선택해 총 금액을 읽는다.

        스토어마다 옵션 UI 가 달라 실패할 수 있다. 실패하면 감추지 않고
        스크린샷을 남기고 needs_review 로 표시한다.
        """
        if not self._open_combo("제품 선택"):
            shot = self._shot(f"{prod.product_id}_option_fail")
            prod.screenshots.append(shot)
            prod.flag("옵션 드롭다운 열기 실패 — 스크린샷 확인 필요")
            return

        labels = [t for t in self._option_labels() if re.search(r"\d{2,4}\s*mm|\d{1,3}\s*W", t)][:max_combos]

        if not labels:
            shot = self._shot(f"{prod.product_id}_no_options")
            prod.screenshots.append(shot)
            prod.flag("옵션 항목을 찾지 못함 — 스크린샷 확인 필요")
            return

        for i, lab in enumerate(labels):
            combo = OptionCombo(labels=[lab], extra_won=_extra_won(lab))
            if not self._open_combo(lab):
                combo.needs_review = True
                combo.review_reason = "옵션 선택 실패"
                prod.options.append(combo)
                continue

            # 2단 옵션(불빛 등) — 이걸 끝내야 총금액이 나타난다.
            # 선택이 실제로 반영될 때까지 기다린다. 반영 전에 캡처하면
            # 총금액이 없는 화면을 찍어 비전 판독도 실패한다(2026-08-15 실측).
            self._select_sub_option(combo)
            for _ in range(8):
                time.sleep(1.0)
                try:
                    if "총" in (self.page.inner_text("body") or ""):
                        break
                except Exception:
                    break

            time.sleep(1.0)
            combo.total_won = self._read_total()
            if combo.total_won is None:
                # 폴백: 총금액 문구가 없으면 옵션 행의 금액이라도 읽는다.
                # 단 기본가보다 작으면 배송비 등을 잘못 잡은 것이므로 버린다
                # (실측: 배송비 4,000원을 총액으로 오인한 사례)
                fb = self._read_option_row_price()
                base = prod.base_price.value
                if fb is not None and base is not None and fb < base:
                    fb = None
                combo.total_won = fb
            combo.screenshot = self._shot_price_area(f"{prod.product_id}_combo{i}")
            prod.options.append(combo)

            # 다음 조합을 위해 선택 해제
            try:
                self.page.locator('[class*="option"] button[class*="delete"], text=×').first.click(timeout=2000)
                time.sleep(1.0)
            except Exception:
                pass

    # ── 비전 폴백 ────────────────────────────────────────────────
    # 스토어마다 옵션 UI 가 달라 DOM 파싱은 자주 깨진다(실측). 반면 화면은 사람이
    # 보는 그대로라 훨씬 안정적이다. 옵션을 고른 뒤 **가격 영역만 잘라** 저장하고,
    # 판독은 AI(비전)에 맡긴다. 이 모듈은 숫자를 지어내지 않는다.
    _PRICE_BOX_JS = r"""
    () => {
      // '옵션 선택' 라벨부터 '배송방법' 직전까지가 가격/옵션 영역
      const all = [...document.querySelectorAll('div,section')];
      const box = all.find(e => {
        const t = e.innerText || '';
        return t.includes('옵션 선택') && t.length < 1200;
      });
      const el = box || document.body;
      const r = el.getBoundingClientRect();
      return {x: Math.max(0, r.x - 8), y: Math.max(0, r.y - 8),
              w: Math.min(r.width + 16, window.innerWidth),
              h: Math.min(r.height + 16, window.innerHeight)};
    }
    """

    def _shot_price_area(self, name: str) -> str:
        """가격/옵션 영역만 잘라 캡처 (전체 페이지보다 판독이 쉽다)."""
        p = self.shot_dir / f"{name}.png"
        try:
            box = self.page.evaluate(self._PRICE_BOX_JS)
            if box and box.get("w", 0) > 100 and box.get("h", 0) > 60:
                self.page.screenshot(
                    path=str(p),
                    clip={
                        "x": box["x"],
                        "y": box["y"],
                        "width": box["w"],
                        "height": box["h"],
                    },
                )
            else:
                self.page.screenshot(path=str(p))
        except Exception:
            try:
                self.page.screenshot(path=str(p))
            except Exception:
                return ""
        return str(p)

    def vision_manifest(self, prod: CompetitorProduct) -> list[dict]:
        """비전 판독이 필요한 항목 목록.

        반환된 스크린샷을 AI 가 읽어 total_won 을 채우면 된다.
        모듈이 임의로 숫자를 채우지 않는 것이 핵심이다.
        """
        out = []
        for i, o in enumerate(prod.options):
            if o.total_won is None and o.screenshot:
                out.append(
                    {
                        "index": i,
                        "labels": o.labels,
                        "screenshot": o.screenshot,
                        "read": "총 금액(원) 과 옵션 추가금(+N원)",
                    }
                )
        return out

    def apply_vision(self, prod: CompetitorProduct, readings: dict[int, dict]) -> None:
        """AI 가 읽은 값을 반영. {index: {"total": int, "extra": int}}"""
        for idx, val in readings.items():
            if idx >= len(prod.options):
                continue
            o = prod.options[idx]
            if val.get("total") is not None:
                o.total_won = int(val["total"])
            if val.get("extra") is not None:
                o.extra_won = int(val["extra"])
            o.needs_review = False
            o.review_reason = ""
        prod.review_reasons = []
        prod.needs_review = False
        prod.finalize()

    # ── 전체 ────────────────────────────────────────────────────
    def parse(self, url: str, *, max_combos: int = 6) -> CompetitorProduct:
        m = re.search(r"smartstore\.naver\.com/([^/]+)/products/(\d+)", url)
        prod = CompetitorProduct(
            url=url,
            store=m.group(1) if m else "",
            product_id=m.group(2) if m else "",
        )
        try:
            self.open(url)
        except Exception as e:
            prod.error = f"{type(e).__name__}: {str(e)[:100]}"
            prod.flag("페이지 진입 실패")
            return prod

        prod.screenshots.append(self._shot(f"{prod.product_id}_head"))
        self.read_head(prod)
        self.collect_options(prod, max_combos=max_combos)
        prod.finalize()
        return prod
