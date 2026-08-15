"""옵션 조합(조합형) — 입력행 구성 → 적용 → ag-Grid 편집.

2026-08-15 실측으로 확정한 사실:

  1. 옵션명 개수는 <select> 가 아니라 selectized **input** 이다.
     맞음 : [ng-model="vm.choiceOptionNameCount"]   (태그 무관 속성 셀렉터)
     틀림 : select[ng-model="vm.choiceOptionNameCount"]

  2. '옵션목록으로 적용' 은 <button> 이 아니라 <a class="btn btn-primary"> 다.

  3. 적용 결과는 <table>/<tr> 이 아니라 **ag-Grid** 로 렌더링된다.
     행 확인은 .ag-cell[col-id="..."] 로 한다. tr 을 세면 0 이 나와
     '생성 실패' 로 오판한다(실제로 그렇게 오판했다).
     컬럼: optionName1 / optionName2 / price / stockQuantity / status / usable

  4. ag-Grid 셀에는 input 이 상주하지 않는다. **더블클릭**으로 편집 모드에
     들어가야 input 이 생긴다.

  5. 클릭이 안 되면 셀렉터보다 **모달**을 먼저 의심한다.
     쌓인 경고 모달이 화면을 덮고 있으면 정상 셀렉터도 전부 타임아웃난다.
"""

from __future__ import annotations

from typing import Any

from scripts.naver.smartstore.product.modal_guard import dismiss_blocking_modals

OPTION_USE_ON = 'input[ng-model="vm.isChoiceType"][value="true"]'
OPTION_TYPE_COMBINATION = 'input[ng-model="vm.choiceType"][value="COMBINATION"]'
OPTION_NAME_COUNT = '[ng-model="vm.choiceOptionNameCount"]'  # select 아님 — input
OPTION_GROUP_NAME = 'input[ng-model="choiceOptionInput.groupName"]'
OPTION_VALUE_NAME = 'input[ng-model="choiceOptionInput.name"]'

COL_NAME1 = "optionName1"
COL_NAME2 = "optionName2"
COL_PRICE = "price"
COL_STOCK = "stockQuantity"
COL_STATUS = "status"

_SET_COUNT_JS = r"""
(n) => {
  const el = document.querySelector('[ng-model="vm.choiceOptionNameCount"]');
  if (!el) return {ok: false, error: 'count_element_missing'};
  const s = el.selectize;
  if (!s) return {ok: false, error: 'selectize_missing'};
  s.addItem(String(n));
  try {
    if (window.angular) {
      const sc = window.angular.element(el).scope();
      if (sc) sc.$applyAsync();
    }
  } catch (e) {}
  return {ok: true, items: s.items};
}
"""

_APPLY_JS = r"""
() => {
  const a = [...document.querySelectorAll('a')]
      .find(e => /옵션목록으로 적용/.test(e.innerText || ''));
  if (!a) return false;
  a.click();          // Playwright 클릭은 actionability 로 거부되는 경우가 있다
  return true;
}
"""

_READ_GRID_JS = r"""
() => {
  const col = c => [...document.querySelectorAll(`.ag-cell[col-id="${c}"]`)]
      .map(e => (e.innerText || '').trim());
  return {
    name1: col('optionName1'),
    name2: col('optionName2'),
    price: col('price'),
    stock: col('stockQuantity'),
    status: col('status'),
  };
}
"""


def _num(s: str) -> str:
    return (s or "").replace(",", "").strip()


class OptionGrid:
    """조합형 옵션 생성 및 옵션가·재고 설정."""

    def __init__(self, page: Any):
        self.page = page

    # ── 읽기 ────────────────────────────────────────────────────
    def read_rows(self) -> list[dict]:
        """생성된 조합을 행 단위로. ag-Grid 라 tr 이 아니라 ag-cell 을 본다."""
        try:
            g = self.page.evaluate(_READ_GRID_JS)
        except Exception:
            return []
        n = len(g.get("name1") or [])
        rows = []
        for i in range(n):
            rows.append(
                {
                    "name1": g["name1"][i],
                    "name2": g["name2"][i] if i < len(g["name2"]) else "",
                    "price": _num(g["price"][i]) if i < len(g["price"]) else "",
                    "stock": _num(g["stock"][i]) if i < len(g["stock"]) else "",
                    "status": g["status"][i] if i < len(g["status"]) else "",
                }
            )
        return rows

    # ── 구성 ────────────────────────────────────────────────────
    def set_option_names(self, pairs: list[tuple[str, list[str]]]) -> dict:
        """옵션명/값 입력. pairs = [('길이', ['600mm', ...]), ('색상', [...])]"""
        if not pairs:
            return {"ok": False, "error": "no_pairs"}

        r = self.page.evaluate(_SET_COUNT_JS, len(pairs))
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        self.page.wait_for_timeout(1500)

        gi = self.page.locator(OPTION_GROUP_NAME)
        vi = self.page.locator(OPTION_VALUE_NAME)
        if gi.count() < len(pairs):
            return {"ok": False, "error": f"rows_{gi.count()}_expected_{len(pairs)}"}

        for i, (gname, values) in enumerate(pairs):
            try:
                gi.nth(i).fill(gname)
                self.page.wait_for_timeout(250)
                vi.nth(i).fill(",".join(values))
                self.page.wait_for_timeout(400)
            except Exception as e:
                return {"ok": False, "error": f"fill_row{i}_{type(e).__name__}"}

        # 넣었다고 믿지 않고 되읽는다
        got_g = [gi.nth(i).input_value() for i in range(len(pairs))]
        got_v = [vi.nth(i).input_value() for i in range(len(pairs))]
        for i, (gname, values) in enumerate(pairs):
            if got_g[i] != gname or got_v[i] != ",".join(values):
                return {"ok": False, "error": f"mismatch_row{i}", "actual": (got_g[i], got_v[i])}
        return {"ok": True, "groups": got_g, "values": got_v}

    def apply(self, *, expected_rows: int | None = None) -> dict:
        """'옵션목록으로 적용'. 누르기 전에 화면을 덮은 모달부터 치운다."""
        notices = dismiss_blocking_modals(self.page)
        try:
            clicked = self.page.evaluate(_APPLY_JS)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}", "notices": notices}
        if not clicked:
            return {"ok": False, "error": "apply_button_missing", "notices": notices}
        self.page.wait_for_timeout(2500)
        notices += dismiss_blocking_modals(self.page)

        rows = self.read_rows()
        if expected_rows is not None and len(rows) != expected_rows:
            return {
                "ok": False,
                "error": f"rows_{len(rows)}_expected_{expected_rows}",
                "notices": notices,
            }
        return {"ok": True, "rows": len(rows), "notices": notices}

    # ── 셀 편집 ─────────────────────────────────────────────────
    def _edit_cell(self, col: str, idx: int, value: str) -> bool:
        """ag-Grid 는 더블클릭해야 편집용 input 이 생성된다."""
        cell = self.page.locator(f'.ag-cell[col-id="{col}"]').nth(idx)
        try:
            cell.dblclick(timeout=4000)
            self.page.wait_for_timeout(300)
            inp = cell.locator("input")
            if inp.count() == 0:
                inp = self.page.locator(".ag-cell-edit-input, .ag-input-field-input").first
            inp.fill(value, timeout=3000)
            self.page.wait_for_timeout(200)
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(400)
            return True
        except Exception:
            return False

    def set_prices_and_stock(
        self,
        price_by_name1: dict[str, int],
        stock: int,
    ) -> dict:
        """1단 옵션값별 옵션가와 공통 재고를 넣고 **행마다 되읽어 확인**한다."""
        rows = self.read_rows()
        if not rows:
            return {"ok": False, "error": "no_rows"}

        unknown = sorted({r["name1"] for r in rows} - set(price_by_name1))
        if unknown:
            return {"ok": False, "error": "unmapped_option_values", "values": unknown}

        for i, r in enumerate(rows):
            self._edit_cell(COL_PRICE, i, str(price_by_name1[r["name1"]]))
            self._edit_cell(COL_STOCK, i, str(stock))
            dismiss_blocking_modals(self.page)

        after = self.read_rows()
        bad = []
        for r in after:
            want_p = str(price_by_name1.get(r["name1"]))
            if r["price"] != want_p or r["stock"] != str(stock):
                bad.append({"row": f"{r['name1']}/{r['name2']}", "price": r["price"], "stock": r["stock"]})
        return {"ok": not bad, "rows": len(after), "mismatched": bad, "detail": after}
