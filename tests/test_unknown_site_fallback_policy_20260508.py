"""tests/test_unknown_site_fallback_policy_20260508.py"""

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from core.agent_runtime.runtime.universal.unknown_site_fallback_policy import (
    evaluate_unknown_site,
    get_action_grade_for_unknown_site,
    is_blocked_on_unknown_site,
)


def test_readonly_auto_allowed():
    assert get_action_grade_for_unknown_site("read_page") == GRADE_AUTO_ALLOWED
    assert get_action_grade_for_unknown_site("readonly_explore") == GRADE_AUTO_ALLOWED
    assert get_action_grade_for_unknown_site("extract_text") == GRADE_AUTO_ALLOWED


def test_download_auto_allowed():
    assert get_action_grade_for_unknown_site("download_document") == GRADE_AUTO_ALLOWED


def test_form_fill_auto_allowed():
    assert get_action_grade_for_unknown_site("fill_non_sensitive_form") == GRADE_AUTO_ALLOWED


def test_write_post_delegated():
    assert get_action_grade_for_unknown_site("write_post") == GRADE_USER_DELEGATED


def test_publish_delegated():
    assert get_action_grade_for_unknown_site("publish_post") == GRADE_USER_DELEGATED


def test_comment_delegated():
    assert get_action_grade_for_unknown_site("write_comment") == GRADE_USER_DELEGATED


def test_delete_delegated():
    assert get_action_grade_for_unknown_site("delete_post") == GRADE_USER_DELEGATED


def test_send_message_delegated():
    assert get_action_grade_for_unknown_site("send_message") == GRADE_USER_DELEGATED


def test_submit_non_legal_delegated():
    assert get_action_grade_for_unknown_site("submit_non_legal_form") == GRADE_USER_DELEGATED


def test_payment_user_direct():
    assert get_action_grade_for_unknown_site("payment") == GRADE_USER_DIRECT


def test_esign_user_direct():
    assert get_action_grade_for_unknown_site("e_sign") == GRADE_USER_DIRECT


def test_bid_user_direct():
    assert get_action_grade_for_unknown_site("bid_final_submit") == GRADE_USER_DIRECT


def test_captcha_bypass_blocked():
    assert get_action_grade_for_unknown_site("captcha_bypass") == GRADE_BLOCKED
    assert is_blocked_on_unknown_site("captcha_bypass") is True


def test_password_save_blocked():
    assert get_action_grade_for_unknown_site("password_save") == GRADE_BLOCKED


def test_cookie_export_blocked():
    assert get_action_grade_for_unknown_site("cookie_export") == GRADE_BLOCKED


def test_npki_access_blocked():
    assert get_action_grade_for_unknown_site("npki_access") == GRADE_BLOCKED


def test_auto_payment_blocked():
    assert get_action_grade_for_unknown_site("auto_payment") == GRADE_BLOCKED


def test_risk_signal_escalates_delegated_to_direct():
    grade = get_action_grade_for_unknown_site("submit_non_legal_form", risk_signals=["payment"])
    assert grade == GRADE_USER_DIRECT


def test_evaluate_auto_allowed():
    result = evaluate_unknown_site("read_page")
    assert result["executable"] is True
    assert result["grade"] == GRADE_AUTO_ALLOWED


def test_evaluate_blocked():
    result = evaluate_unknown_site("captcha_bypass")
    assert result["executable"] is False
    assert result["grade"] == GRADE_BLOCKED


def test_evaluate_delegated_without_permission():
    result = evaluate_unknown_site("write_post", has_permission=False)
    assert result["executable"] is False
    assert result["grade"] == GRADE_USER_DELEGATED


def test_evaluate_delegated_with_permission():
    result = evaluate_unknown_site("write_post", has_permission=True)
    assert result["executable"] is True


def test_evaluate_user_direct():
    result = evaluate_unknown_site("payment")
    assert result["executable"] is False
    assert result["grade"] == GRADE_USER_DIRECT
