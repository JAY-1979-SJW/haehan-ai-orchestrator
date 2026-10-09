"""Browser Value Registry Policy 테스트."""

from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_value_registry import (
    VTYPE_SAMPLE_NUMBER,
    VTYPE_SAMPLE_TEXT,
    ValuePolicy,
    clear_all,
    is_forbidden_value,
    list_values,
    register_value,
    resolve_value_for_field,
    validate_raw_input,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


def test_enum_sample_value_register():
    p = ValuePolicy(
        value_key="sample_search_keyword",
        label="검색어 샘플",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="공고",
    )
    res = register_value(p)
    assert res["ok"] is True
    assert "sample_search_keyword" in list_values()


def test_raw_password_blocked():
    p = ValuePolicy(
        value_key="user_password",
        label="비밀번호",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="any",
    )
    res = register_value(p)
    assert res["ok"] is False
    assert res["verdict"] == "VALUE_BLOCKED"


def test_otp_blocked():
    p = ValuePolicy(
        value_key="otp_code",
        label="OTP",
        value_type=VTYPE_SAMPLE_NUMBER,
        sample_safe_value="123456",
    )
    res = register_value(p)
    assert res["ok"] is False


def test_cert_password_blocked():
    p = ValuePolicy(
        value_key="cert_password_x",
        label="인증서 비밀번호",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="x",
    )
    res = register_value(p)
    assert res["ok"] is False


def test_cookie_value_blocked():
    p = ValuePolicy(
        value_key="cookie_jar",
        label="cookie",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="x",
    )
    res = register_value(p)
    assert res["ok"] is False


def test_session_value_blocked():
    p = ValuePolicy(
        value_key="session_id",
        label="session",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="x",
    )
    res = register_value(p)
    assert res["ok"] is False


def test_storage_state_blocked():
    p = ValuePolicy(
        value_key="storage_state_blob",
        label="storage",
        value_type=VTYPE_SAMPLE_TEXT,
        sample_safe_value="x",
    )
    res = register_value(p)
    assert res["ok"] is False


def test_rrn_pattern_in_raw_blocked():
    forbidden, reason = is_forbidden_value("이름 800101-1234567 보낸다", "")
    assert forbidden is True
    assert "주민번호" in reason


def test_account_pattern_blocked():
    forbidden, _reason = is_forbidden_value("계좌 110-456-789012", "")
    assert forbidden is True


def test_resolve_value_for_field_ok():
    register_value(
        ValuePolicy(
            value_key="sample_keyword",
            label="x",
            value_type=VTYPE_SAMPLE_TEXT,
            sample_safe_value="공고",
            allowed_fields=("search_field",),
        )
    )
    res = resolve_value_for_field("sample_keyword", "search_field")
    assert res["ok"] is True
    assert res["sample_safe_value"] == "공고"


def test_resolve_value_for_disallowed_field():
    register_value(
        ValuePolicy(
            value_key="sample_keyword",
            label="x",
            value_type=VTYPE_SAMPLE_TEXT,
            sample_safe_value="공고",
            allowed_fields=("search_field",),
        )
    )
    res = resolve_value_for_field("sample_keyword", "other_field")
    assert res["ok"] is False
    assert res["verdict"] == "FIELD_NOT_ALLOWED"


def test_unknown_value_key():
    res = resolve_value_for_field("nonexistent", "any")
    assert res["ok"] is False


def test_raw_input_not_permitted():
    res = validate_raw_input("hello", "search")
    assert res["ok"] is False
    assert res["verdict"] == "RAW_INPUT_NOT_PERMITTED"


def test_raw_input_with_password_blocked():
    res = validate_raw_input("mypass", "password_field")
    assert res["ok"] is False
    assert res["verdict"] == "RAW_INPUT_BLOCKED"
