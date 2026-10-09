"""1단계 auth 토대 단위 테스트.

AUTH_ENABLED 상태와 http_users.json 경로를 테스트마다 명시적으로 주입해
로컬 개발자 PC의 시크릿/환경 설정(.env, gitignored 시크릿)과 무관하게
결정적으로 실행된다.
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

from ai_orchestrator.core import config
from tools.gates import auth


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)


@pytest.fixture
def auth_users_file(tmp_path, monkeypatch):
    users_path = tmp_path / "http_users.json"
    users_path.write_text(
        json.dumps(
            [
                {
                    "username": "owner",
                    "password_hash": "sha256$00$00",
                    "role": "owner",
                    "enabled": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "HTTP_USERS_PATH", users_path)
    return users_path


def test_auth_disabled_returns_dummy_owner(auth_disabled):
    assert config.AUTH_ENABLED is False
    user = auth.get_current_user(credentials=None)
    assert user["actor"] == "system"
    assert user["role"] == "owner"
    assert user["organization_ids"] == ["default-org"]
    assert user["active_organization_id"] == "default-org"


def test_require_role_allows_dummy_owner(auth_disabled):
    dep = auth.require_role("owner", "admin")
    user = dep(user=auth.get_current_user(credentials=None))
    assert user["role"] == "owner"


def test_require_role_rejects_mismatch():
    dep = auth.require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        dep(user={"actor": "x", "role": "viewer"})
    assert excinfo.value.status_code == 403


def test_load_users_reads_http_users_json(auth_users_file):
    users = auth._load_users()
    assert "owner" in users
    assert users["owner"]["role"] == "owner"
    assert users["owner"]["enabled"] is True
