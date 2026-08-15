"""검색태그 / 옵션 그리드 / 모달 가드 테스트 (브라우저 불필요).

이 파일이 지키는 실제 사고 (2026-08-15) — 전부 실측으로 확인된 것:
  1. 태그 확정 실패로 '라인조명간접조명' 처럼 뭉침 (예전 '매입라인조명라인등' 과 동일)
  2. 카테고리명과 같은 태그를 넣어 경고 모달이 10개 쌓였고,
     그 모달이 화면을 덮어 이후 모든 클릭이 TimeoutError 가 됨
  3. 결과 확인 위치를 잘못 봐서(.selectize-input .item, <tr>) 성공을 실패로 판정
"""

from __future__ import annotations

from scripts.naver.smartstore.product.modal_guard import (
    dismiss_blocking_modals,
    peek_modal,
)
from scripts.naver.smartstore.product.option_grid import OptionGrid
from scripts.naver.smartstore.product.tag_section import (
    MAX_TAG_BYTES,
    MAX_TAGS,
    TagSection,
    tag_byte_len,
    validate_tags,
)


# ── 태그 사전 검증 ───────────────────────────────────────────────
def test_byte_len_counts_utf8():
    assert tag_byte_len("라인조명") == 12
    assert tag_byte_len("LED") == 3


def test_category_name_tag_is_rejected():
    """실측: 카테고리가 '인테리어조명' 일 때 같은 이름 태그가 네이버에서 거부됐다.

    미리 거르지 않으면 경고 모달이 쌓이고, 그 모달이 이후 클릭을 전부 막는다.
    """
    ok, rejected = validate_tags(["라인조명", "인테리어조명"], category="인테리어조명")
    assert ok == ["라인조명"]
    assert rejected[0][0] == "인테리어조명"
    assert "카테고리" in rejected[0][1]


def test_brand_and_store_names_rejected():
    ok, rej = validate_tags(["반딧불", "라인조명"], brand="반딧불")
    assert ok == ["라인조명"]
    assert rej[0][0] == "반딧불"


def test_too_long_tag_rejected():
    long_tag = "가" * 11  # 33바이트
    assert tag_byte_len(long_tag) > MAX_TAG_BYTES
    ok, rej = validate_tags([long_tag])
    assert ok == []
    assert "초과" in rej[0][1]


def test_ten_byte_boundary_accepted():
    ten = "가" * 10  # 정확히 30바이트
    assert tag_byte_len(ten) == MAX_TAG_BYTES
    ok, _ = validate_tags([ten])
    assert ok == [ten]


def test_duplicates_rejected():
    ok, rej = validate_tags(["라인조명", "라인조명"])
    assert ok == ["라인조명"]
    assert rej[0][1] == "중복"


def test_max_ten_tags():
    tags = [f"태그{i}" for i in range(15)]
    ok, rej = validate_tags(tags)
    assert len(ok) == MAX_TAGS
    assert all("초과" in r[1] for r in rej)


def test_blank_tags_ignored():
    ok, _ = validate_tags(["", "  ", "라인조명"])
    assert ok == ["라인조명"]


# ── 뭉침 방지 배선 ───────────────────────────────────────────────
def test_add_clears_textbox_before_typing():
    """확정 후 입력창을 비우지 않으면 다음 태그가 이어붙는다."""
    import inspect

    from scripts.naver.smartstore.product import tag_section

    js = tag_section._ADD_ONE_JS
    assert "setTextboxValue('')" in js, "입력창 초기화가 없다 — 태그가 뭉친다"
    # 오염 감지: 화면에 뜬 '직접입력: XXX' 가 넣으려는 값과 다르면 클릭하지 않는다
    assert "textbox_dirty" in js
    assert "shown !== text" in js
    inspect.getsource(TagSection.add)  # 존재 확인


def test_reads_tags_from_choice_label_not_selectize_item():
    """결과 확인 위치 회귀 방지 — 여기를 잘못 봐서 다섯 번 헛짚었다."""
    from scripts.naver.smartstore.product import tag_section

    assert ".choice-tag .choice-label" in tag_section._READ_JS
    assert ".selectize-input .item" not in tag_section._READ_JS


def test_tag_widget_selector_is_config_based():
    """vm.searchKeyword 는 브랜드/제조사 자동완성이다 — 태그가 아니다."""
    from scripts.naver.smartstore.product import tag_section

    assert tag_section.TAG_CONFIG == "::vm.config.directInputSelectizeConfig"
    assert "vm.searchKeyword" not in tag_section._WIDGET_IDX_JS


# ── 옵션 그리드 ──────────────────────────────────────────────────
def test_option_grid_reads_ag_cells_not_table_rows():
    """적용 결과는 <tr> 이 아니라 ag-Grid 다. tr 을 세면 0 이 나와 오판한다."""
    from scripts.naver.smartstore.product import option_grid

    assert ".ag-cell[col-id=" in option_grid._READ_GRID_JS
    assert "querySelectorAll('tr')" not in option_grid._READ_GRID_JS


def test_option_name_count_selector_is_not_select_tag():
    """selectized input 이다. select[...] 로 찾으면 없다고 나온다(실측)."""
    from scripts.naver.smartstore.product import option_grid

    assert option_grid.OPTION_NAME_COUNT == '[ng-model="vm.choiceOptionNameCount"]'
    assert not option_grid.OPTION_NAME_COUNT.startswith("select")


def test_apply_button_is_anchor_not_button():
    from scripts.naver.smartstore.product import option_grid

    assert "querySelectorAll('a')" in option_grid._APPLY_JS


def test_edit_cell_uses_double_click():
    """ag-Grid 셀에는 input 이 상주하지 않는다."""
    import inspect

    assert "dblclick" in inspect.getsource(OptionGrid._edit_cell)


def test_apply_dismisses_modals_first():
    """클릭 실패의 진짜 원인은 셀렉터가 아니라 화면을 덮은 모달이었다."""
    import inspect

    src = inspect.getsource(OptionGrid.apply)
    assert "dismiss_blocking_modals" in src
    assert src.index("dismiss_blocking_modals") < src.index("_APPLY_JS")


# ── 스텁 페이지로 동작 검증 ──────────────────────────────────────
class _StubPage:
    """evaluate 를 스크립트 내용으로 분기하는 최소 스텁."""

    def __init__(self, rows=None, modals=None):
        self.rows = rows or {}
        self.modals = list(modals or [])
        self.dismissed = []

    def evaluate(self, script, arg=None):
        if 'role="dialog"' in script and "btn.click()" in script:
            if not self.modals:
                return False
            self.dismissed.append(self.modals.pop(0))
            return True
        if 'role="dialog"' in script:
            return {"text": self.modals[0], "buttons": ["확인"]} if self.modals else None
        if "col-id=" in script:
            return self.rows
        return None

    def wait_for_timeout(self, ms):
        return None


def test_dismiss_returns_modal_texts():
    """모달 문구를 버리면 실패 사유를 잃는다 — 반드시 돌려줘야 한다."""
    page = _StubPage(modals=["태그 불가 단어: 인테리어조명", "동일한 태그가 있습니다."])
    got = dismiss_blocking_modals(page)
    assert got == ["태그 불가 단어: 인테리어조명", "동일한 태그가 있습니다."]
    assert peek_modal(page) is None


def test_dismiss_handles_no_modal():
    assert dismiss_blocking_modals(_StubPage()) == []


def test_read_rows_maps_columns():
    page = _StubPage(
        rows={
            "name1": ["600mm", "1200mm"],
            "name2": ["주광색", "전구색"],
            "price": ["0", "15,000"],
            "stock": ["100", "100"],
            "status": ["판매중", "판매중"],
        }
    )
    rows = OptionGrid(page).read_rows()
    assert len(rows) == 2
    assert rows[1]["price"] == "15000", "콤마를 벗겨야 비교가 된다"
    assert rows[0]["name1"] == "600mm"


def test_set_prices_rejects_unmapped_values():
    """매핑에 없는 옵션값이 있으면 임의로 0 을 넣지 않고 실패로 알린다."""
    page = _StubPage(
        rows={
            "name1": ["600mm", "1500mm"],
            "name2": ["주광색", "주광색"],
            "price": ["0", "0"],
            "stock": ["0", "0"],
            "status": ["품절", "품절"],
        }
    )
    r = OptionGrid(page).set_prices_and_stock({"600mm": 0}, 100)
    assert r["ok"] is False
    assert r["error"] == "unmapped_option_values"
    assert r["values"] == ["1500mm"]
