"""저장 직전 전수 점검(postflight) 테스트 — 브라우저 불필요.

이 파일이 지키는 실제 사고 (2026-08-15). 하루에 같은 오판을 네 번 했다:
  · 검색태그 / 옵션 / 배송비 — 접혀 있어서 '미설정' 으로 오판 (실제로는 설정돼 있었음)
  · 예약구매 — 켜져 있는 줄 모르고 저장할 뻔함 (예약구매 상품이 될 뻔했다)
"""

from __future__ import annotations

from scripts.naver.smartstore.product.postflight import (
    MissingField,
    PostflightReport,
    expand_all_sections,
    postflight,
    read_missing,
    read_risky_settings,
    read_sections,
)


class _StubPage:
    """evaluate 를 스크립트 내용으로 분기하는 최소 스텁."""

    def __init__(self, *, sections=None, missing=None, preorder_on=False, toggles=0):
        self._sections = sections or []
        self._missing = missing or []
        self._preorder_on = preorder_on
        self._remaining = toggles
        self.expand_calls = 0

    def evaluate(self, script, arg=None):
        if "메뉴" in script:
            self.expand_calls += 1
            n = self._remaining
            self._remaining = 0
            return {"clicked": n, "total": 22}
        if "form-section" in script and "invalid_required" in script:
            return self._sections
        if "ng-invalid-required" in script:
            return self._missing
        if "isPreOrderOn" in script:
            return {
                "preOrder": [
                    {"value": "true", "checked": self._preorder_on},
                    {"value": "false", "checked": not self._preorder_on},
                ]
            }
        return None

    def wait_for_timeout(self, ms):
        return None


# ── 펼치기 ──────────────────────────────────────────────────────
def test_expand_handles_anchor_and_button_with_space():
    """<a>'메뉴토글' 만 보면 배송 섹션을 못 펼친다 — <button>'메뉴 토글' 도 있다."""
    # 주의: `from ... product import postflight` 는 __init__ 이 재수출한 **함수**를
    # 가져온다(모듈과 이름이 같아 가려진다). 모듈 내부 상수는 직접 임포트해야 한다.
    from scripts.naver.smartstore.product.postflight import _EXPAND_JS

    assert "querySelectorAll('a,button')" in _EXPAND_JS
    assert "메뉴\\s*토글" in _EXPAND_JS, "공백 유무를 모두 허용해야 한다"


def test_expand_stops_when_nothing_left():
    page = _StubPage(toggles=3)
    assert expand_all_sections(page) == 3
    assert page.expand_calls == 2  # 3개 클릭 후 0 을 받고 종료


def test_postflight_expands_before_reading():
    """접힌 섹션의 입력요소는 DOM 에 없다 — 펼치기 전에 읽으면 전부 '없음' 이다."""
    page = _StubPage(toggles=2)
    rep = postflight(page)
    assert rep.expanded == 2


def test_postflight_can_skip_expanding():
    page = _StubPage(toggles=2)
    assert postflight(page, expand=False).expanded == 0


# ── 섹션 읽기 ────────────────────────────────────────────────────
def test_section_titles_come_from_title_line_not_h3():
    """제목이 h3 가 아니라 .title-line 안의 label 이다. h3 로 찾으면 19개 중 2개만 잡힌다."""
    from scripts.naver.smartstore.product.postflight import _SECTIONS_JS

    assert ".title-line" in _SECTIONS_JS


def test_read_sections_maps_fields():
    page = _StubPage(
        sections=[
            {
                "title": "배송",
                "fields": 12,
                "filled": 5,
                "invalid_required": 0,
                "summary": "일반배송 / 택배 / 유료(3,000원",
                "visible": True,
            },
        ]
    )
    s = read_sections(page)[0]
    assert s.title == "배송"
    assert s.filled == 5
    assert "3,000원" in s.summary, "접힌 섹션 요약을 잃으면 설정 여부를 오판한다"


# ── 필수 미입력 ──────────────────────────────────────────────────
def test_missing_separates_actionable_from_hidden():
    """숨김/비활성 항목까지 똑같이 보여주면 목록이 신뢰를 잃는다."""
    page = _StubPage(
        missing=[
            {
                "ng": "vm.content.certificateDetails",
                "label": "법에 의한 인증",
                "section": "상품정보제공고시",
                "visible": True,
                "disabled": False,
            },
            {
                "ng": "vm.checkValueForValidate.supplement",
                "label": "선택형",
                "section": "",
                "visible": False,
                "disabled": False,
            },
            {
                "ng": "vm.product.customerBenefit.reviewPointPolicy.textReviewPoint",
                "label": "",
                "section": "구매/리뷰 혜택",
                "visible": False,
                "disabled": True,
            },
        ]
    )
    rep = postflight(page)
    assert len(rep.missing) == 3
    assert len(rep.actionable_missing) == 1
    assert rep.actionable_missing[0].ng.endswith("certificateDetails")


def test_missing_field_actionable_rule():
    assert MissingField("a", "", "", visible=True, disabled=False).actionable is True
    assert MissingField("a", "", "", visible=False, disabled=False).actionable is False
    assert MissingField("a", "", "", visible=True, disabled=True).actionable is False


def test_read_missing_survives_page_error():
    class Boom:
        def evaluate(self, *a, **k):
            raise RuntimeError("nope")

        def wait_for_timeout(self, ms):
            pass

    assert read_missing(Boom()) == []


# ── 위험 설정 ────────────────────────────────────────────────────
def test_preorder_on_is_warned():
    """예약구매가 켜진 채 저장하면 일반 판매가 아니라 예약구매 상품이 된다."""
    page = _StubPage(preorder_on=True)
    warns = read_risky_settings(page)
    assert warns and "예약구매" in warns[0]


def test_preorder_off_is_silent():
    assert read_risky_settings(_StubPage(preorder_on=False)) == []


def test_report_not_ready_when_preorder_on():
    """조치 가능한 미입력이 없어도 위험 설정이 있으면 준비 완료가 아니다."""
    rep = postflight(_StubPage(preorder_on=True))
    assert rep.missing == []
    assert rep.ready is False


# ── 리포트 ───────────────────────────────────────────────────────
def test_ready_when_clean():
    assert postflight(_StubPage()).ready is True


def test_summary_mentions_counts():
    rep = PostflightReport(
        sections=[],
        missing=[MissingField("x", "", "", visible=True, disabled=False)],
        warnings=["예약구매 켜짐"],
    )
    s = rep.summary()
    assert "필수미입력 1건" in s
    assert "경고 1건" in s


def test_to_dict_is_serializable_for_agents():
    import json

    rep = postflight(
        _StubPage(
            missing=[{"ng": "a", "label": "L", "section": "S", "visible": True, "disabled": False}],
            preorder_on=True,
        )
    )
    d = rep.to_dict()
    assert json.dumps(d, ensure_ascii=False)
    assert d["ready"] is False
    assert d["missing"][0]["actionable"] is True
