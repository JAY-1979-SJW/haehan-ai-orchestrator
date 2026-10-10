"""승인 대기 계정 거절·삭제 라우트 POST /api/v1/users/{id}/reject — owner 전용, 승인된 계정은 삭제 불가, 감사 로그.

이메일 인증이 없어 남이 owner 이메일로 먼저 가입(선점)할 수 있다. 지울 수단이 없으면 본인이 가입하지 못하므로 복구용으로 둔다.
사용자 DB·감사 로그는 임시 폴더. 합성 이메일(example.com)만 쓴다.
"""

from __future__ import annotations

import json

import pytest

from ai_orchestrator.core import config
from ai_orchestrator.auth import user_auth_router as user_auth
from ai_orchestrator.auth import auth_audit, user_db
from tests.console_api_contract_support import API, basic, enable_basic_auth, make_client

OWNER_MAIL = "boss@example.com"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_get_db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: tmp_path / "auth_audit.jsonl")


@pytest.fixture
def client():
    return make_client()


def _pending(email: str) -> str:
    return user_db.create_user(email, "대기", "pw-pending-demo-1")["id"]


def _active(email: str, role: str = "user") -> tuple[str, str]:
    uid = _pending(email)
    with user_db._conn() as con:
        con.execute("UPDATE users SET enabled = 1, role = ? WHERE id = ?", (role, uid))
        con.commit()
    return uid, user_auth._make_token(uid)


def _exists(uid: str) -> bool:
    return user_db._get_user_unfiltered(uid) is not None


def _audit(tmp_path) -> list[dict]:
    path = tmp_path / "auth_audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _reject(client, uid, headers=None):
    return client.post(f"{API}/users/{uid}/reject", headers=headers or {})


# ── 권한 ─────────────────────────────────────────────────────────────────────


def test_requires_credentials(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    assert _reject(client, uid).status_code == 401
    assert _exists(uid)


@pytest.mark.parametrize("user", ["admin_u", "viewer_u"])
def test_only_owner_may_reject(client, monkeypatch, tmp_path, user):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    assert _reject(client, uid, basic(user)).status_code == 403
    assert _exists(uid)


def test_jwt_admin_and_plain_user_cannot_reject(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    for role in ("admin", "user"):
        _, token = _active(f"{role}@example.com", role)
        r = _reject(client, uid, {"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
    assert _exists(uid)


def test_basic_owner_can_reject(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    r = _reject(client, uid, basic("owner_u"))
    assert r.status_code == 200
    assert r.json() == {"status": "rejected", "user_id": uid}
    assert not _exists(uid)


def test_jwt_owner_can_reject(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    _, token = _active("realowner@example.com", "owner")
    assert _reject(client, uid, {"Authorization": f"Bearer {token}"}).status_code == 200


def test_owner_by_email_can_reject(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "OWNER_EMAILS", config.parse_owner_emails(OWNER_MAIL))
    _, token = _active(OWNER_MAIL)  # 승인된 활성 계정 → OWNER_EMAILS 로 owner
    uid = _pending("squatter@example.com")
    assert _reject(client, uid, {"Authorization": f"Bearer {token}"}).status_code == 200


# ── 안전: 승인된 계정은 지우지 않는다 ────────────────────────────────────────


def test_active_account_cannot_be_deleted(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid, _ = _active("active@example.com")
    r = _reject(client, uid, basic("owner_u"))
    assert r.status_code == 409
    assert _exists(uid)  # 그대로 남아 있다


def test_unknown_user_is_404(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    assert _reject(client, "no-such-id", basic("owner_u")).status_code == 404


def test_reject_twice_second_is_404(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    assert _reject(client, uid, basic("owner_u")).status_code == 200
    assert _reject(client, uid, basic("owner_u")).status_code == 404


def test_other_pending_accounts_are_untouched(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    keep, drop = _pending("keep@example.com"), _pending("drop@example.com")
    _reject(client, drop, basic("owner_u"))
    assert _exists(keep) and not _exists(drop)


# ── 복구: 선점된 이메일을 다시 쓸 수 있다 ────────────────────────────────────


def test_squatted_email_can_be_registered_after_reject(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "OWNER_EMAILS", config.parse_owner_emails(OWNER_MAIL))
    squatter = _pending(OWNER_MAIL)  # 남이 owner 이메일로 먼저 가입
    body = {"email": OWNER_MAIL, "name": "대표", "password": "Pw-demo-12345-xyz"}
    assert client.post(f"{API}/users/signup", json=body).status_code == 409  # 본인은 가입 불가
    assert _reject(client, squatter, basic("owner_u")).status_code == 200
    assert client.post(f"{API}/users/signup", json=body).status_code == 201  # 지운 뒤에는 가능


# ── 감사 로그 ────────────────────────────────────────────────────────────────


def test_audit_records_outcome_and_actor_without_email(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    pending = _pending("secret.person@example.com")
    active, _ = _active("active@example.com")
    _reject(client, pending, basic("owner_u"))
    _reject(client, active, basic("owner_u"))
    _reject(client, "ghost", basic("owner_u"))
    rows = [r for r in _audit(tmp_path) if r["event"] == "reject"]
    assert [r["outcome"] for r in rows] == ["deleted", "not_pending", "not_found"]
    assert all(r["actor_id"] == "owner_u" for r in rows)
    assert rows[0]["target_user_id"] == pending
    assert "secret.person" not in json.dumps(rows)  # 이메일 원문은 남기지 않는다


def test_forbidden_attempt_leaves_no_reject_event(client, monkeypatch, tmp_path):
    enable_basic_auth(monkeypatch, tmp_path)
    uid = _pending("a@example.com")
    _reject(client, uid, basic("admin_u"))
    assert not [r for r in _audit(tmp_path) if r["event"] == "reject"]  # 권한 거절은 라우트에 들어오기 전


# ── 저장소 함수 ──────────────────────────────────────────────────────────────


def test_delete_pending_user_results():
    pending = _pending("a@example.com")
    active, _ = _active("b@example.com")
    assert user_db.delete_pending_user(pending) == "deleted"
    assert user_db.delete_pending_user(pending) == "not_found"
    assert user_db.delete_pending_user(active) == "not_pending"
    assert user_db.delete_pending_user("nope") == "not_found"
