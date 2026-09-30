"""네이버 로그인 입력 칸 — 클릭 대기 시간과 입력 분기. 실제 브라우저·자격증명을 쓰지 않는다(가짜 페이지)."""

from __future__ import annotations

import pytest

from scripts.naver import auth as A


class FakeElement:
    def __init__(self, value: str = "", click_error: Exception | None = None):
        self.value = value
        self.click_timeouts: list[int] = []
        self.click_error = click_error

    def wait_for(self, state, timeout):
        return None

    def is_visible(self, timeout=0):
        return True

    def input_value(self, timeout=0):
        return self.value

    def click(self, timeout):
        self.click_timeouts.append(timeout)
        if self.click_error:
            raise self.click_error

    def fill(self, value, timeout=0):
        self.value = value


class FakeKeyboard:
    def __init__(self, element: FakeElement):
        self.element = element

    def press(self, key):
        if key == "Delete":
            self.element.value = ""

    def type(self, ch, delay=0):
        self.element.value += ch


class FakePage:
    def __init__(self, element: FakeElement):
        self.element = element
        self.keyboard = FakeKeyboard(element)

    def locator(self, selector):
        first = self.element

        class _Loc:
            pass

        loc = _Loc()
        loc.first = first
        return loc


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(A.time, "sleep", lambda s: None)


def test_click_timeout_is_generous_enough_for_a_slow_pc():
    """2초는 부하가 있는 PC 에서 아이디/비밀번호 칸 클릭이 번갈아 시간 초과됐다(2026-09-30)."""
    assert A._INPUT_CLICK_TIMEOUT_MS >= 5000


def test_empty_field_is_typed_with_the_generous_timeout():
    el = FakeElement("")
    result = A._safe_human_input(FakePage(el), "#id", "skyjwsin", "ID", delay_ms=0)
    assert result["ok"] and result["action"] == "empty" and el.value == "skyjwsin"
    assert el.click_timeouts == [A._INPUT_CLICK_TIMEOUT_MS]


def test_prefilled_other_value_is_cleared_and_replaced():
    """브라우저 자동 채우기로 다른 값이 들어 있으면 지우고 다시 입력한다(다른 계정 값이 그대로 제출되면 안 됨)."""
    el = FakeElement("otherAcct1")
    result = A._safe_human_input(FakePage(el), "#id", "skyjwsin", "ID", delay_ms=0)
    assert result["ok"] and result["action"] == "replaced" and el.value == "skyjwsin"
    assert el.click_timeouts == [A._INPUT_CLICK_TIMEOUT_MS] * 2


def test_same_value_is_skipped_without_clicking():
    el = FakeElement("skyjwsin")
    result = A._safe_human_input(FakePage(el), "#id", "skyjwsin", "ID", delay_ms=0)
    assert result["ok"] and result["action"] == "skip" and el.click_timeouts == []


def test_click_failure_is_a_failed_result_not_an_exception():
    el = FakeElement("", click_error=RuntimeError("Timeout 8000ms exceeded"))
    result = A._safe_human_input(FakePage(el), "#id", "skyjwsin", "ID", delay_ms=0)
    assert result["ok"] is False and result["action"] == "error"


def test_redaction_helper_hides_raw_values():
    redacted = A._redact_input_result({"ok": True, "before": "otherAcct1", "after": "skyjwsin"})
    assert redacted["before"] == "[REDACTED]" and redacted["after"] == "[REDACTED]"
    assert redacted["before_len"] == 10 and "skyjwsin" not in str(redacted)
