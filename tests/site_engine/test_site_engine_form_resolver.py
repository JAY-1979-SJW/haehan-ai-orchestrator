"""Unit tests for scripts.site_engine.form_resolver."""

from scripts.site_engine.form_resolver import (
    FormFieldKind,
    FormFieldSensitivity,
    FormResolutionInput,
    classify_field_sensitivity,
    mask_field_value,
    resolve_form_fields,
)

_MASK = "***REDACTED***"


def _raw(selector="#f", name="", id_="", type_="text", placeholder="", label=""):
    return {"selector": selector, "name": name, "id": id_, "type": type_, "placeholder": placeholder, "label": label}


# ── sensitivity classification ───────────────────────────────────────


def test_password_kind_is_forbidden():
    assert classify_field_sensitivity(FormFieldKind.PASSWORD) == FormFieldSensitivity.FORBIDDEN


def test_otp_kind_is_forbidden():
    assert classify_field_sensitivity(FormFieldKind.OTP) == FormFieldSensitivity.FORBIDDEN


def test_email_kind_is_safe():
    assert classify_field_sensitivity(FormFieldKind.EMAIL) == FormFieldSensitivity.SAFE


def test_name_kind_is_safe():
    assert classify_field_sensitivity(FormFieldKind.NAME) == FormFieldSensitivity.SAFE


# ── mask_field_value ─────────────────────────────────────────────────


def test_mask_password_value():
    assert mask_field_value("hunter2", FormFieldKind.PASSWORD) == _MASK


def test_mask_otp_value():
    assert mask_field_value("123456", FormFieldKind.OTP) == _MASK


def test_no_mask_safe_value():
    assert mask_field_value("alice@example.com", FormFieldKind.EMAIL) == "alice@example.com"


# ── resolve_form_fields ──────────────────────────────────────────────


def test_resolve_detects_password_by_type():
    inp = FormResolutionInput(
        page_url="https://example.com/login",
        fields_raw=[_raw(name="pw", type_="password")],
    )
    result = resolve_form_fields(inp)
    assert result.candidates[0].kind == FormFieldKind.PASSWORD
    assert result.has_sensitive_fields


def test_resolve_detects_email_by_name():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[_raw(name="email")],
    )
    result = resolve_form_fields(inp)
    assert result.candidates[0].kind == FormFieldKind.EMAIL
    assert not result.has_sensitive_fields


def test_resolve_detects_otp_by_placeholder():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[_raw(placeholder="인증번호 입력")],
    )
    result = resolve_form_fields(inp)
    assert result.candidates[0].kind == FormFieldKind.OTP


def test_resolve_detects_file_by_type():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[_raw(type_="file")],
    )
    result = resolve_form_fields(inp)
    assert result.candidates[0].kind == FormFieldKind.FILE


def test_resolve_sensitive_count():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[
            _raw(name="email"),
            _raw(name="pw", type_="password"),
            _raw(name="pw2", type_="password", id_="password_confirm"),
        ],
    )
    result = resolve_form_fields(inp)
    assert result.sensitive_field_count == 2


def test_resolve_candidates_have_no_value_field():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[_raw(name="pw", type_="password")],
    )
    result = resolve_form_fields(inp)
    assert not hasattr(result.candidates[0], "value")


def test_resolve_password_confirm_by_id():
    inp = FormResolutionInput(
        page_url="https://example.com",
        fields_raw=[_raw(type_="password", id_="password_confirm")],
    )
    result = resolve_form_fields(inp)
    assert result.candidates[0].kind == FormFieldKind.PASSWORD_CONFIRM
