from pathlib import Path
from uuid import uuid4

import pytest

from scripts.auth import credentials


def _runtime_paths() -> tuple[Path, Path]:
    base = Path("data") / "test_runtime" / "credentials_cli_security" / uuid4().hex
    return base / "credentials.json", base / ".cred.key"


def test_credentials_cli_get_masks_identifier(monkeypatch, capsys):
    cred_file, key_file = _runtime_paths()
    monkeypatch.setattr(credentials, "CRED_FILE", cred_file)
    monkeypatch.setattr(credentials, "KEY_FILE", key_file)

    credentials.set_cred("naver", id="skyjwshin@example.com", pw="password-123")
    credentials._cmd_get("naver")

    output = capsys.readouterr().out
    assert "skyjwshin@example.com" not in output
    assert "sk***@example.com" in output
    assert "password-123" not in output


def test_google_password_credentials_are_disabled(monkeypatch):
    cred_file, key_file = _runtime_paths()
    monkeypatch.setattr(credentials, "CRED_FILE", cred_file)
    monkeypatch.setattr(credentials, "KEY_FILE", key_file)

    with pytest.raises(ValueError):
        credentials.set_cred("google", id="skyjwshin@example.com", pw="password-123")

    assert credentials.get_cred("google") == {"id": "", "pw": ""}


def test_credentials_cli_list_masks_identifiers(monkeypatch, capsys):
    cred_file, key_file = _runtime_paths()
    monkeypatch.setattr(credentials, "CRED_FILE", cred_file)
    monkeypatch.setattr(credentials, "KEY_FILE", key_file)

    credentials.set_cred("naver", id="local-admin", pw="password-123")
    credentials._cmd_list()

    output = capsys.readouterr().out
    assert "local-admin" not in output
    assert "lo***in" in output
    assert "password-123" not in output
