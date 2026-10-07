"""공용 사람처럼 입력(scripts/browser/page/human_input.py) — 클릭 대기 옵션, force 클릭 폴백, 보이는지 재확인. 가짜 페이지만 쓴다."""

from __future__ import annotations

import pytest

from scripts.browser.page import human_input as H


class FakeElement:
    def __init__(
        self,
        value="",
        *,
        fail_normal_click=False,
        fail_all_clicks=False,
        wait_error=None,
        visible=True,
        drop_chars=False,
    ):
        self.value = value
        self.click_calls: list[tuple[int, bool]] = []
        self.fail_normal_click, self.fail_all_clicks = fail_normal_click, fail_all_clicks
        self.wait_error, self.visible, self.drop_chars = wait_error, visible, drop_chars

    def wait_for(self, state, timeout):
        if self.wait_error:
            raise self.wait_error

    def is_visible(self):
        return self.visible

    def input_value(self, timeout=0):
        return self.value

    def click(self, timeout, force=False):
        self.click_calls.append((timeout, force))
        if self.fail_all_clicks or (self.fail_normal_click and not force):
            raise RuntimeError("click timeout")

    def fill(self, value, timeout=0):
        self.value = value


class FakeKeyboard:
    def __init__(self, element):
        self.element = element

    def press(self, key):
        if key == "Delete":
            self.element.value = ""

    def type(self, ch, delay=0):
        if not self.element.drop_chars:
            self.element.value += ch


class FakePage:
    def __init__(self, element):
        self.element = element
        self.keyboard = FakeKeyboard(element)

    def locator(self, selector):
        first = self.element

        class Loc:
            pass

        loc = Loc()
        loc.first = first
        return loc


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(H.time, "sleep", lambda s: None)


def run(element, **kwargs):
    return H.safe_human_input(FakePage(element), "#f", "value1", label="F", delay_ms=0, **kwargs)


def test_default_click_timeout_is_unchanged_for_other_sites():
    el = FakeElement()
    assert run(el)["ok"] and el.click_calls == [(3000, False)]


def test_custom_click_timeout_reaches_every_click():
    el = FakeElement("other")
    assert run(el, click_timeout_ms=8000)["action"] == "replaced"
    assert el.click_calls == [(8000, False), (8000, False)]


def test_same_value_is_skipped_without_clicking():
    el = FakeElement("value1")
    assert run(el)["action"] == "skip" and el.click_calls == []


def test_prefilled_other_value_is_cleared_then_typed():
    """브라우저 자동 채우기 값(다른 계정)이 그대로 제출되면 안 된다."""
    el = FakeElement("bigsun2024")
    result = run(el)
    assert result["ok"] and result["action"] == "replaced" and el.value == "value1"


def test_force_click_fallback_when_normal_click_times_out():
    el = FakeElement(fail_normal_click=True)
    assert run(el, click_timeout_ms=5000)["ok"]
    assert el.click_calls == [(5000, False), (5000, True)]


def test_click_failure_everywhere_is_an_error_result_not_an_exception():
    result = run(FakeElement(fail_all_clicks=True))
    assert result["ok"] is False and result["action"] == "error"


def test_wait_timeout_but_actually_visible_still_proceeds():
    """네이버 로그인 폼은 보안 스크립트가 붙는 동안 wait_for 가 시간 초과되지만 실제로는 보인다."""
    el = FakeElement(wait_error=RuntimeError("wait_for timeout"), visible=True)
    result = run(el)
    assert result["ok"] and el.value == "value1"


def test_wait_timeout_and_not_visible_fails():
    result = run(FakeElement(wait_error=RuntimeError("wait_for timeout"), visible=False))
    assert result["ok"] is False and result["action"] == "error"


def test_value_mismatch_after_typing_is_reported():
    result = run(FakeElement(drop_chars=True))
    assert result["ok"] is False and result["reason"] == "value_mismatch"


def test_find_selector_returns_first_visible():
    class Page:
        def query_selector(self, sel):
            class El:
                def __init__(self, vis):
                    self.vis = vis

                def is_visible(self):
                    return self.vis

            return {"#a": None, "#b": El(False), "#c": El(True)}.get(sel)

    assert H.find_selector(Page(), ["#a", "#b", "#c"]) == "#c"
    assert H.find_selector(Page(), ["#a", "#b"]) is None
