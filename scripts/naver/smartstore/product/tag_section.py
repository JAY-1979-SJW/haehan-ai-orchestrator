"""검색태그(직접입력) 섹션 — 실측으로 확정한 경로만 사용한다.

2026-08-15 에 다섯 번 헛짚고 얻은 사실들:

  1. 셀렉터
     맞음  : select[config="::vm.config.directInputSelectizeConfig"]
     틀림  : input[ng-model="vm.searchKeyword"]  ← 브랜드/제조사 자동완성이다(maxItems=1)

  2. 전제조건
     '검색설정' 섹션이 접혀 있으면 DOM 에 아예 없다.
     그리고 체크박스 vm.viewData.isDirectInput 을 켜야 위젯이 생성된다(ng-if).

  3. 항목 확정
     Enter 로는 확정되지 않는다. 드롭다운의 '직접입력: XXX'(.create) 를 눌러야 한다.
     settings.create 가 단순 플래그가 아니라 **검증 함수**이기 때문이다:
         create: e => byteLen(e) > MAX ? alert(...) : $apply(() => push({text:e}))
     그래서 addItem()/createItem() 은 아무 일도 하지 않는다.

  4. 뭉침
     확정 후 입력창이 비워지지 않아 다음 글자가 이어붙는다.
     '라인조명'+'간접조명' -> '라인조명간접조명'.
     예전 '매입라인조명라인등' 사고와 같은 원인. 매번 setTextboxValue('') 가 필요하다.

  5. 결과 확인 위치
     .choice-tag .choice-label strong  ("# 라인조명")
     .selectize-input .item 이 아니다. 여기를 잘못 봐서 성공을 실패로 판정했다.

  6. 거부 규칙
     카테고리명·브랜드명·판매처명과 같은 태그는 거부된다.
     (실측: 카테고리가 '인테리어조명' 일 때 같은 이름 태그가 거부됨)
     한 태그당 한글 10자 / 30바이트 이하.
"""

from __future__ import annotations

from typing import Any

from scripts.naver.smartstore.product.modal_guard import dismiss_blocking_modals

MAX_TAG_BYTES = 30  # 한글 10자
MAX_TAGS = 10

DIRECT_INPUT_CHECKBOX = 'input[ng-model="vm.viewData.isDirectInput"]'
TAG_CONFIG = "::vm.config.directInputSelectizeConfig"

_READ_JS = r"""
() => [...document.querySelectorAll('.choice-tag .choice-label strong')]
        .map(e => (e.innerText || '').replace(/^#\s*/, '').trim())
        .filter(Boolean)
"""

_WIDGET_IDX_JS = r"""
(config) => {
  const sels = [...document.querySelectorAll('select[ncp-selectize], select[selectize]')];
  return sels.findIndex(s => (s.getAttribute('config') || '') === config);
}
"""

_CLEAR_ALL_JS = r"""
() => {
  const btns = [...document.querySelectorAll('.choice-tag .choice-label a[ng-click*="deleteTag"]')];
  btns.forEach(b => { try { b.click(); } catch (e) {} });
  return btns.length;
}
"""

# 입력창을 비우고 -> 값을 넣고 -> .create 를 눌러 확정한다.
# 화면에 보이는 '직접입력: XXX' 텍스트가 넣으려는 값과 다르면 입력창이 오염된 것이므로
# 클릭하지 않고 실패로 돌려준다(뭉친 태그가 등록되는 것을 막는다).
_ADD_ONE_JS = r"""
(payload) => {
  const {idx, text} = payload;
  const sels = [...document.querySelectorAll('select[ncp-selectize], select[selectize]')];
  const el = sels[idx];
  const s = el && el.selectize;
  const ctrl = el ? el.parentElement.querySelector('.selectize-control') : null;
  if (!s || !ctrl) return {ok: false, error: 'widget_missing'};

  s.focus();
  s.setTextboxValue('');
  s.setTextboxValue(text);
  s.refreshOptions(true);
  try { s.open(); } catch (e) {}

  const cre = ctrl.querySelector('.selectize-dropdown-content .create');
  if (!cre) return {ok: false, error: 'create_option_missing'};
  const shown = (cre.innerText || '').replace(/^직접입력:\s*/, '').trim();
  if (shown !== text) return {ok: false, error: 'textbox_dirty', shown};

  try { cre.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); } catch (e) {}
  cre.click();
  try { s.setTextboxValue(''); s.close(); } catch (e) {}
  return {ok: true};
}
"""


def tag_byte_len(tag: str) -> int:
    return len((tag or "").encode("utf-8"))


def validate_tags(
    tags: list[str],
    *,
    category: str | None = None,
    brand: str | None = None,
    store: str | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """등록 가능한 태그와 거부 사유를 나눈다(브라우저 없이 판정).

    네이버가 거부할 것을 미리 걸러야 경고 모달이 쌓이지 않는다.
    모달이 쌓이면 이후 모든 클릭이 막힌다(실측).
    """
    forbidden = {(x or "").strip() for x in (category, brand, store) if x}
    ok: list[str] = []
    rejected: list[tuple[str, str]] = []
    seen: set[str] = set()

    for raw in tags:
        t = (raw or "").strip()
        if not t:
            continue
        if t in seen:
            rejected.append((t, "중복"))
            continue
        if t in forbidden:
            rejected.append((t, "카테고리/브랜드/판매처명과 동일 — 네이버가 거부함"))
            continue
        if tag_byte_len(t) > MAX_TAG_BYTES:
            rejected.append((t, f"{tag_byte_len(t)}바이트 — 한글 10자(30바이트) 초과"))
            continue
        if len(ok) >= MAX_TAGS:
            rejected.append((t, f"최대 {MAX_TAGS}개 초과"))
            continue
        seen.add(t)
        ok.append(t)
    return ok, rejected


class TagSection:
    """검색태그 직접입력. 넣을 때마다 개수를 확인하고, 실패를 감추지 않는다."""

    def __init__(self, page: Any):
        self.page = page

    # ── 상태 ────────────────────────────────────────────────────
    def read_tags(self) -> list[str]:
        try:
            return list(self.page.evaluate(_READ_JS) or [])
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
            return []

    def _widget_index(self) -> int:
        try:
            return int(self.page.evaluate(_WIDGET_IDX_JS, TAG_CONFIG))
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
            return -1

    def is_available(self) -> bool:
        return self._widget_index() >= 0

    # ── 준비 ────────────────────────────────────────────────────
    def ensure_direct_input(self) -> bool:
        """'태그 직접 입력' 체크박스를 켠다. 위젯은 이게 켜져야 생성된다(ng-if)."""
        cb = self.page.locator(DIRECT_INPUT_CHECKBOX).first
        try:
            if cb.count() == 0:
                return False
            if not cb.is_checked():
                try:
                    cb.click(timeout=3000)
                except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
                    # 숨겨진 체크박스라 Playwright 클릭이 거부될 수 있다
                    self.page.evaluate(f"() => document.querySelector('{DIRECT_INPUT_CHECKBOX}').click()")
                self.page.wait_for_timeout(1200)
            return bool(cb.is_checked())
        except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
            return False

    def clear_all(self, *, max_rounds: int = 5) -> int:
        before = len(self.read_tags())
        for _ in range(max_rounds):
            if not self.read_tags():
                break
            try:
                self.page.evaluate(_CLEAR_ALL_JS)
                self.page.wait_for_timeout(700)
            except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
                break
        return before - len(self.read_tags())

    # ── 입력 ────────────────────────────────────────────────────
    def add(self, tag: str) -> dict:
        idx = self._widget_index()
        if idx < 0:
            return {"ok": False, "error": "widget_missing"}
        before = len(self.read_tags())
        try:
            r = self.page.evaluate(_ADD_ONE_JS, {"idx": idx, "text": tag})
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 태그 위젯 UI 조작 - 실패 시 빈 목록/False/에러dict 반환
            return {"ok": False, "error": f"{type(e).__name__}"}
        if not r.get("ok"):
            return r
        self.page.wait_for_timeout(700)
        after = len(self.read_tags())
        if after <= before:
            # 네이버가 거부하면 모달로 사유를 알려준다 — 버리지 않고 돌려준다
            notes = dismiss_blocking_modals(self.page)
            return {"ok": False, "error": "not_registered", "notices": notes}
        return {"ok": True, "count": after}

    def set_tags(
        self,
        tags: list[str],
        *,
        category: str | None = None,
        brand: str | None = None,
        store: str | None = None,
        replace: bool = True,
    ) -> dict:
        """태그 일괄 설정. 사전 검증 → (선택) 기존 삭제 → 하나씩 확정."""
        accepted, rejected = validate_tags(tags, category=category, brand=brand, store=store)

        if not self.ensure_direct_input():
            return {"ok": False, "error": "direct_input_unavailable", "rejected": rejected}
        if not self.is_available():
            return {"ok": False, "error": "widget_missing", "rejected": rejected}

        if replace:
            self.clear_all()

        added: list[str] = []
        failed: list[dict] = []
        for t in accepted:
            r = self.add(t)
            if r.get("ok"):
                added.append(t)
            else:
                failed.append({"tag": t, **r})

        final = self.read_tags()
        return {
            "ok": len(added) == len(accepted) and not failed,
            "added": added,
            "failed": failed,
            "rejected": rejected,
            "final": final,
        }
