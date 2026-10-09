"""register-with-code client + cmd_register_with_code 흐름 단위 테스트.

mock urlopen으로 서버를 흉내내고:
  - 성공 시 agent_id/code_id/device_token 추출
  - 실패 시 generic 메시지로 RegistrationError
  - 응답 본문/원문이 예외 메시지에 노출되지 않음
  - cmd_register_with_code가 config에는 token을 저장하지 않고
    keyring(=fake)에만 저장하는지 확인
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch
from urllib import error as _urlerr

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

from core.agent_runtime import agent as _agent
from core.agent_runtime.common import desktop_config as _cfg
from core.agent_runtime.connection import token_store as _ts
from core.agent_runtime.connection.registration_client import (
    RegistrationError,
    register_with_code,
)


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _ok_opener(payload: dict):
    def _opener(req, timeout=10):
        assert req.method == "POST"
        assert "/api/v1/local-agents/register-with-code" in req.full_url
        # Authorization 헤더가 절대 들어가지 않아야 한다.
        for h, _ in req.headers.items() if hasattr(req.headers, "items") else []:
            assert h.lower() != "authorization"
        return _FakeResp(json.dumps(payload).encode())

    return _opener


def test_register_with_code_success_returns_agent_id_and_token():
    payload = {
        "agent_id": "la-1234567890ab",
        "device_token": "dt-secret-xxx",
        "code_id": "rc-deadbeef0001",
        "host": "test-pc",
        "os_name": "Windows 11",
        "version": "0.1.0",
        "registered_at": "2026-04-30T12:00:00",
        "label": "lab",
        "allowed_actions": ["open_url"],
    }
    meta, token = register_with_code(
        "https://srv.example",
        "RC-PLAINTEXT-XYZ",
        host="test-pc",
        os_name="Windows 11",
        version="0.1.0",
        _opener=_ok_opener(payload),
    )
    assert meta.agent_id == "la-1234567890ab"
    assert meta.code_id == "rc-deadbeef0001"
    assert token == "dt-secret-xxx"


def test_register_with_code_http_error_is_generic():
    def _err_opener(req, timeout=10):
        raise _urlerr.HTTPError(
            req.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"detail":{"code":"INVALID","registration_code":"PEEK"}}'),
        )

    with pytest.raises(RegistrationError) as ei:
        register_with_code(
            "https://srv",
            "RC-X",
            host="h",
            os_name="o",
            version="v",
            _opener=_err_opener,
        )
    msg = ei.value.generic_message
    assert "PEEK" not in msg
    assert "RC-X" not in msg
    assert msg.startswith("invalid_registration_code") or msg.startswith("registration_failed_http_")


def test_register_with_code_invalid_response():
    def _bad(req, timeout=10):
        return _FakeResp(b"not json")

    with pytest.raises(RegistrationError):
        register_with_code(
            "https://srv",
            "RC-X",
            host="h",
            os_name="o",
            version="v",
            _opener=_bad,
        )


# ─── cmd_register_with_code ──────────────────────────────────────────────


class _FakeKeyring:
    def __init__(self):
        self._store = {}

    def get_keyring(self):
        be = type("B", (), {})()
        be.__class__.__name__ = "FakeBackend"
        return be

    def set_password(self, s, u, p):
        self._store[(s, u)] = p

    def get_password(self, s, u):
        return self._store.get((s, u))

    def delete_password(self, s, u):
        self._store.pop((s, u), None)


@pytest.fixture
def fake_kr(monkeypatch, tmp_path):
    fk = _FakeKeyring()
    monkeypatch.setattr(_ts, "_try_import_keyring", lambda: fk)
    monkeypatch.setattr(_cfg, "DEFAULT_CONFIG_PATH", tmp_path / "config.json")
    return fk


def test_cmd_register_with_code_writes_config_without_secret(fake_kr, tmp_path, capsys):
    payload = {
        "agent_id": "la-aaaaaaaaaaaa",
        "device_token": "dt-VERY-SECRET",
        "code_id": "rc-aaaaaaaa0001",
        "host": "pc-1",
        "os_name": "Windows 11",
        "version": "0.1.0",
        "registered_at": "2026-04-30T12:00:00",
        "label": "demo",
        "allowed_actions": ["open_url"],
    }
    with patch("core.agent_runtime.agent._register_with_code") as m:
        # m은 (meta, token) 튜플을 반환해야 한다 (실제 구현 시그니처 동일).
        from core.agent_runtime.connection.registration_client import RegistrationResult

        m.return_value = (
            RegistrationResult(
                agent_id=payload["agent_id"],
                code_id=payload["code_id"],
                host=payload["host"],
                os_name=payload["os_name"],
                version=payload["version"],
                registered_at=payload["registered_at"],
                label=payload["label"],
                allowed_actions=payload["allowed_actions"],
            ),
            payload["device_token"],
        )
        rc = _agent.cmd_register_with_code(
            server_url="https://srv.example",
            registration_code="RC-PLAINTEXT-NEVER-LOG",
        )
    assert rc == 0

    cfg_path = _cfg.DEFAULT_CONFIG_PATH
    raw = cfg_path.read_text(encoding="utf-8")
    assert "dt-VERY-SECRET" not in raw
    assert "RC-PLAINTEXT-NEVER-LOG" not in raw
    for k in ("device_token", "registration_code", "password", "token_hash", "code_hash", "Authorization"):
        assert k not in raw
    parsed = json.loads(raw)
    assert parsed["agent_id"] == "la-aaaaaaaaaaaa"

    # token은 keyring(=fake)에 저장되어야 한다.
    assert fake_kr.get_password("haehan-agent", "https://srv.example::la-aaaaaaaaaaaa") == "dt-VERY-SECRET"

    out = capsys.readouterr().out
    assert "dt-VERY-SECRET" not in out
    assert "RC-PLAINTEXT-NEVER-LOG" not in out
    assert "la-aaaaaaaaaaaa" in out
    assert "rc-aaaaaaaa0001" in out


def test_cmd_register_with_code_failure_no_secret(fake_kr, capsys):
    with patch(
        "core.agent_runtime.agent._register_with_code",
        side_effect=RegistrationError(http_status=400, generic_message="invalid_registration_code"),
    ):
        rc = _agent.cmd_register_with_code(
            server_url="https://srv.example",
            registration_code="RC-PLAINTEXT-NEVER-LOG",
        )
    assert rc == 1
    err = capsys.readouterr().err
    assert "RC-PLAINTEXT-NEVER-LOG" not in err


def test_cmd_status_does_not_print_token(fake_kr, tmp_path, capsys):
    # config 저장
    _cfg.save_config(
        _cfg.DesktopConfig(
            server_url="https://srv.example",
            agent_id="la-zzz",
            label="x",
            created_at="now",
            version="0.1.0",
        )
    )
    fake_kr.set_password("haehan-agent", "https://srv.example::la-zzz", "secret-token-XYZ")
    rc = _agent.cmd_status()
    assert rc == 0
    out = capsys.readouterr().out
    assert "secret-token-XYZ" not in out
    parsed = json.loads(out)
    assert parsed["token_saved"] is True
    assert parsed["agent_id"] == "la-zzz"
    assert "device_token" not in parsed


def test_cmd_status_token_missing_when_not_saved(fake_kr, capsys):
    _cfg.save_config(
        _cfg.DesktopConfig(
            server_url="https://srv.example",
            agent_id="la-no-token",
            version="0.1.0",
        )
    )
    rc = _agent.cmd_status()
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["token_saved"] is False
