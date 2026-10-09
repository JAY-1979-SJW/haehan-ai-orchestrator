"""콘솔 인증 A안 경계 시험 — `get_current_user` 가 Bearer JWT 도 받는 정책(2026-10-07 대표님 결정).

확인 항목:
- role 매핑 표(owner→owner · admin→admin · operator→operator · viewer→viewer · 그 외→user)와 최소 권한(하위 역할이 상위 전용 라우트를 못 지남)
- 만료·위조·서명키 불일치·alg=none·변조·sub 없음·미등록/비활성/승인 대기 사용자·잘못된 스킴은 401
- 검증기 미등록이면 fail-closed(401)
- AUTH_ENABLED=false 동작 불변, Basic 동작 불변
사용자 DB·감사 로그는 임시 폴더. 실제 사용자·비밀 값은 쓰지 않는다.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.auth import auth_audit, user_db
from ai_orchestrator.auth import user_auth_router as user_auth
from ai_orchestrator.core import config
from tests.console_api_contract_support import (
    API,
    basic,
    disable_auth,
    enable_basic_auth,
    make_client,
)
from tools.gates import auth as gate
from tools.gates.auth import require_role

CHAT = f"{API}/chat/sessions"
RUN = f"{API}/ai-agent/run"
TASK = f"{API}/local-agents/la-1/tasks/task-1"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_get_db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: tmp_path / "auth_audit.jsonl")
    # 대화기록 저장소도 임시 폴더로(콘솔 라우트 호출 시 실제 파일 보호)
    from ai_orchestrator.tasks import chat_sessions as store

    monkeypatch.setattr(store, "_STORE_PATH", tmp_path / "chat_sessions.json")
    store._sessions.clear()
    yield
    store._sessions.clear()


@pytest.fixture
def client():
    return make_client()


def _make_user(email: str, role: str, *, enabled: bool = True) -> tuple[str, str]:
    """사용자 생성(+role·활성 지정) 후 (id, 정상 서명 토큰). role 지정은 시험용으로 DB 에 직접 쓴다."""
    user = user_db.create_user(email, "시험", "pw-jwt-demo-1")
    with user_db._conn() as con:
        con.execute(
            "UPDATE users SET role = ?, enabled = ? WHERE id = ?",
            (role, int(enabled), user["id"]),
        )
        con.commit()
    return user["id"], user_auth._make_token(user["id"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── role 매핑 매트릭스 (실제 require_role 의존성을 쓰는 시험용 미니 앱) ─────────


def _matrix_app() -> TestClient:
    app = FastAPI()
    sets = {
        "owner_only": ("owner",),
        "admin_owner": ("admin", "owner"),
        "operator_up": ("operator", "admin", "owner"),
        "viewer_up": ("admin", "owner", "viewer"),
    }
    for name, roles in sets.items():

        def _route(user: dict = Depends(require_role(*roles))) -> dict:
            return user

        app.get(f"/{name}")(_route)
    return TestClient(app, raise_server_exceptions=False)


# 기대 통과 표: (JWT role) → 통과해야 하는 라우트 집합. 표에 없는 조합은 403 이어야 한다.
_ALLOWED = {
    "owner": {"owner_only", "admin_owner", "operator_up", "viewer_up"},
    "admin": {"admin_owner", "operator_up", "viewer_up"},
    "operator": {"operator_up"},
    "viewer": {"viewer_up"},
    "user": set(),  # 가입 기본값 — 통과하는 라우트 없음
    "superuser": set(),  # 표에 없는 role 문자열도 최소 권한
    "": set(),
}
_ROUTES = ("owner_only", "admin_owner", "operator_up", "viewer_up")


@pytest.mark.parametrize("role", list(_ALLOWED))
@pytest.mark.parametrize("route", _ROUTES)
def test_role_mapping_matrix(monkeypatch, tmp_path, role, route):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user(f"{role or 'blank'}@example.com", role)
    r = _matrix_app().get(f"/{route}", headers=_bearer(token))
    assert r.status_code == (200 if route in _ALLOWED[role] else 403), (
        role,
        route,
        r.text,
    )


def test_mapping_table_is_exactly_the_documented_one():
    assert gate._JWT_ROLE_MAP == {
        "owner": "owner",
        "admin": "admin",
        "operator": "operator",
        "viewer": "viewer",
    }
    assert gate._JWT_NO_PRIVILEGE_ROLE == "user"


def test_jwt_user_identity_is_email_and_mapped_role(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user("Owner.Person@Example.com", "admin")
    r = _matrix_app().get("/admin_owner", headers=_bearer(token))
    assert r.json() == {
        "actor": "owner.person@example.com",
        "role": "admin",
    }  # 가입 시 이메일은 소문자로 저장


def test_role_is_read_from_db_each_request(monkeypatch, tmp_path):
    # 발급된 토큰에는 role 이 없다 — 권한 강등·비활성화가 다음 요청부터 바로 반영된다
    enable_basic_auth(monkeypatch, tmp_path)
    uid, token = _make_user("demote@example.com", "admin")
    app = _matrix_app()
    assert app.get("/admin_owner", headers=_bearer(token)).status_code == 200
    with user_db._conn() as con:
        con.execute("UPDATE users SET role = 'user' WHERE id = ?", (uid,))
        con.commit()
    assert app.get("/admin_owner", headers=_bearer(token)).status_code == 403
    with user_db._conn() as con:
        con.execute("UPDATE users SET role = 'admin', enabled = 0 WHERE id = ?", (uid,))
        con.commit()
    assert app.get("/admin_owner", headers=_bearer(token)).status_code == 401


# ── 실제 콘솔 라우트: 허용 role ──────────────────────────────────────────────


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_console_routes_accept_owner_and_admin_jwt(client, monkeypatch, tmp_path, role):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user(f"{role}@example.com", role)
    assert client.get(CHAT, headers=_bearer(token)).status_code == 200
    assert client.post(CHAT, json={"first_message": "hi"}, headers=_bearer(token)).status_code == 200


def test_viewer_jwt_reaches_task_poll_only(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user("viewer@example.com", "viewer")
    # 작업 폴링은 viewer 허용(404 = 인증·권한은 통과하고 작업만 없음), 대화기록·실행은 403
    assert client.get(TASK, headers=_bearer(token)).status_code == 404
    assert client.get(CHAT, headers=_bearer(token)).status_code == 403
    assert client.post(RUN, json={"prompt": "x"}, headers=_bearer(token)).status_code == 403


# ── 401: 만료·위조·변조·경계 ─────────────────────────────────────────────────


def _claims(sub: str, *, exp_delta: timedelta = timedelta(days=1)) -> dict:
    return {"sub": sub, "exp": datetime.now(UTC) + exp_delta}


def _forged_tokens(uid: str) -> dict[str, str]:
    good = user_auth._make_token(uid)
    header, payload, signature = good.split(".")
    other_uid_payload = jwt.encode(
        {"sub": "someone-else"},
        "irrelevant-secret-xxxxxxxxxxxxxxxxxxxx",
        algorithm="HS256",
    ).split(".")[1]
    return {
        "expired": jwt.encode(
            _claims(uid, exp_delta=timedelta(seconds=-60)),
            config.JWT_SECRET,
            algorithm="HS256",
        ),
        "wrong_secret": jwt.encode(_claims(uid), "not-the-server-secret-xxxxxxxxxxxxxxxx", algorithm="HS256"),
        "alg_none": jwt.encode(_claims(uid), None, algorithm="none"),
        "tampered_payload": f"{header}.{other_uid_payload}.{signature}",
        "truncated_signature": f"{header}.{payload}.{signature[:-6]}",
        "no_sub": jwt.encode(
            {"exp": datetime.now(UTC) + timedelta(days=1)},
            config.JWT_SECRET,
            algorithm="HS256",
        ),
        "garbage": "not-a-jwt",
        "empty_parts": "..",
    }


@pytest.mark.parametrize(
    "kind",
    [
        "expired",
        "wrong_secret",
        "alg_none",
        "tampered_payload",
        "truncated_signature",
        "no_sub",
        "garbage",
        "empty_parts",
    ],
)
@pytest.mark.parametrize("url", [CHAT, TASK])
def test_invalid_tokens_are_401_on_console_routes(client, monkeypatch, tmp_path, kind, url):
    enable_basic_auth(monkeypatch, tmp_path)
    uid, _ = _make_user("victim@example.com", "owner")  # 권한이 가장 높은 계정을 노린 위조
    token = _forged_tokens(uid)[kind]
    r = client.get(url, headers=_bearer(token))
    assert r.status_code == 401, (kind, r.text)
    assert r.headers.get("www-authenticate") == "Bearer"


def test_invalid_token_cannot_run_the_agent(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid, _ = _make_user("victim@example.com", "owner")
    forged = _forged_tokens(uid)["wrong_secret"]
    assert client.post(RUN, json={"prompt": "x"}, headers=_bearer(forged)).status_code == 401


def test_token_of_unknown_user_is_401(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    token = user_auth._make_token("no-such-user")
    assert client.get(CHAT, headers=_bearer(token)).status_code == 401


def test_pending_user_token_is_401(client, monkeypatch, tmp_path):
    # 승인 대기(enabled=0) 계정은 role 이 owner 로 돼 있어도 거절
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user("pending@example.com", "owner", enabled=False)
    assert client.get(CHAT, headers=_bearer(token)).status_code == 401


def test_expired_token_of_valid_owner_is_401_while_fresh_one_passes(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid, fresh = _make_user("owner@example.com", "owner")
    stale = jwt.encode(
        _claims(uid, exp_delta=timedelta(seconds=-1)),
        config.JWT_SECRET,
        algorithm="HS256",
    )
    time.sleep(0.01)
    assert client.get(CHAT, headers=_bearer(stale)).status_code == 401
    assert client.get(CHAT, headers=_bearer(fresh)).status_code == 200


def test_wrong_scheme_and_empty_bearer_are_rejected(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user("owner@example.com", "owner")
    assert client.get(CHAT, headers={"Authorization": f"Token {token}"}).status_code == 401
    assert client.get(CHAT, headers={"Authorization": "Bearer "}).status_code in (
        401,
        403,
    )
    assert client.get(CHAT, headers={"Authorization": token}).status_code == 401  # 스킴 없음


def test_no_credentials_still_401(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(CHAT).status_code == 401


def test_fail_closed_when_no_bearer_resolver_registered(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _make_user("owner@example.com", "owner")
    monkeypatch.setattr(gate, "_bearer_resolver", None)
    assert client.get(CHAT, headers=_bearer(token)).status_code == 401


def test_resolver_is_registered_by_user_auth_router():
    # 앱이 뜨면(user_auth_router import) 검증 함수가 등록돼 있어야 JWT 가 동작한다
    assert gate._bearer_resolver is user_auth.resolve_bearer_user


# ── 불변: AUTH_ENABLED=false, Basic ──────────────────────────────────────────


def test_auth_disabled_ignores_authorization_header_and_acts_as_owner(client, monkeypatch):
    disable_auth(monkeypatch)
    assert client.get(CHAT).status_code == 200
    assert client.get(CHAT, headers=_bearer("garbage")).status_code == 200  # AUTH off 는 토큰을 보지 않는다(기존 동작)
    assert gate.get_current_user(credentials=None) == dict(gate._DUMMY_USER)  # 직접 호출 호환(bearer 기본값 무시)


def test_basic_behaviour_is_unchanged(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert client.get(CHAT, headers=basic("owner_u")).status_code == 200
    assert client.get(CHAT, headers=basic("admin_u")).status_code == 200
    assert client.get(CHAT, headers=basic("viewer_u")).status_code == 403
    bad = {"Authorization": basic("owner_u")["Authorization"][:-2] + "xx"}
    assert client.get(CHAT, headers=bad).status_code == 401


def test_basic_actor_and_role_are_unchanged(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    r = _matrix_app().get("/admin_owner", headers=basic("admin_u"))
    assert r.json() == {"actor": "admin_u", "role": "admin"}
