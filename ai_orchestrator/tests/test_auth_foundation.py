"""1단계 auth 토대 단위 테스트.

AUTH_ENABLED=False 에서 기존 동작에 영향 주지 않음을 보장한다.
"""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator import auth, config


def test_auth_disabled_returns_dummy_owner():
    assert config.AUTH_ENABLED is False
    user = auth.get_current_user(credentials=None)
    assert user == {"actor": "system", "role": "owner"}


def test_require_role_allows_dummy_owner():
    dep = auth.require_role("owner", "admin")
    user = dep(user=auth.get_current_user(credentials=None))
    assert user["role"] == "owner"


def test_require_role_rejects_mismatch():
    dep = auth.require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        dep(user={"actor": "x", "role": "viewer"})
    assert excinfo.value.status_code == 403


def test_load_users_reads_http_users_json():
    users = auth._load_users()
    assert "owner" in users
    assert users["owner"]["role"] == "owner"
    assert users["owner"]["enabled"] is True


if __name__ == "__main__":
    test_auth_disabled_returns_dummy_owner()
    print("PASS: AUTH_ENABLED=False dummy owner")
    test_require_role_allows_dummy_owner()
    print("PASS: require_role dummy owner 허용")
    test_require_role_rejects_mismatch()
    print("PASS: require_role 역할 불일치 403")
    test_load_users_reads_http_users_json()
    print("PASS: _load_users http_users.json 로드")
    print("\n모든 auth 토대 테스트 통과")
