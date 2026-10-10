import pytest

from scripts.common.gate import GateBlocked
from scripts.naver import mail
from scripts.naver import router
from scripts.naver.mail import read_state_guard as rsg


@pytest.mark.parametrize(
    "action",
    ["read", "list", "search", "open_body", "compose", "draft", "reply", "reply_all", "forward"],
)
def test_naver_mail_read_and_write_preparation_allowed(action):
    rsg.assert_action_allowed(action)


@pytest.mark.parametrize(
    ("action", "gate_name"),
    [
        ("send", "naver_mail_send"),
        ("delete", "naver_mail_delete"),
        ("trash", "naver_mail_delete"),
        ("move", "naver_mail_move"),
        ("archive", "naver_mail_move"),
        ("spam", "naver_mail_move"),
    ],
)
def test_naver_mail_send_delete_move_are_approval_gated(action, gate_name):
    with pytest.raises(GateBlocked) as exc:
        rsg.assert_action_allowed(action)
    assert exc.value.result.op_name == gate_name


@pytest.mark.parametrize("sub", ["inbox", "read", "search", "compose", "draft", "", None])
def test_naver_mail_router_allows_read_and_write_preparation(sub):
    router._gate_mail(sub)


@pytest.mark.parametrize(
    ("sub", "gate_name"),
    [
        ("send", "naver_mail_send"),
        ("delete", "naver_mail_delete"),
        ("trash", "naver_mail_delete"),
        ("move", "naver_mail_move"),
        ("archive", "naver_mail_move"),
        ("spam", "naver_mail_move"),
    ],
)
def test_naver_mail_router_gates_send_delete_move(sub, gate_name):
    with pytest.raises(GateBlocked) as exc:
        router._gate_mail(sub)
    assert exc.value.result.op_name == gate_name


def test_naver_mail_send_function_has_internal_gate_before_page_access():
    with pytest.raises(GateBlocked) as exc:
        mail.send_mail(None)
    assert exc.value.result.op_name == "naver_mail_send"
