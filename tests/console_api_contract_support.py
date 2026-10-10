"""AI 작업 콘솔 HTTP 계약 시험 공용 도우미.

admin-web 홈(UniversalChat)이 부르는 백엔드 URL 5종을 **실제 앱 객체**(`ai_orchestrator.asgi.app`)로 시험한다.
실제 라우터 마운트·접두(`/api/v1`)·의존성이 그대로 걸려 있어, 라우트가 빠지거나 접두가 바뀌면 여기서 먼저 깨진다.
실제 비밀번호·운영 파일은 쓰지 않는다 — 합성 사용자와 임시 폴더만 사용한다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.core import config as _config
from ai_orchestrator.asgi import app

API = "/api/v1"

# 합성 계정 — 비밀번호는 해시 검증용 식별자일 뿐 운영 의미가 없다.
_PASSWORDS = {
    "owner_u": ("pw_owner_demo", "owner"),
    "admin_u": ("pw_admin_demo", "admin"),
    "viewer_u": ("pw_viewer_demo", "viewer"),
}


def _salted_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"sha256${salt.hex()}${hashlib.sha256(salt + password.encode('utf-8')).hexdigest()}"


def basic(username: str) -> dict[str, str]:
    """합성 계정의 Basic 인증 헤더."""
    password = _PASSWORDS[username][0]
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def make_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def enable_basic_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AUTH_ENABLED=True + 합성 http_users.json (운영 파일은 건드리지 않는다)."""
    users = [
        {
            "username": name,
            "password_hash": _salted_hash(pw),
            "role": role,
            "enabled": True,
        }
        for name, (pw, role) in _PASSWORDS.items()
    ]
    path = tmp_path / "http_users.json"
    path.write_text(json.dumps(users), encoding="utf-8")
    monkeypatch.setattr(_config, "AUTH_ENABLED", True)
    monkeypatch.setattr(_config, "HTTP_USERS_PATH", path)


def disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTH_ENABLED=False — 자기완결 데스크톱 모드(모든 요청이 owner)."""
    monkeypatch.setattr(_config, "AUTH_ENABLED", False)
