"""F-4C — local_agent.trusted_secrets 단위 테스트.

검증:
  A) is_valid_secret_id 형식 검증
  B) validate_secret_ref — 정상/누락/충돌/raw 비밀 거절
  C) reject_raw_secret_params — password / cookie / session / storage 차단
  D) redact_for_log — raw 값 마스킹 + secret_id prefix 마스킹
  E) resolve_secret 은 NotImplementedError
  F) raw 비밀값이 결과/마스킹 출력에 노출되지 않음
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import trusted_secrets as ts  # noqa: E402


# ─── A) is_valid_secret_id ───────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "hometax_user_id",
    "hometax-cert-password",
    "abc.def_123",
    "a-b",
    "AAAA",
])
def test_is_valid_secret_id_accepts_clean_slug(value):
    assert ts.is_valid_secret_id(value) is True


@pytest.mark.parametrize("value", [
    "",
    "ab",                     # too short
    "x" * 200,                # too long
    " hometax_user_id",       # leading space
    "hometax_user_id ",       # trailing space
    "hometax user id",        # inner space
    "hometax/user",           # slash
    "hometax:user",           # colon
    "홈택스아이디",            # non-ASCII
    None,
    123,
    object(),
])
def test_is_valid_secret_id_rejects_bad(value):
    assert ts.is_valid_secret_id(value) is False


# ─── B) validate_secret_ref ──────────────────────────────────────────────

def _good_ref() -> dict:
    return {
        "site_key": "hometax",
        "login_method": "certificate",
        "user_id_secret_id": "hometax_user_id",
        "password_secret_id": "hometax_cert_password",
    }


def test_validate_secret_ref_accepts_good():
    out = ts.validate_secret_ref(_good_ref())
    assert out["ok"] is True
    assert out["error_code"] == ""


def test_validate_secret_ref_rejects_non_mapping():
    out = ts.validate_secret_ref("not-a-dict")
    assert out["ok"] is False
    assert out["error_code"] == "REF_NOT_MAPPING"


def test_validate_secret_ref_rejects_raw_password_in_ref():
    bad = _good_ref()
    bad["password"] = "actual-secret-value"
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"
    # value 가 결과에 노출되지 않아야 한다.
    serialized = repr(out)
    assert "actual-secret-value" not in serialized


def test_validate_secret_ref_rejects_raw_cert_password():
    bad = _good_ref()
    bad["cert_password"] = "p@ssw0rd"
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"
    assert "p@ssw0rd" not in repr(out)


def test_validate_secret_ref_rejects_missing_site_key():
    bad = _good_ref()
    del bad["site_key"]
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "MISSING_SITE_KEY"


def test_validate_secret_ref_rejects_uppercase_site_key():
    bad = _good_ref()
    bad["site_key"] = "Hometax"
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "SITE_KEY_NOT_LOWERCASE"


def test_validate_secret_ref_rejects_invalid_user_id_secret_id():
    bad = _good_ref()
    bad["user_id_secret_id"] = "bad id"
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_USER_ID_SECRET_ID"


def test_validate_secret_ref_rejects_password_id_collision():
    bad = _good_ref()
    bad["password_secret_id"] = bad["user_id_secret_id"]
    out = ts.validate_secret_ref(bad)
    assert out["ok"] is False
    assert out["error_code"] == "USER_AND_PASSWORD_SECRET_ID_COLLIDE"


# ─── C) reject_raw_secret_params ─────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "password", "passwd", "cert_password", "certificate_password",
    "otp", "token", "access_token", "refresh_token",
    "cookie", "session", "storage_state",
    "localStorage", "sessionStorage",
])
def test_reject_raw_secret_params_blocks_raw_keys(key):
    out = ts.reject_raw_secret_params({key: "secret-value-do-not-leak"})
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"
    assert "secret-value-do-not-leak" not in repr(out)


def test_reject_raw_secret_params_allows_secret_id_only_dict():
    out = ts.reject_raw_secret_params({
        "site_key": "hometax",
        "password_secret_id": "hometax_cert_password",
    })
    assert out["ok"] is True


def test_reject_raw_secret_params_passes_through_non_mapping():
    assert ts.reject_raw_secret_params("not a dict")["ok"] is True
    assert ts.reject_raw_secret_params(None)["ok"] is True


def test_reject_raw_secret_params_allows_empty_password_field():
    # 빈 문자열은 무해 — 외부 입력 폼 default 등.
    out = ts.reject_raw_secret_params({"password": ""})
    assert out["ok"] is True


def test_reject_raw_secret_params_warning_lists_keys_lowercase():
    out = ts.reject_raw_secret_params({
        "Cookie": "abc",
        "STORAGE_STATE": "{}",
    })
    assert out["ok"] is False
    warns = set(out["warnings"])
    assert "raw_secret_param:cookie" in warns
    assert "raw_secret_param:storage_state" in warns


# ─── D) redact_for_log ───────────────────────────────────────────────────

def test_redact_for_log_masks_raw_password():
    payload = {
        "site_key": "hometax",
        "password": "do-not-leak-1234",
        "cert_password": "do-not-leak-cert",
    }
    out = ts.redact_for_log(payload)
    assert out["password"] == "***"
    assert out["cert_password"] == "***"
    assert out["site_key"] == "hometax"
    assert "do-not-leak-1234" not in repr(out)
    assert "do-not-leak-cert" not in repr(out)


def test_redact_for_log_masks_secret_id_prefix_only():
    payload = {
        "user_id_secret_id": "hometax_user_id",
        "password_secret_id": "hometax_cert_password",
    }
    out = ts.redact_for_log(payload)
    # prefix 4글자만 남고 나머지는 *** 로 가려진다.
    assert out["user_id_secret_id"].endswith("***")
    assert out["user_id_secret_id"].startswith("home")
    assert "user_id" not in out["user_id_secret_id"]
    assert out["password_secret_id"].endswith("***")
    assert out["password_secret_id"].startswith("home")


def test_redact_for_log_recurses_into_lists_and_nested_dicts():
    payload = {
        "items": [
            {"password": "leak-A", "label": "row-1"},
            {"cookie": "leak-B"},
        ],
        "outer": {"inner": {"session": "leak-C"}},
    }
    out = ts.redact_for_log(payload)
    flat = repr(out)
    assert "leak-A" not in flat
    assert "leak-B" not in flat
    assert "leak-C" not in flat
    assert out["items"][0]["label"] == "row-1"


# ─── E) resolve_secret ───────────────────────────────────────────────────

def test_resolve_secret_is_not_implemented():
    with pytest.raises(NotImplementedError):
        ts.resolve_secret("hometax_cert_password")


def test_resolve_secret_rejects_invalid_id_with_value_error():
    with pytest.raises(ValueError):
        ts.resolve_secret("bad id with space")


# ─── F) raw 비밀값 누출 회귀 테스트 ──────────────────────────────────────

def test_raw_secret_param_keys_lists_documented_keywords():
    keys = set(ts.raw_secret_param_keys())
    expected = {
        "password", "passwd", "cert_password", "certificate_password",
        "otp", "token", "access_token", "refresh_token",
        "cookie", "session", "storage_state",
        "localstorage", "sessionstorage",
    }
    assert expected.issubset(keys)
