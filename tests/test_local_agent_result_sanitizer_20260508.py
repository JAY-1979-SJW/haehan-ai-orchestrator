"""결과 sanitizer 테스트"""

from __future__ import annotations

from core.agent_runtime.runtime.result_sanitizer import (
    sanitize_result,
    validate_sanitized_result,
)


def _raw(**kw):
    base = {
        "task_id": "t1",
        "ok": True,
        "status": "COMPLETED",
        "title_hint": "공고 목록",
        "current_url_host": "www.g2b.go.kr",
        "extracted_data": {},
        "message_ko": "완료",
    }
    base.update(kw)
    return base


# ── sanitize_result ────────────────────────────────────────────────────────────


def test_sanitize_removes_cookie():
    r = sanitize_result(_raw(cookie="sess=abc"))
    assert "cookie" not in r or r.get("cookie") in (None, False, "", [], {})


def test_sanitize_removes_session():
    r = sanitize_result(_raw(session="s=xyz"))
    assert "session" not in r or r.get("session") in (None, False, "", [], {})


def test_sanitize_removes_password():
    r = sanitize_result(_raw(password="secret"))
    assert "password" not in r or r.get("password") in (None, False, "", [], {})


def test_sanitize_removes_otp():
    r = sanitize_result(_raw(otp="123456"))
    assert "otp" not in r or r.get("otp") in (None, False, "", [], {})


def test_sanitize_removes_token():
    r = sanitize_result(_raw(token="abc123"))
    assert "token" not in r or r.get("token") in (None, False, "", [], {})


def test_sanitize_removes_cert_password():
    r = sanitize_result(_raw(certificate_password="pw"))
    assert "certificate_password" not in r or r.get("certificate_password") in (None, False, "", [], {})


def test_sanitize_removes_npki():
    r = sanitize_result(_raw(npki_data="binary"))
    assert "npki_data" not in r or r.get("npki_data") in (None, False, "", [], {})


def test_sanitize_keeps_safe_fields():
    r = sanitize_result(_raw(title_hint="공고 목록", current_url_host="www.g2b.go.kr"))
    assert r["title_hint"] == "공고 목록"
    assert r["current_url_host"] == "www.g2b.go.kr"


def test_sanitize_fixed_fields_always_false():
    r = sanitize_result(_raw(cookie="sess=abc"))
    assert r["cookie_exported"] is False
    assert r["session_exported"] is False
    assert r["password_collected"] is False
    assert r["otp_collected"] is False
    assert r["certificate_password_collected"] is False
    assert r["sensitive_data_collected"] is False


def test_sanitize_extracted_data_sensitive_key_removed():
    r = sanitize_result(_raw(extracted_data={"cookie": "abc", "text": "공고"}))
    extracted = r.get("extracted_data", {})
    assert "cookie" not in extracted
    assert extracted.get("text") == "공고"


def test_sanitize_removed_fields_tracked():
    r = sanitize_result(_raw(cookie="abc", session="xyz"))
    assert "_sanitized_fields" in r
    assert "cookie" in r["_sanitized_fields"] or "session" in r["_sanitized_fields"]


# ── validate_sanitized_result ──────────────────────────────────────────────────


def test_validate_clean_result_ok():
    r = sanitize_result(_raw())
    violations = validate_sanitized_result(r)
    assert violations == []


def test_validate_detects_leftover_cookie():
    r = sanitize_result(_raw())
    r["cookie"] = "sess=abc"
    violations = validate_sanitized_result(r)
    assert any("cookie" in v for v in violations)


def test_validate_detects_fixed_field_tampered():
    r = sanitize_result(_raw())
    r["password_collected"] = True
    violations = validate_sanitized_result(r)
    assert any("password_collected" in v for v in violations)
