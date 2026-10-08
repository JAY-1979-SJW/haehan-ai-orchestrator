import pytest

from scripts.site_engine import site_session_safety as safety


def test_different_user_is_common_session_integrity_failure():
    result = safety.build_session_integrity_result(
        {"ok": False, "reason": "different_user_logged_in"},
        site="naver",
        workflow="content_explore",
    )

    assert result["ok"] is False
    assert result["blocked"] is True


def test_expected_actual_user_mismatch_blocks_any_site():
    result = safety.build_session_integrity_result(
        {"ok": True, "user": "user-b"},
        site="hiworks",
        workflow="dashboard",
        expected_user="user-a",
    )

    assert result["blocked"] is True
    assert result["reason"] == "session_user_mismatch"


def test_assert_session_integrity_raises_on_failure():
    with pytest.raises(safety.SessionIntegrityBlocked):
        safety.assert_session_integrity(
            {"ok": False, "reason": "expired_session"},
            site="smartstore",
            workflow="product_list",
        )


def test_assert_session_integrity_allows_normal_result():
    result = safety.assert_session_integrity(
        {"ok": True, "user": "user-a"},
        site="eum",
        workflow="device_inventory",
        expected_user="user-a",
    )

    assert result["ok"] is True
    assert result["blocked"] is False
