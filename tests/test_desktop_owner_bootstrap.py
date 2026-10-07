"""데스크톱 첫 가입자 자동 owner 승인(D3, 대표님 결정 A안) — 보안 조건을 시험으로 고정한다.

조건: ① users 가 완전히 비어 있을 때의 첫 가입만 ② 동시 가입에도 한 명만 ③ 데스크톱 로컬 모드에서만(서버 모드 꺼짐)
④ 감사 로그 bootstrap_owner ⑤ 예전 users.db 가 이행돼 비어 있지 않으면 일어나지 않음.
"""

from __future__ import annotations

import json
import threading

import pytest

from ai_orchestrator import config
from ai_orchestrator.gates import auth as gate_auth
from ai_orchestrator.persistence import auth_audit, user_db
from tests.console_api_contract_support import API, make_client

SIGNUP = f"{API}/users/signup"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_get_db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: tmp_path / "auth_audit.jsonl")
    monkeypatch.delenv("HAEHAN_DESKTOP", raising=False)


def _desktop(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    monkeypatch.setattr(config, "APP_HOST", "127.0.0.1")
    monkeypatch.setenv("HAEHAN_DESKTOP", "1")


def _body(n: int = 1) -> dict:
    return {"email": f"user{n}@example.com", "name": f"사용자{n}", "password": "pw-demo-secret-1"}


# ── 게이트 판정 매트릭스: 세 조건이 모두 맞아야만 켜진다 ──────────────────


@pytest.mark.parametrize(
    ("auth_enabled", "desktop_env", "host", "allowed"),
    [
        (False, "1", "127.0.0.1", True),
        (False, "1", "localhost", True),
        (True, "1", "127.0.0.1", False),  # 서버 모드(AUTH_ENABLED=true) — 꺼짐
        (False, "", "127.0.0.1", False),  # 데스크톱 표지 없음 — 꺼짐
        (False, "0", "127.0.0.1", False),
        (False, "1", "0.0.0.0", False),  # 외부에 열린 바인딩 — 꺼짐
        (True, "", "0.0.0.0", False),
    ],
)
def test_gate_matrix(monkeypatch, auth_enabled, desktop_env, host, allowed):
    monkeypatch.setattr(config, "AUTH_ENABLED", auth_enabled)
    monkeypatch.setattr(config, "APP_HOST", host)
    if desktop_env:
        monkeypatch.setenv("HAEHAN_DESKTOP", desktop_env)
    assert gate_auth.desktop_owner_bootstrap_allowed() is allowed


# ── DB 계층 ──────────────────────────────────────────────────────────────


def test_first_user_becomes_owner_second_stays_pending():
    first, boot1 = user_db.create_user_bootstrapping("a@example.com", "A", "pw-demo-secret-1", allow_bootstrap=True)
    second, boot2 = user_db.create_user_bootstrapping("b@example.com", "B", "pw-demo-secret-1", allow_bootstrap=True)
    assert boot1 is True and first["role"] == "owner" and first["enabled"] == 1
    assert boot2 is False and second["role"] == "user" and second["enabled"] == 0


def test_not_allowed_means_pending_even_when_empty():
    user, boot = user_db.create_user_bootstrapping("a@example.com", "A", "pw-demo-secret-1", allow_bootstrap=False)
    assert boot is False and user["role"] == "user" and user["enabled"] == 0


def test_existing_pending_user_blocks_bootstrap():
    """비어 있지 않으면(승인 대기 계정 하나라도 있으면) 부트스트랩이 일어나지 않는다."""
    user_db.create_user("old@example.com", "옛", "pw-demo-secret-1")  # enabled=0 로 존재
    user, boot = user_db.create_user_bootstrapping("new@example.com", "새", "pw-demo-secret-1", allow_bootstrap=True)
    assert boot is False and user["enabled"] == 0


def test_concurrent_signups_make_exactly_one_owner():
    results: list[tuple[dict, bool]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(12)

    def worker(i: int) -> None:
        try:
            barrier.wait()
            results.append(
                user_db.create_user_bootstrapping(
                    f"c{i}@example.com", f"C{i}", "pw-demo-secret-1", allow_bootstrap=True
                )
            )
        except BaseException as exc:  # noqa: BLE001 - 시험: 어떤 예외든 수집해 아래에서 단언
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors
    assert len(results) == 12
    owners = [u for u, boot in results if boot]
    assert len(owners) == 1
    with user_db._conn() as con:
        rows = con.execute("SELECT role, enabled FROM users").fetchall()
    assert sorted((r["role"], r["enabled"]) for r in rows) == [("owner", 1)] + [("user", 0)] * 11


# ── 라우터 계층: 응답·감사 로그·모드 ─────────────────────────────────────────


def _audit_events(tmp_path) -> list[dict]:
    p = tmp_path / "auth_audit.jsonl"
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_desktop_first_signup_is_approved_and_audited(monkeypatch, tmp_path):
    _desktop(monkeypatch)
    client = make_client()
    r = client.post(SIGNUP, json=_body(1))
    assert r.status_code == 201
    assert r.json()["status"] == "approved" and r.json()["user"]["role"] == "owner"
    # 바로 로그인 가능(승인 대기가 아님)
    login = client.post(f"{API}/users/login", json={"email": "user1@example.com", "password": "pw-demo-secret-1"})
    assert login.status_code == 200 and login.json()["user"]["role"] == "owner"
    events = _audit_events(tmp_path)
    boot = [e for e in events if e["outcome"] == "bootstrap_owner"]
    assert len(boot) == 1 and boot[0]["event"] == "signup" and boot[0]["actor_id"] == r.json()["user"]["id"]
    assert "user1@example.com" not in json.dumps(boot[0])  # 이메일은 마스킹


def test_desktop_second_signup_pending(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert client.post(SIGNUP, json=_body(1)).json()["status"] == "approved"
    r2 = client.post(SIGNUP, json=_body(2))
    assert r2.status_code == 201 and r2.json()["status"] == "pending_approval"
    login = client.post(f"{API}/users/login", json={"email": "user2@example.com", "password": "pw-demo-secret-1"})
    assert login.status_code != 200


def test_server_mode_first_signup_stays_pending_and_not_audited(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)  # 서버 모드
    monkeypatch.setenv("HAEHAN_DESKTOP", "1")  # 표지가 있어도 서버(AUTH_ENABLED=true)에서는 꺼짐
    r = make_client().post(SIGNUP, json=_body(1))
    assert r.status_code == 201 and r.json()["status"] == "pending_approval" and r.json()["user"]["role"] == "user"
    assert not [e for e in _audit_events(tmp_path) if e["outcome"] == "bootstrap_owner"]


def test_auth_disabled_without_desktop_marker_stays_pending(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)  # 개발 환경 등
    r = make_client().post(SIGNUP, json=_body(1))
    assert r.json()["status"] == "pending_approval"


def test_migrated_users_db_prevents_bootstrap(monkeypatch):
    """예전 번들의 users.db 가 이행돼 계정이 있으면(승인 완료 계정이든 아니든) 자동 승인은 일어나지 않는다."""
    legacy = user_db.create_user("owner-old@example.com", "예전 소유자", "pw-demo-secret-1")
    assert user_db.approve_user(legacy["id"])
    _desktop(monkeypatch)
    r = make_client().post(SIGNUP, json=_body(1))
    assert r.json()["status"] == "pending_approval" and r.json()["user"]["role"] == "user"


def test_duplicate_email_still_conflicts(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert client.post(SIGNUP, json=_body(1)).status_code == 201
    assert client.post(SIGNUP, json=_body(1)).status_code == 409
