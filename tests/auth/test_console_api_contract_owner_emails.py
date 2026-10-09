"""OWNER_EMAILS — 설정된 이메일의 '승인된 활성 계정'만 owner 로 취급한다(대표님 결정).

확인 항목: 설정 파싱(대소문자·구분자·잘못된 항목), 승인된 활성 계정만 owner, 미승인·미등록·별칭 불가, 설정이 비면 기존 동작,
DB role 불변, Basic 계정 영향 없음, owner 이메일 계정 승인은 owner 만(admin 의 권한 상승 차단), owner 이메일 가입 감사 표시.
사용자 DB·감사 로그는 임시 폴더. 실제 사용자·이메일은 쓰지 않는다(example.com 합성 값).
"""

from __future__ import annotations

import json

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.auth import auth_audit, user_db
from ai_orchestrator.auth import user_auth_router as user_auth
from ai_orchestrator.core import config
from tests.console_api_contract_support import (
    API,
    basic,
    enable_basic_auth,
    make_client,
)
from tools.gates import auth as gate
from tools.gates.auth import require_role

OWNER = "boss@example.com"
CHAT = f"{API}/chat/sessions"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_get_db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: tmp_path / "auth_audit.jsonl")
    from ai_orchestrator.tasks import chat_sessions as store

    monkeypatch.setattr(store, "_STORE_PATH", tmp_path / "chat_sessions.json")
    store._sessions.clear()
    gate._owner_email_logged.clear()
    yield
    store._sessions.clear()


@pytest.fixture
def client():
    return make_client()


def _set_owner_emails(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(config, "OWNER_EMAILS", config.parse_owner_emails(raw))


def _user(email: str, role: str = "user", *, enabled: bool = True) -> tuple[str, str]:
    u = user_db.create_user(email, "시험", "pw-owner-mail-demo-1")
    with user_db._conn() as con:
        con.execute(
            "UPDATE users SET role = ?, enabled = ? WHERE id = ?",
            (role, int(enabled), u["id"]),
        )
        con.commit()
    return u["id"], user_auth._make_token(u["id"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _row(uid: str) -> dict:
    row = user_db._get_user_unfiltered(uid)
    assert row is not None
    return row


def _db_role(uid: str) -> str:
    return _row(uid)["role"]


def _matrix() -> TestClient:
    app = FastAPI()

    def _owner(user: dict = Depends(require_role("owner"))) -> dict:
        return user

    def _admin(user: dict = Depends(require_role("admin", "owner"))) -> dict:
        return user

    app.get("/owner_only")(_owner)
    app.get("/admin_owner")(_admin)
    return TestClient(app, raise_server_exceptions=False)


# ── 설정 파싱 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", set()),
        ("   ", set()),
        (None, set()),
        ("Boss@Example.COM", {"boss@example.com"}),
        (
            " a@x.com , b@x.com ;c@x.com  d@x.com ",
            {"a@x.com", "b@x.com", "c@x.com", "d@x.com"},
        ),
        ("not-an-email, @x.com, a@, a@@x.com, a@b@c.com", set()),
        ("ok@x.com,bad,ok@x.com", {"ok@x.com"}),
    ],
)
def test_parse_owner_emails(raw, expected):
    assert config.parse_owner_emails(raw) == expected


def test_default_config_is_empty_when_env_unset():
    assert config.parse_owner_emails("") == frozenset()


# ── 판정: 승인된 활성 계정만 owner ───────────────────────────────────────────


def test_approved_owner_email_account_is_owner_without_db_change(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid, token = _user(OWNER, "user")
    r = _matrix().get("/owner_only", headers=_bearer(token))
    assert r.status_code == 200
    assert r.json() == {"actor": OWNER, "role": "owner", "role_source": "OWNER_EMAILS"}
    assert _db_role(uid) == "user"  # DB 의 role 은 바꾸지 않는다


def test_case_insensitive_between_config_and_account(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, "  BOSS@Example.COM ")
    _, token = _user("Boss@EXAMPLE.com")  # 가입 시 소문자로 저장된다
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 200


def test_owner_email_reaches_console_routes(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, token = _user(OWNER)
    assert client.get(CHAT, headers=_bearer(token)).status_code == 200


def test_other_account_is_not_owner(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, token = _user("someone@example.com")
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 403


@pytest.mark.parametrize(
    "alias",
    [
        "boss+tag@example.com",
        "b.oss@example.com",
        "boss@example.com.evil.io",
        "xboss@example.com",
    ],
)
def test_aliases_and_lookalikes_are_not_owner(monkeypatch, tmp_path, alias):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, token = _user(alias)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 403


def test_pending_owner_email_account_cannot_authenticate(monkeypatch, tmp_path):
    # 미승인(enabled=0)은 owner 이메일이어도 토큰 자체가 401 — owner 가 될 수 없다
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, token = _user(OWNER, enabled=False)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 401
    assert _matrix().get("/admin_owner", headers=_bearer(token)).status_code == 401


def test_disabled_after_approval_loses_owner_immediately(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid, token = _user(OWNER)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 200
    with user_db._conn() as con:
        con.execute("UPDATE users SET enabled = 0 WHERE id = ?", (uid,))
        con.commit()
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 401


def test_unknown_enabled_state_is_not_elevated():
    # 활성 여부를 알 수 없는 레코드(enabled 없음)는 fail-closed
    assert gate.is_owner_email_account({"email": OWNER}) is False
    assert gate.is_owner_email_account({"email": OWNER, "enabled": 0}) is False
    assert gate.is_owner_email_account({"email": OWNER, "enabled": 1}) is False  # 설정이 비어 있으면 대상 아님


def test_empty_setting_keeps_existing_behaviour(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, "")
    _, token = _user(OWNER)
    r = _matrix().get("/owner_only", headers=_bearer(token))
    assert r.status_code == 403  # 가입 기본 role "user" 그대로


def test_removing_email_from_setting_revokes_owner(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _, token = _user(OWNER)
    _set_owner_emails(monkeypatch, OWNER)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 200
    _set_owner_emails(monkeypatch, "")
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 403


def test_elevates_admin_but_never_demotes_db_owner(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, admin_token = _user(OWNER, "admin")
    assert _matrix().get("/owner_only", headers=_bearer(admin_token)).status_code == 200  # admin → owner
    _, db_owner_token = _user("dbowner@example.com", "owner")  # 목록에 없어도 DB owner 는 그대로
    r = _matrix().get("/owner_only", headers=_bearer(db_owner_token))
    assert r.status_code == 200
    assert "role_source" not in r.json()  # 설정 때문이 아니라 DB role 때문


def test_basic_accounts_are_unaffected_even_if_username_looks_like_owner_email(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    path = config.HTTP_USERS_PATH
    users = json.loads(path.read_text(encoding="utf-8"))
    users.append(
        {
            "username": OWNER,
            "password_hash": users[0]["password_hash"],
            "role": "viewer",
            "enabled": True,
        }
    )
    path.write_text(json.dumps(users), encoding="utf-8")
    # Basic 자격으로 owner 이메일 문자열을 사용자명으로 써도 role 은 파일 값(viewer) 그대로 — 설정은 JWT 계정에만 적용
    import base64

    token = base64.b64encode(f"{OWNER}:pw_owner_demo".encode()).decode()
    r = _matrix().get("/owner_only", headers={"Authorization": f"Basic {token}"})
    assert r.status_code in (401, 403)  # 비밀번호가 맞아도 owner 로 올라가지 않는다
    assert basic("owner_u")["Authorization"]  # (참고) 기존 합성 계정 헤더는 그대로 생성된다


def test_role_source_is_logged_once_with_masked_email(monkeypatch, tmp_path, caplog):
    import logging

    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, token = _user(OWNER)
    app = _matrix()
    with caplog.at_level(logging.INFO, logger=gate.logger.name):
        app.get("/owner_only", headers=_bearer(token))
        app.get("/owner_only", headers=_bearer(token))
    lines = [r.getMessage() for r in caplog.records if "OWNER_EMAILS" in r.getMessage()]
    assert len(lines) == 1
    assert OWNER not in lines[0]  # 이메일 원문은 남기지 않는다
    assert "b***@example.com" in lines[0]


# ── 이메일 사칭: 가입·승인 흐름 ──────────────────────────────────────────────
# 이메일 인증이 없다(가입은 이메일 소유 확인 없이 접수). 그래서 남이 owner 이메일로 먼저 가입할 수 있다.
# 방어: (1) 미승인 계정은 owner 불가 (2) owner 이메일 계정 승인은 owner 만 — admin 이 승인해 owner 를 만드는 상승 차단
# (3) owner 이메일 가입은 감사 로그에 표시 (4) 이메일은 유일해서 본인이 먼저 가입하면 남이 같은 이메일로 가입할 수 없다.


def _pending(email: str) -> str:
    return user_db.create_user(email, "대기", "pw-pending-demo-1")["id"]


def test_squatter_pending_account_has_no_power_until_approved(monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid = _pending(OWNER)  # 누군가 owner 이메일로 먼저 가입(미승인)
    token = user_auth._make_token(uid)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 401


def test_admin_cannot_approve_owner_email_account(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid = _pending(OWNER)
    r = client.post(f"{API}/users/{uid}/approve", headers=basic("admin_u"))
    assert r.status_code == 403
    assert _row(uid)["enabled"] == 0  # 승인되지 않았다


def test_jwt_admin_cannot_approve_owner_email_account(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    _, admin_token = _user("admin2@example.com", "admin")
    uid = _pending(OWNER)
    assert client.post(f"{API}/users/{uid}/approve", headers=_bearer(admin_token)).status_code == 403
    assert _row(uid)["enabled"] == 0


def test_owner_can_approve_owner_email_account(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid = _pending(OWNER)
    assert client.post(f"{API}/users/{uid}/approve", headers=basic("owner_u")).status_code == 200
    assert _row(uid)["enabled"] == 1
    token = user_auth._make_token(uid)
    assert _matrix().get("/owner_only", headers=_bearer(token)).status_code == 200  # 승인 후에야 owner


def test_admin_can_still_approve_ordinary_accounts(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    uid = _pending("ordinary@example.com")
    assert client.post(f"{API}/users/{uid}/approve", headers=basic("admin_u")).status_code == 200


def test_approve_unknown_user_is_still_404(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, OWNER)
    assert client.post(f"{API}/users/nope/approve", headers=basic("admin_u")).status_code == 404


def test_empty_setting_leaves_approval_unchanged(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    _set_owner_emails(monkeypatch, "")
    uid = _pending(OWNER)
    assert client.post(f"{API}/users/{uid}/approve", headers=basic("admin_u")).status_code == 200


def test_owner_email_signup_is_marked_in_audit_log(client, monkeypatch, tmp_path):
    _set_owner_emails(monkeypatch, OWNER)
    body = {"email": OWNER.upper(), "name": "대표", "password": "Pw-demo-12345-xyz"}
    r = client.post(f"{API}/users/signup", json=body)
    assert r.status_code == 201
    rows = [json.loads(line) for line in (tmp_path / "auth_audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["event"] == "signup" and row["outcome"] == "owner_email_pending" for row in rows)
    assert all(OWNER not in json.dumps(row) for row in rows)  # 감사 로그의 이메일은 마스킹


def test_ordinary_signup_is_not_marked(client, monkeypatch, tmp_path):
    _set_owner_emails(monkeypatch, OWNER)
    r = client.post(
        f"{API}/users/signup",
        json={
            "email": "plain@example.com",
            "name": "일반",
            "password": "Pw-demo-12345-xyz",
        },
    )
    assert r.status_code == 201
    text = (tmp_path / "auth_audit.jsonl").read_text(encoding="utf-8")
    assert "owner_email_pending" not in text


def test_owner_email_cannot_be_registered_twice(client, monkeypatch, tmp_path):
    # 본인이 먼저 가입하면 남이 같은 이메일로 가입할 수 없다(이메일 유일)
    _set_owner_emails(monkeypatch, OWNER)
    body = {"email": OWNER, "name": "대표", "password": "Pw-demo-12345-xyz"}
    assert client.post(f"{API}/users/signup", json=body).status_code == 201
    assert client.post(f"{API}/users/signup", json={**body, "name": "사칭"}).status_code == 409
