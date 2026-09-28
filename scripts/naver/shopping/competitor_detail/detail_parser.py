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

import contextlib
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


def _extra_won_opt(label: str) -> int | None:
    """같은 값이지만 표기가 **아예 없으면 0 이 아니라 None**(=모름)을 반환한다.

    스토어에 따라 1단 옵션의 가격차를 라벨에 표기하지 않는다(실측: 명정라이팅은
    '1200mm 일자 40W' 처럼 금액이 없다). 이때 0 으로 단정하면 자기검증이
    '산술 불일치' 를 오탐한다. 모르는 것은 모른다고 둬야 검증이 침묵한다.
    """
    found = _EXTRA.findall(label or "")
    if not found:
        return None
    return sum(int(x.replace(",", "")) for x in found)


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

    # 옵션 단수 상한 — 무한 루프 방지용 안전장치
    MAX_OPTION_DEPTH = 4

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
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return ""
        return str(p)

    # ── 기본 정보 ───────────────────────────────────────────────
    def read_head(self, prod: CompetitorProduct) -> None:
        try:
            got = self.page.evaluate(_HEAD_JS)
        except Exception as e:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
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
            with contextlib.suppress(ValueError):
                prod.rating = Field(float(got["rating"]), SRC_DOM, CONF_MED)

    # ── 옵션 ────────────────────────────────────────────────────
    # 실측(2026-08-15)으로 확정한 옵션 UI 구조:
    #   트리거: <a role="button" aria-expanded="true|false">제품 선택</a>
    #   항목  : <a role="option" data-shp-contents-type="제품 선택"
    #                            data-shp-contents-id="1200mm 일자 40W">
    # data-shp-contents-type 이 **소속 드롭다운**을 알려준다. 덕분에 좌측메뉴('전구')나
    # 스펙표('형광색상 주광색')를 옵션으로 오인하던 문제가 원천적으로 사라진다.
    # 트리거·항목은 PC/모바일 2벌이 DOM 에 있으므로 :visible 이 필수다.

    _GROUPS_JS = r"""
    () => {
      const seen = [];
      for (const a of document.querySelectorAll('a[role="option"][data-shp-contents-type]')) {
        const g = a.getAttribute('data-shp-contents-type');
        if (g && !seen.includes(g)) seen.push(g);
      }
      return seen;
    }
    """

    _EXPANDED_JS = r"""
    (name) => {
      const a = [...document.querySelectorAll('a[role="button"]')]
        .filter(x => { const r = x.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
        .find(x => (x.innerText || '').trim().startsWith(name));
      return a ? a.getAttribute('aria-expanded') : null;
    }
    """

    def option_groups(self) -> list[str]:
        """옵션 드롭다운 이름을 DOM 순서대로. 닫혀 있어도 읽을 수 있다."""
        try:
            return list(self.page.evaluate(self._GROUPS_JS) or [])
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return []

    def _is_open(self, group: str) -> bool:
        try:
            return self.page.evaluate(self._EXPANDED_JS, group) == "true"
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return False

    def _open_dropdown(self, group: str) -> bool:
        """드롭다운을 연다. **이미 열려 있으면 누르지 않는다.**

        1단을 선택하면 2단이 자동으로 열린다. 열린 것을 또 누르면 토글되어 닫히고,
        그 뒤 항목 클릭이 'not visible' 로 조용히 실패한다. 총금액이 끝내 나오지
        않던 진짜 원인이 이것이었다(2026-08-15 실측).
        """
        if self._is_open(group):
            return True
        try:
            self.page.locator(f'a[role="button"]:has-text("{group}"):visible').first.click(timeout=5000)
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return False
        for _ in range(10):
            time.sleep(0.4)
            if self._is_open(group):
                return True
        return False

    def _items(self, group: str) -> list[str]:
        """해당 드롭다운의 항목 라벨(중복 제거). PC/모바일 2벌이라 중복이 난다."""
        try:
            got = self.page.evaluate(
                r"""(g) => [...document.querySelectorAll(
                        `a[role="option"][data-shp-contents-type="${g}"]`)]
                     .map(a => (a.innerText || '').trim().replace(/\s+/g, ' '))
                     .filter(Boolean)""",
                group,
            )
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return []
        return list(dict.fromkeys(got))

    def _selected(self, group: str) -> bool:
        """선택이 실제로 반영됐는지 확인. 반영 형태가 **두 가지**다(2026-08-15 실측).

        1) 중간 단계 : 항목이 남고 aria-selected="true" 가 된다.
        2) 마지막 단계: 항목이 **통째로 사라지고** '총 금액' 이 나타난다.
           이때 트리거 라벨도 '제품 선택' 으로 되돌아가므로 라벨로는 확인할 수 없다.

        2)번을 몰라서 '선택 실패' 로 오판했다. 항목이 있었는데 사라진 것은
        실패가 아니라 **완료**다. (이 함수는 클릭 직후에만 호출된다)
        """
        try:
            return bool(
                self.page.evaluate(
                    r"""(g) => {
                        const opts = [...document.querySelectorAll(
                            `a[role="option"][data-shp-contents-type="${g}"]`)];
                        if (opts.some(a => a.getAttribute('aria-selected') === 'true')) return true;
                        return opts.length === 0;
                    }""",
                    group,
                )
            )
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return False

    def _pick(self, group: str, label: str) -> str | None:
        """드롭다운에서 항목을 고르고 **반영까지 확인**한다. 실패하면 None."""
        if not self._open_dropdown(group):
            return None
        loc = self.page.locator(f'a[role="option"][data-shp-contents-type="{group}"]:visible')
        try:
            n = loc.count()
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return None
        for i in range(n):
            item = loc.nth(i)
            try:
                txt = re.sub(r"\s+", " ", (item.inner_text() or "").strip())
            except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
                continue
            if label not in txt and txt not in label:
                continue
            try:
                item.click(timeout=5000)
            except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
                return None
            for _ in range(8):
                time.sleep(0.4)
                if self._selected(group):
                    return txt
            return None
        return None

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
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
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
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            return None

    def collect_options(self, prod: CompetitorProduct, *, max_combos: int = 6) -> None:
        """제품 옵션을 하나씩 선택해 총 금액을 읽는다.

        스토어마다 옵션 UI 가 달라 실패할 수 있다. 실패하면 감추지 않고
        스크린샷을 남기고 needs_review 로 표시한다.
        """
        groups = self.option_groups()
        if not groups:
            prod.screenshots.append(self._shot(f"{prod.product_id}_no_options"))
            prod.flag("옵션 드롭다운을 찾지 못함 — 스크린샷 확인 필요")
            return

        primary = groups[0]
        labels = self._items(primary)[:max_combos]
        if not labels:
            prod.screenshots.append(self._shot(f"{prod.product_id}_no_items"))
            prod.flag(f"'{primary}' 항목을 찾지 못함 — 스크린샷 확인 필요")
            return

        for i, lab in enumerate(labels):
            if i:
                # 조합마다 초기 상태에서 시작한다. 선택 해제 UI 는 스토어마다
                # 다르지만 재로딩은 항상 같은 상태를 보장한다(느리지만 확실).
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=45000)
                    self.page.wait_for_timeout(5000)
                except Exception:  # noqa: BLE001 - 재시도 전 상태 초기화 등 보조 동작 — 실패해도 계속 진행(2026-09-28 검토)
                    pass

            combo = OptionCombo(labels=[], extra_won=None)
            picked = self._pick(primary, lab)
            if picked is None:
                combo.labels = [lab]
                combo.needs_review = True
                combo.review_reason = f"'{primary}' 선택 실패"
                combo.screenshot = self._shot_price_area(f"{prod.product_id}_combo{i}")
                prod.options.append(combo)
                continue
            combo.labels.append(picked)
            e = _extra_won_opt(picked)
            if e is not None:
                combo.extra_won = (combo.extra_won or 0) + e

            # 하위 옵션(불빛/색온도 등)을 모두 골라야 총금액이 나타난다.
            # 하위 드롭다운은 **상위를 고른 뒤에야 DOM 에 생성된다**(2026-08-15 실측).
            # 그래서 처음 한 번 열거해 두면 안 되고 매 단계 다시 열거해야 한다.
            # 이 방식이면 3단 이상 옵션도 그대로 처리된다.
            done = {primary}
            for _ in range(self.MAX_OPTION_DEPTH):
                # 하위 드롭다운은 **비동기로 주입**된다. 즉시 열거하면 아직 없어서
                # 옵션이 없는 것으로 오판하고, 추가금이 0 으로 남아 자기검증이
                # '산술 불일치' 를 오탐한다(2026-08-15 실측).
                remaining: list[str] = []
                for _ in range(10):
                    remaining = [g for g in self.option_groups() if g not in done]
                    if remaining:
                        break
                    time.sleep(0.5)
                if not remaining:
                    break
                g = remaining[0]
                sub = self._items(g)
                got = self._pick(g, sub[0]) if sub else None
                if got is None:
                    combo.needs_review = True
                    combo.review_reason = f"'{g}' 선택 실패"
                    break
                combo.labels.append(got)
                e = _extra_won_opt(got)
                if e is not None:
                    combo.extra_won = (combo.extra_won or 0) + e
                done.add(g)

            total = None
            for _ in range(10):
                total = self._read_total()
                if total is not None:
                    break
                time.sleep(0.6)
            if total is None:
                # 폴백: 총금액 문구가 없으면 옵션 행의 금액이라도 읽는다.
                # 단 기본가보다 작으면 배송비 등을 잘못 잡은 것이므로 버린다
                # (실측: 배송비 4,000원을 총액으로 오인한 사례)
                fb = self._read_option_row_price()
                base = prod.base_price.value
                if fb is not None and base is not None and fb < base:
                    fb = None
                total = fb
            combo.total_won = total

            if not combo.needs_review and prod.base_price.value is not None:
                combo.verify(prod.base_price.value)
            combo.screenshot = self._shot_price_area(f"{prod.product_id}_combo{i}")
            prod.options.append(combo)

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
        except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            try:
                self.page.screenshot(path=str(p))
            except Exception:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
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
        except Exception as e:  # noqa: BLE001 - 경쟁사 상품 상세페이지 읽기 전용 파싱(옵션/가격/스크린샷 조사) — 실패는 안전한 기본값(None/빈값/False)으로 폴백, 구매·결제·쓰기 없음(2026-09-28 검토)
            prod.error = f"{type(e).__name__}: {str(e)[:100]}"
            prod.flag("페이지 진입 실패")
            return prod

        prod.screenshots.append(self._shot(f"{prod.product_id}_head"))
        self.read_head(prod)
        self.collect_options(prod, max_combos=max_combos)
        prod.finalize()
        return prod
