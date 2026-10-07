"""콘솔 HTTP 계약 — 로그인 확인 경로 GET /api/v1/users/me (userAuth.ts:76-78)와 폴백 GET /api/v1/auth/me (:84).

홈(page.tsx)은 `getMe()` 가 실패하면 /about 으로 보낸다. 사용자 DB·감사 로그는 임시 폴더로 바꿔 실제 파일을 쓰지 않는다.
동작 변경 없음.

⚠ 마지막 절의 '인증 방식 불일치' 시험은 **현재 동작을 기록**하는 특성화 시험이다(옳다는 뜻이 아님). 정책이 정해져 동작이 바뀌면
그 시험을 새 정책에 맞게 고친다. 배경과 사실관계는 아래 절 주석 참고.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors import user_auth_router as user_auth
from ai_orchestrator.persistence import auth_audit, user_db
from tests.console_api_contract_support import (
    API,
    basic,
    disable_auth,
    enable_basic_auth,
    make_client,
)

ME = f"{API}/users/me"
AUTH_ME = f"{API}/auth/me"

_USER_KEYS = {"id", "email", "name", "role", "plan", "created_at"}


@pytest.fixture(autouse=True)
def _isolated_user_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_get_db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: tmp_path / "auth_audit.jsonl")


@pytest.fixture
def client():
    return make_client()


def _approved_user_token() -> tuple[dict, str]:
    user = user_db.create_user("console@example.com", "콘솔", "pw-console-demo-1")
    assert user_db.approve_user(user["id"])
    return user, user_auth._make_token(user["id"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── GET /users/me ────────────────────────────────────────────────────────────


def test_me_auth_disabled_returns_owner_without_token(client, monkeypatch):
    disable_auth(monkeypatch)
    r = client.get(ME)
    assert r.status_code == 200
    assert set(r.json()) == _USER_KEYS
    assert r.json()["role"] == "owner"


def test_me_requires_token_when_auth_enabled(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(ME).status_code == 401


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_me_rejects_malformed_token(client, monkeypatch, tmp_path, token):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_rejects_token_of_unknown_user(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    token = user_auth._make_token("no-such-user-id")
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_returns_user_without_password_hash(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    user, token = _approved_user_token()
    r = client.get(ME, headers=_bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == _USER_KEYS
    assert body["id"] == user["id"]
    assert body["email"] == "console@example.com"
    assert "password_hash" not in body and "password" not in body


def test_me_rejects_pending_user_token(client, monkeypatch, tmp_path):
    # 승인 대기(enabled=0) 사용자는 토큰이 있어도 조회되지 않는다
    enable_basic_auth(monkeypatch, tmp_path)
    user = user_db.create_user("pending@example.com", "대기", "pw-pending-demo-1")
    token = user_auth._make_token(user["id"])
    assert client.get(ME, headers=_bearer(token)).status_code == 401


# ── GET /auth/me (getMe 폴백) ────────────────────────────────────────────────


def test_auth_me_requires_credentials_when_auth_enabled(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(AUTH_ME).status_code == 401


@pytest.mark.parametrize(
    ("user", "role"),
    [("owner_u", "owner"), ("admin_u", "admin"), ("viewer_u", "viewer")],
)
def test_auth_me_returns_only_actor_and_role(client, monkeypatch, tmp_path, user, role):
    enable_basic_auth(monkeypatch, tmp_path)
    r = client.get(AUTH_ME, headers=basic(user))
    assert r.status_code == 200
    assert r.json() == {"actor": user, "role": role}


def test_auth_me_auth_disabled_is_system_owner(client, monkeypatch):
    disable_auth(monkeypatch)
    assert client.get(AUTH_ME).json() == {"actor": "system", "role": "owner"}


# ── 인증 방식 불일치 (현재 동작 기록 — 특성화 시험) ──────────────────────────
# 사실관계(코드 근거):
#  - 로그인 확인(/users/me)은 JWT Bearer(`get_jwt_user`), 콘솔 라우트(/chat/sessions, /ai-agent/run, /local-agents/.../tasks)는
#    Basic(`require_role` → `get_current_user`) 이다. user_auth_router.py 의 주석도 "일반 사용자 인증은 JWT, 관리자 작업은 Basic"이라 적는다.
#  - admin-web 프록시(`api/proxy/[...path]/route.ts`)는 클라이언트 Authorization → `haehan_ai_token` 쿠키(JWT) → 서버 Basic 순으로
#    인증을 붙인다. 로그인하면 `setToken()`(userAuth.ts)이 이 쿠키를 심는다.
#  - 따라서 AUTH_ENABLED=true(docker-compose 기본) 운영 웹에서 쿠키가 있는 로그인 사용자의 콘솔 호출은 Bearer 로 나가
#    아래처럼 401 이 될 수 있다. 쿠키가 없을 때만 서버 Basic 이 붙어 통과한다. 실제 브라우저·운영에서 확인한 것은 아니다(코드 추정).


def test_jwt_bearer_is_not_accepted_by_basic_gated_console_routes(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _approved_user_token()
    headers = _bearer(token)
    assert client.get(ME, headers=headers).status_code == 200  # 같은 토큰이 로그인 확인에서는 통과
    assert client.get(f"{API}/chat/sessions", headers=headers).status_code == 401
    assert client.post(f"{API}/ai-agent/run", json={"prompt": "x"}, headers=headers).status_code == 401
    assert client.get(f"{API}/local-agents/la-1/tasks/task-1", headers=headers).status_code == 401


def test_basic_credentials_are_not_accepted_by_jwt_gated_users_me(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(AUTH_ME, headers=basic("owner_u")).status_code == 200
    assert client.get(ME, headers=basic("owner_u")).status_code == 401
