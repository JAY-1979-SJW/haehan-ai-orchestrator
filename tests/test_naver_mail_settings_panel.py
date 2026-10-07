import pytest

from scripts.common.gate import GateBlocked
from scripts.naver.mail import settings_panel as sp


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
        if "text_sample" in expr:
            return {
                "url": "https://mail.naver.com/v2/settings",
                "title": "환경설정 : 네이버 메일",
                "text_sample": "기본 환경 메일함 관리 서명/빠른답장 스팸 설정",
                "fields": [
                    {
                        "label": "서명 이름",
                        "kind": "input:text",
                        "name": "signatureName",
                        "value_present": True,
                        "required": True,
                    }
                ],
                "links": ["저장", "취소", "추가"],
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


def test_settings_detail_inventory_reads_controls_without_saving():
    detail = sp.inspect_settings_detail(FakeSettingsActions(), "환경설정")
    assert detail["menu_name"] == "환경설정"
    assert detail["fields"][0]["name"] == "signatureName"
    assert "저장" in detail["links"]


def test_external_mail_import_prepare_plan_blocks_final_submit():
    plan = sp.prepare_external_mail_import(
        provider="example",
        email_address="user@example.com",
        server_type="imap",
        server_host="imap.example.com",
        port=993,
    )

    assert plan.menu_name == "외부메일 가져오기"
    assert plan.action == "external_mail_add"
    assert plan.fields["server_type"] == "imap"
    assert plan.approval_required is True
    assert plan.final_submit_blocked is True
    assert any("credentials" in warning for warning in plan.warnings)


def test_settings_prepare_plans_cover_major_detail_features():
    plans = [
        sp.prepare_external_mail_update(account_hint="u***@example.com", server_host="imap.example.com"),
        sp.prepare_external_mail_delete(account_hint="u***@example.com"),
        sp.prepare_signature_update(signature_name="work", body_preview="Regards"),
        sp.prepare_quick_reply_update(template_name="default", body_preview="확인했습니다."),
        sp.prepare_auto_classification_rule(
            rule_name="vendor",
            sender_contains="@vendor.example",
            target_folder="거래처",
        ),
        sp.prepare_forwarding_rule(forwarding_address="ops@example.com"),
        sp.prepare_vacation_reply(enabled=True, subject="부재중", body_preview="확인 후 회신하겠습니다."),
        sp.prepare_spam_policy_update(blocked_domain="spam.example"),
        sp.prepare_mailbox_management(folder_name="거래처", operation="rename", new_name="업무"),
        sp.prepare_capacity_cleanup(target="trash", delete_scope="review_only"),
    ]

    assert [p.action for p in plans] == [
        "external_mail_update",
        "external_mail_delete",
        "signature_update",
        "quick_reply_update",
        "auto_classification_rule",
        "forwarding_rule",
        "vacation_reply",
        "spam_policy_update",
        "mailbox_management",
        "mailbox_cleanup",
    ]
    assert all(p.safe_to_prepare for p in plans)
    assert all(p.approval_gate == "naver_mail_settings_save" for p in plans)
    assert all(p.final_submit_blocked for p in plans)


def test_settings_action_execution_requires_approval_by_default():
    plan = sp.prepare_signature_update(signature_name="work", body_preview="Regards")

    with pytest.raises(GateBlocked) as exc:
        sp.execute_settings_action_plan(plan)

    assert exc.value.result.op_name == "naver_mail_settings_save"
