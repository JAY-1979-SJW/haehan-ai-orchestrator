"""네이버 로그인 폼 입력 — 8초 클릭 대기, 자동 채우기 값 교체, 실패 시 비밀번호 미접촉. 실제 브라우저·자격증명은 쓰지 않는다."""

from __future__ import annotations

import pytest

from scripts.browser.page import human_input as H
from scripts.naver.common import auth as A


class FakeElement:
    def __init__(self, value=""):
        self.value = value
        self.click_timeouts: list[int] = []
        self.fail_clicks = False

    def wait_for(self, state, timeout):
        return None

    def is_visible(self):
        return True

    def input_value(self, timeout=0):
        return self.value

    def click(self, timeout, force=False):
        self.click_timeouts.append(timeout)
        if self.fail_clicks:
            raise RuntimeError("Timeout exceeded")

    def fill(self, value, timeout=0):
        self.value = value


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        if key == "Delete":
            self.page.focused_value("")

    def type(self, ch, delay=0):
        self.page.focused_value(self.page.focused.value + ch)


class FakePage:
    """#id, #pw 두 칸. 마지막으로 클릭한 칸에 키 입력이 들어간다."""

    def __init__(self, id_value="", pw_value=""):
        self.elements = {"#id": FakeElement(id_value), "#pw": FakeElement(pw_value)}
        self.focused = self.elements["#id"]
        self.keyboard = FakeKeyboard(self)

    def focused_value(self, value):
        self.focused.value = value

    def locator(self, selector):
        page, el = self, self.elements[selector]
        original_click = el.click

        def click(timeout, force=False):
            page.focused = el
            return original_click(timeout, force)

        el.click = click

        class Loc:
            pass

        loc = Loc()
        loc.first = el
        return loc


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(A.time, "sleep", lambda s: None)


def test_click_timeout_is_generous_enough_for_a_slow_pc():
    """2초는 부하가 있는 PC 에서 아이디/비밀번호 칸 클릭이 번갈아 시간 초과됐다(2026-09-30)."""
    assert A._INPUT_CLICK_TIMEOUT_MS >= 5000


def test_login_form_types_both_fields_with_the_generous_timeout():
    page = FakePage()
    assert A._fill_login_form(page, "skyjwsin", "secret-pw") is None
    assert page.elements["#id"].value == "skyjwsin" and page.elements["#pw"].value == "secret-pw"
    for element in page.elements.values():
        assert element.click_timeouts == [A._INPUT_CLICK_TIMEOUT_MS]


def test_autofilled_other_account_is_replaced_in_both_fields():
    """2026-09-30 실측: 아이디 칸에 기본 저장 계정(bigsun2024)이 미리 채워져 있었다. 제출 전에 지우고 대상 계정으로 다시 입력해야 한다."""
    page = FakePage(id_value="bigsun2024", pw_value="other-account-pw")
    assert A._fill_login_form(page, "skyjwsin", "secret-pw") is None
    assert page.elements["#id"].value == "skyjwsin" and page.elements["#pw"].value == "secret-pw"


def test_id_failure_stops_before_touching_the_password_field():
    page = FakePage()
    page.elements["#id"].fail_clicks = True
    result = A._fill_login_form(page, "skyjwsin", "secret-pw")
    assert result["ok"] is False and result["reason"].startswith("id_input_failed")
    assert page.elements["#pw"].click_timeouts == [] and page.elements["#pw"].value == ""


def test_password_failure_result_never_contains_the_raw_password():
    page = FakePage()
    page.elements["#pw"].fail_clicks = True
    result = A._fill_login_form(page, "skyjwsin", "secret-pw")
    assert result["ok"] is False and result["reason"].startswith("pw_input_failed")
    assert "secret-pw" not in str(result)


def test_naver_no_longer_keeps_its_own_copy_of_the_input_helper():
    """공용 scripts/browser/page/human_input.py 로 통합했다 — 자체 사본이 다시 생기면 안 된다."""
    assert not hasattr(A, "_safe_human_input")
    assert A.safe_human_input is H.safe_human_input


def test_redaction_helper_hides_raw_values():
    redacted = A._redact_input_result({"ok": True, "before": "otherAcct1", "after": "skyjwsin"})
    assert redacted["before"] == "[REDACTED]" and redacted["after"] == "[REDACTED]"
    assert redacted["before_len"] == 10 and "skyjwsin" not in str(redacted)
