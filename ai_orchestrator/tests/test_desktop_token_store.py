"""Desktop agent token_store / desktop_config / redaction 단위 테스트.

검증 항목:
  - keyring 사용 가능 시 device_token이 OS credential store에 저장되고
    config.json에는 저장되지 않는다.
  - keyring 사용 불가능하고 fallback 비활성이면 fail-closed.
  - 평문 fallback은 명시적 옵트인일 때만 동작한다.
  - desktop_config은 비밀 키를 저장하지 않는다 (방어선).
  - redaction.redact()는 sensitive 키를 마스킹한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

from core.agent_runtime.common import desktop_config as _cfg
from core.agent_runtime.common import redaction as _red
from core.agent_runtime.connection import token_store as _ts

# ─── Fake keyring backend ────────────────────────────────────────────────


class _FakeKeyring:
    def __init__(self, *, usable: bool = True):
        self._store: dict[tuple[str, str], str] = {}
        self._usable = usable

    def get_keyring(self):
        class _BE:
            pass

        be = _BE()
        be.__class__.__name__ = "FakeBackend" if self._usable else "FailKeyring"
        return be

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str):
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


@pytest.fixture
def fake_keyring(monkeypatch):
    fk = _FakeKeyring(usable=True)
    monkeypatch.setattr(_ts, "_try_import_keyring", lambda: fk)
    return fk


@pytest.fixture
def no_keyring(monkeypatch):
    monkeypatch.setattr(_ts, "_try_import_keyring", lambda: None)


# ─── token_store ─────────────────────────────────────────────────────────


def test_save_and_load_via_keyring(fake_keyring):
    backend = _ts.save_device_token("https://srv.example", "la-abc", "tok-xyz")
    assert backend == "FakeBackend"
    assert _ts.has_device_token("https://srv.example", "la-abc") is True
    assert _ts.load_device_token("https://srv.example", "la-abc") == "tok-xyz"


def test_save_fail_closed_without_keyring(no_keyring):
    with pytest.raises(_ts.TokenStoreError):
        _ts.save_device_token("https://srv.example", "la-abc", "tok-xyz")


def test_plaintext_fallback_only_when_optin(no_keyring, tmp_path):
    backend = _ts.save_device_token(
        "https://srv.example",
        "la-abc",
        "tok-xyz",
        allow_plaintext_fallback=True,
        plaintext_base_dir=tmp_path,
    )
    assert backend == "plaintext-fallback"
    # load with same opt-in works
    got = _ts.load_device_token(
        "https://srv.example",
        "la-abc",
        allow_plaintext_fallback=True,
        plaintext_base_dir=tmp_path,
    )
    assert got == "tok-xyz"
    # without opt-in, must NOT find the plaintext token (default fail-closed)
    assert _ts.load_device_token("https://srv.example", "la-abc") is None


def test_delete_device_token(fake_keyring):
    _ts.save_device_token("https://srv", "la-1", "tok-1")
    assert _ts.delete_device_token("https://srv", "la-1") is True
    assert _ts.load_device_token("https://srv", "la-1") is None


def test_describe_backend_does_not_return_token(fake_keyring):
    _ts.save_device_token("https://srv", "la-1", "secret-token-value")
    usable, name = _ts.describe_backend()
    assert usable is True
    assert "secret-token-value" not in name


# ─── desktop_config ──────────────────────────────────────────────────────


def test_config_save_load_no_secret(tmp_path):
    p = tmp_path / "config.json"
    cfg = _cfg.DesktopConfig(
        server_url="https://srv",
        agent_id="la-1",
        label="jay-laptop",
        created_at="2026-04-30T12:00:00",
        version="0.1.0",
    )
    saved = _cfg.save_config(cfg, path=p)
    raw = json.loads(saved.read_text(encoding="utf-8"))
    assert raw["agent_id"] == "la-1"
    for forbidden in (
        "device_token",
        "registration_code",
        "password",
        "token_hash",
        "code_hash",
        "Authorization",
        "salt",
    ):
        assert forbidden not in raw

    loaded = _cfg.load_config(path=p)
    assert loaded.agent_id == "la-1"
    assert loaded.server_url == "https://srv"


def test_config_strips_unexpected_secret_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "server_url": "https://srv",
                "agent_id": "la-1",
                "device_token": "should-not-load",
                "password": "pw",
                "token_hash": "h",
                "code_hash": "h",
            }
        ),
        encoding="utf-8",
    )
    cfg = _cfg.load_config(path=p)
    assert cfg.agent_id == "la-1"
    # 강제로 hasattr 체크 — DesktopConfig에 device_token 필드 자체가 없어야 한다.
    assert not hasattr(cfg, "device_token")


# ─── redaction ───────────────────────────────────────────────────────────


def test_redact_masks_sensitive_keys():
    out = _red.redact(
        {
            "agent_id": "la-1",
            "device_token": "tok",
            "Authorization": "Basic xxx",
            "nested": {"registration_code": "rc-secret", "label": "ok"},
            "list": [{"password": "p", "ok": 1}],
        }
    )
    assert out["agent_id"] == "la-1"
    assert out["device_token"] == "***REDACTED***"
    assert out["Authorization"] == "***REDACTED***"
    assert out["nested"]["registration_code"] == "***REDACTED***"
    assert out["nested"]["label"] == "ok"
    assert out["list"][0]["password"] == "***REDACTED***"
    assert out["list"][0]["ok"] == 1


def test_safe_summary_excludes_secrets():
    s = _red.safe_summary(
        {
            "agent_id": "la-1",
            "code_id": "rc-1",
            "label": "x",
            "device_token": "tok",
            "registration_code": "rc-secret",
        }
    )
    assert s == {"agent_id": "la-1", "code_id": "rc-1", "label": "x"}
