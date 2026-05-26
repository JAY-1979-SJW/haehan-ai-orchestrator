import pytest

from scripts.gate import GateBlocked
from scripts.naver_mail import settings_panel as sp


class FakeSettingsActions:
    def __init__(self):
        self.clicked = []

    def evaluate(self, expr):
        if "mailbox_item.support" in expr and "out.push" in expr:
            return [
                {"name": "환경설정", "href": "", "support": True},
                {"name": "로그아웃", "href": "", "support": True},
                {"name": "외부메일 가져오기", "href": "#", "support": True},
                {"name": "메일용량", "href": "", "support": True},
                {"name": "고객센터", "href": "", "support": True},
            ]
        if "label.click()" in expr:
            self.clicked.append(expr)
            return True
        if "save_controls" in expr:
            return {
                "url": "https://mail.naver.com/v2/settings",
                "title": "환경설정 : 네이버 메일",
                "tabs": ["기본 환경", "메일함 관리", "서명/빠른답장", "스팸 설정"],
                "buttons": ["저장", "취소"],
                "inputs_count": 5,
                "checkboxes_count": 2,
                "save_controls": ["저장"],
            }
        return None

    def wait_dom(self, expr, timeout_s=8.0):
        return True


def test_settings_support_menus_are_discovered_separately_from_folders():
    menus = sp.list_settings_menus(FakeSettingsActions())
    by_name = {m.name: m for m in menus}
    assert {"환경설정", "외부메일 가져오기", "메일용량", "고객센터", "로그아웃"} <= set(by_name)
    assert by_name["환경설정"].action == "inspect"
    assert by_name["로그아웃"].blocked is True
    assert by_name["로그아웃"].reason == "session_end_action"


def test_settings_panel_can_be_opened_readonly():
    panel = sp.open_settings_panel(FakeSettingsActions(), "환경설정")
    assert panel.title == "환경설정 : 네이버 메일"
    assert "메일함 관리" in panel.tabs
    assert panel.inputs_count == 5
    assert panel.save_controls == ["저장"]


def test_logout_menu_is_blocked():
    with pytest.raises(ValueError, match="BLOCKED_SETTINGS_MENU"):
        sp.open_settings_panel(FakeSettingsActions(), "로그아웃")


def test_settings_save_requires_approval_gate():
    with pytest.raises(GateBlocked) as exc:
        sp.assert_settings_save_allowed(setting="signature")
    assert exc.value.result.op_name == "naver_mail_settings_save"
