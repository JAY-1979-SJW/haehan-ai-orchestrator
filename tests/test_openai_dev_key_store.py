"""AGENT_OPENAI_DEV_KEY_STORE_01 — 20+ 테스트."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from local_agent import openai_key_store as ks


# 테스트용 가짜 key — 실 OpenAI key 형태 아님 (의도적 dummy)
DUMMY_KEY = "tkVALID_NOT_A_REAL_OPENAI_KEY_xyz123456789"


# ── 1) 모듈 API 표면 ────────────────────────────────────


def test_module_exports_required_api():
    for sym in ("save_dev_key", "load_dev_key", "delete_dev_key",
                "has_dev_key", "get_key_fingerprint",
                "validate_key_format", "redact_key",
                "describe_backend"):
        assert hasattr(ks, sym), f"missing: {sym}"


def test_service_name_namespaced():
    assert ks.SERVICE_NAME == "haehan-openai-dev"


# ── 2) validate_key_format ─────────────────────────────


def test_validate_empty_rejected():
    ok, code = ks.validate_key_format("")
    assert ok is False and code == "INVALID_FORMAT"


def test_validate_too_short_rejected():
    ok, code = ks.validate_key_format("short")
    assert ok is False


def test_validate_placeholder_rejected():
    for placeholder in ("sk-...", "YOUR_API_KEY", "test", "dummy",
                         "placeholder", "xxxxx"):
        ok, code = ks.validate_key_format(placeholder)
        assert ok is False, f"should reject: {placeholder}"


def test_validate_whitespace_rejected():
    ok, _ = ks.validate_key_format("with space inside long enough")
    assert ok is False


def test_validate_accepts_long_enough_key():
    ok, _ = ks.validate_key_format(DUMMY_KEY)
    assert ok is True


def test_validate_strips_whitespace_before_length_check():
    # surrounding whitespace 만 있으면 stripped 후 비어있으니 reject
    ok, _ = ks.validate_key_format("   ")
    assert ok is False


# ── 3) redact_key / fingerprint ─────────────────────────


def test_redact_key_with_dash_prefix():
    fp = ks.redact_key("sk-abcdEFGH12345678ijklMNOP")
    assert fp == "sk-****MNOP"


def test_redact_key_without_prefix():
    fp = ks.redact_key("abcdefghijklmnopqrstuvWXYZ")
    assert fp.endswith("WXYZ")
    assert "****" in fp


def test_redact_key_short_returns_mask():
    fp = ks.redact_key("abc")
    assert fp == "****"


def test_redact_key_empty():
    assert ks.redact_key("") == ""


def test_redact_does_not_leak_body():
    raw = "sk-veryLongSecretValueWithMid"
    fp = ks.redact_key(raw)
    assert "veryLongSecretValueWith" not in fp


# ── 4) save / load / delete (mock keyring 사용) ────────


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, account, value):
        self.store[(service, account)] = value

    def get_password(self, service, account):
        return self.store.get((service, account))

    def delete_password(self, service, account):
        if (service, account) in self.store:
            del self.store[(service, account)]


@pytest.fixture
def fake_kr(monkeypatch):
    fk = _FakeKeyring()
    monkeypatch.setattr(ks, "_try_keyring", lambda: fk)
    monkeypatch.setattr(ks, "keyring_available", lambda: True)
    return fk


def test_save_returns_fingerprint_only(fake_kr):
    r = ks.save_dev_key(DUMMY_KEY)
    assert r.ok is True
    assert r.backend == "keyring"
    assert r.fingerprint
    # 원문이 fingerprint 에 없어야 함
    assert DUMMY_KEY not in r.fingerprint


def test_save_rejects_placeholder(fake_kr):
    """짧은 placeholder ('test') 는 INVALID_FORMAT (length 우선)."""
    r = ks.save_dev_key("test")
    assert r.ok is False
    assert r.error_code in ("PLACEHOLDER", "INVALID_FORMAT")


def test_save_rejects_short(fake_kr):
    r = ks.save_dev_key("short")
    assert r.ok is False
    assert r.error_code == "INVALID_FORMAT"


def test_load_after_save(fake_kr):
    ks.save_dev_key(DUMMY_KEY)
    loaded = ks.load_dev_key()
    assert loaded == DUMMY_KEY


def test_has_dev_key_true_after_save(fake_kr):
    assert ks.has_dev_key() is False
    ks.save_dev_key(DUMMY_KEY)
    assert ks.has_dev_key() is True


def test_delete_removes_key(fake_kr):
    ks.save_dev_key(DUMMY_KEY)
    assert ks.has_dev_key() is True
    ks.delete_dev_key()
    assert ks.has_dev_key() is False
    assert ks.load_dev_key() is None


def test_get_fingerprint_via_helper(fake_kr):
    assert ks.get_key_fingerprint() == ""
    ks.save_dev_key(DUMMY_KEY)
    fp = ks.get_key_fingerprint()
    assert fp.endswith(DUMMY_KEY[-4:])
    assert DUMMY_KEY not in fp


# ── 5) plaintext fallback 기본 OFF ─────────────────────


def test_save_default_no_plaintext_fallback(monkeypatch):
    """keyring 사용 불가 + fallback opt-out → SAVE 실패 (KEYRING_UNAVAILABLE)."""
    monkeypatch.setattr(ks, "_try_keyring", lambda: None)
    monkeypatch.setattr(ks, "keyring_available", lambda: False)
    r = ks.save_dev_key(DUMMY_KEY)
    assert r.ok is False
    assert r.error_code == "KEYRING_UNAVAILABLE"


def test_save_with_plaintext_fallback_opt_in(monkeypatch, tmp_path):
    """fallback=True 명시 + keyring 불가 → 평문 저장."""
    monkeypatch.setattr(ks, "_try_keyring", lambda: None)
    monkeypatch.setattr(ks, "keyring_available", lambda: False)
    r = ks.save_dev_key(DUMMY_KEY, allow_plaintext_fallback=True,
                         base_dir=tmp_path)
    assert r.ok is True
    assert r.backend == "plaintext"
    # roundtrip
    loaded = ks.load_dev_key(allow_plaintext_fallback=True, base_dir=tmp_path)
    assert loaded == DUMMY_KEY
    # delete
    ks.delete_dev_key(allow_plaintext_fallback=True, base_dir=tmp_path)
    assert ks.has_dev_key(allow_plaintext_fallback=True,
                            base_dir=tmp_path) is False


import inspect


def test_signature_default_fallback_false():
    sig_save = inspect.signature(ks.save_dev_key)
    assert sig_save.parameters["allow_plaintext_fallback"].default is False
    sig_load = inspect.signature(ks.load_dev_key)
    assert sig_load.parameters["allow_plaintext_fallback"].default is False


# ── 6) source 정적 검사 — leak 0 ───────────────────────


def test_module_source_no_raw_key():
    src = Path("local_agent/openai_key_store.py").read_text(encoding="utf-8")
    matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", src)
    real = [m for m in matches if "A-Za-z" not in m]
    assert real == []


def test_module_does_not_log_key_value():
    """logger.X() 호출에 api_key 변수가 인자로 들어가지 않음."""
    src = Path("local_agent/openai_key_store.py").read_text(encoding="utf-8")
    bad = re.findall(
        r"log(?:ger)?\.\w+\([^)]*%[sr][^)]*,\s*api_key\b", src)
    assert bad == []


# ── 7) describe_backend ────────────────────────────────


def test_describe_backend_returns_tuple():
    avail, name = ks.describe_backend()
    assert isinstance(avail, bool)
    assert isinstance(name, str)


# ── 8) audit ────────────────────────────────────────


def test_audit_warn_gui_test_deferred():
    from scripts.ops import audit_openai_dev_key_store as a
    v = a.judge_key_store(gui_connection_test_done=False)
    # [연결 테스트] 활성은 다음 공정 → WARN
    assert v.code in ("PASS_OPENAI_DEV_KEY_STORE",
                       "WARN_GUI_CONNECTION_TEST_DEFERRED")


def test_audit_fail_desktop_ui_touched():
    from scripts.ops import audit_openai_dev_key_store as a
    v = a.judge_key_store(desktop_ui_unchanged=False)
    assert v.code == "FAIL_DESKTOP_UI_TOUCHED"


def test_audit_fail_key_store_missing(monkeypatch, tmp_path):
    from scripts.ops import audit_openai_dev_key_store as a
    monkeypatch.setattr(a, "MODULE_PATH", tmp_path / "missing.py")
    v = a.judge_key_store()
    assert v.code == "FAIL_KEY_STORE_MISSING"


# ── 9) 회귀 가드 ────────────────────────────────────


def test_regression_existing_token_store_intact():
    from local_agent import token_store as ts
    assert hasattr(ts, "save_device_token")
    assert hasattr(ts, "load_device_token")


def test_regression_gui_app_intact():
    from local_agent import gui_app
    assert hasattr(gui_app, "HaehanAgentGuiApp")
    assert hasattr(gui_app, "PAGE_CHAT")


def test_regression_ai_chat_adapter_unchanged():
    from local_agent import ai_chat_adapter as adp
    assert hasattr(adp, "PlaceholderAdapter")
