"""스마트스토어 카테고리 처리 회귀 테스트 (2026-08-15 실측 기반).

이 파일이 지키는 실제 사고들:
  1. 자동완성 1순위가 'LED모듈' — 첫 항목 맹목 클릭 시 엉뚱한 카테고리 선택
  2. `.selectize-dropdown .option` 은 페이지 전역 204개(상단 검색위젯·상품명 자동완성 혼입)
  3. 선택 경로는 `.info-result.text-info` 에 "선택한 카테고리 : <경로>" 로 표시 (라벨 제거 필요)
  4. KC인증 모달이 남아 있으면 이후 클릭이 전부 "intercepts pointer events" 로 실패
  5. Selectize 위젯 options 는 마지막 검색 결과만 보유 → 검색 없이는 대상이 없음
"""

from __future__ import annotations

import inspect

from scripts.naver.smartstore.product import page_selectors as S
from scripts.naver.smartstore.product.general_product import GeneralProductRegister


# ── 셀렉터 계약 ──────────────────────────────────────────────────
def test_category_path_uses_info_result():
    """경로 표시는 info-result 여야 한다. selectize-input .item 은 오탐(15개, '수취인명')."""
    first = S.CATEGORY_PATH_DISPLAY[0]
    assert "info-result" in first, f"1순위가 info-result 가 아님: {first}"
    assert not any(".selectize-input .item" == s for s in S.CATEGORY_PATH_DISPLAY), (
        "selectize-input .item 은 페이지 전역 오탐이라 쓰면 안 된다"
    )


def test_dead_category_selectors_marked_deprecated():
    """사망 확인된 구버전 셀렉터가 1순위로 남아 있으면 안 된다."""
    dead = {".category-path", '[class*="categoryPath"]'}
    assert S.CATEGORY_PATH_DISPLAY[0] not in dead


# ── 신규 메서드 존재 및 계약 ─────────────────────────────────────
def test_widget_fallback_exists():
    """DOM 클릭 실패 시 Selectize 위젯 API 폴백이 있어야 한다."""
    assert hasattr(GeneralProductRegister, "_set_category_via_widget")
    assert hasattr(GeneralProductRegister, "_SELECTIZE_SET_JS")
    js = GeneralProductRegister._SELECTIZE_SET_JS
    assert "input.selectized" in js, "위젯 인스턴스는 input.selectized 에 붙는다"
    assert "setValue" in js


def test_modal_dismisser_exists_and_is_safe():
    """모달 처리기는 있어야 하고, 저장/발행 버튼은 절대 누르면 안 된다."""
    assert hasattr(GeneralProductRegister, "_dismiss_blocking_modals")
    src = inspect.getsource(GeneralProductRegister._dismiss_blocking_modals)
    # docstring 이 아니라 **실제 클릭 셀렉터 라인**만 검사한다.
    # (has-text("닫기") 안에 따옴표가 있어 단순 따옴표 매칭으로는 잘린다)
    selectors = [
        ln.strip().rstrip(",")
        for ln in src.splitlines()
        if ("has-text" in ln or "class*=" in ln) and not ln.strip().startswith("#")
    ]
    joined = " ".join(selectors)
    for forbidden in ("저장하기", "발행", "판매시작"):
        assert forbidden not in joined, f"모달 처리기가 '{forbidden}' 버튼을 클릭 대상으로 둔다 — 위험: {selectors}"
    assert any("닫기" in s or "확인" in s for s in selectors), f"닫기/확인 셀렉터가 없다: {selectors}"


def test_set_category_does_not_blindly_click_first():
    """자동완성 첫 항목 맹목 클릭 금지 — 1순위가 'LED모듈' 인 사례가 실측됨."""
    # 옵션 탐색 로직은 복잡도 분리로 _find_category_option 헬퍼에 있다(결함 #42).
    src = inspect.getsource(GeneralProductRegister.set_category) + inspect.getsource(
        GeneralProductRegister._find_category_option
    )
    assert ".first" not in src.split("자동완성 첫 항목")[0] or "rsplit" in src, "첫 항목을 그대로 쓰는 흔적이 있다"
    # 경로형(>) 필터링과 마지막 노드 일치 검사가 있어야 한다
    assert '">"' in src or "'>'" in src, "경로형(>) 필터링이 없다"
    assert "rsplit" in src, "마지막 노드 일치 검사가 없다"


def test_set_category_verifies_result():
    """선택 후 반드시 실제 값과 대조해야 한다."""
    src = inspect.getsource(GeneralProductRegister.set_category)
    assert "get_selected_category" in src
    assert "category_mismatch" in src


def test_set_category_dismisses_modals():
    """KC인증 모달이 이후 클릭을 막으므로 선택 전후로 정리해야 한다."""
    src = inspect.getsource(GeneralProductRegister.set_category)
    assert src.count("_dismiss_blocking_modals") >= 2, "모달 정리가 선택 전/후 양쪽에 있어야 한다"


# ── 라벨 제거 ────────────────────────────────────────────────────
class _StubPage:
    def __init__(self, text: str):
        self._text = text

    def locator(self, sel):
        return self

    @property
    def first(self):
        return self

    def inner_text(self, timeout=None):
        return self._text


def _reg_with(text: str) -> GeneralProductRegister:
    reg = GeneralProductRegister.__new__(GeneralProductRegister)
    reg.page = _StubPage(text)
    return reg


def test_get_selected_category_strips_label():
    reg = _reg_with("선택한 카테고리 : 가구/인테리어>인테리어소품>조명>인테리어조명")
    assert reg.get_selected_category() == "가구/인테리어>인테리어소품>조명>인테리어조명"


def test_get_selected_category_without_label():
    reg = _reg_with("가구/인테리어>인테리어소품>조명>거실조명")
    assert reg.get_selected_category() == "가구/인테리어>인테리어소품>조명>거실조명"


def test_get_selected_category_empty_on_error():
    class Boom:
        def locator(self, sel):
            raise RuntimeError("no element")

    reg = GeneralProductRegister.__new__(GeneralProductRegister)
    reg.page = Boom()
    assert reg.get_selected_category() == ""
