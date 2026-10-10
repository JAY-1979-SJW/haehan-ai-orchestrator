"""데스크톱 owner 부트스트랩(D3 → B안으로 흡수) — 보안 조건을 시험으로 고정한다.

DB 계층(원자 처리·동시성·게이트 매트릭스)은 그대로 두고, 라우터는 desktop_session_router(이름·이메일, 비밀번호 없음)로
옮겼다. 일반 가입(/users/signup)은 데스크톱에서도 더 이상 자동 승인하지 않는다(늘 승인 대기).
조건: ① users 가 완전히 비어 있을 때의 첫 등록만 ② 동시 제출에도 한 명만 ③ 데스크톱 로컬 모드에서만(서버 모드 404)
④ 감사 로그 desktop_setup/desktop_session ⑤ 이행된 기존 users.db 가 있으면 설정 없이 기존 owner 로 자동 세션.
"""

from __future__ import annotations

import json
import threading

import pytest

from ai_orchestrator.auth import auth_audit, user_db
from ai_orchestrator.core import config
from tests.console_api_contract_support import API, make_client
from tools.gates import auth as gate_auth

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
    results: list[tuple[dict | None, bool]] = []
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


# ── 라우터 계층: 일반 가입은 자동 승인하지 않는다 ─────────────────────────────


def _audit_events(tmp_path) -> list[dict]:
    p = tmp_path / "auth_audit.jsonl"
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_regular_signup_is_never_auto_approved_even_on_desktop(monkeypatch):
    _desktop(monkeypatch)
    r = make_client().post(SIGNUP, json=_body(1))
    assert r.status_code == 201 and r.json()["status"] == "pending_approval" and r.json()["user"]["role"] == "user"
    assert user_db.select_desktop_owner() is None


def test_duplicate_email_still_conflicts_on_signup(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert client.post(SIGNUP, json=_body(1)).status_code == 201
    assert client.post(SIGNUP, json=_body(1)).status_code == 409


# ── B안: 첫 실행 설정 · 자동 세션 ──────────────────────────────────────────

AUTH = f"{API}/auth"
H = {"X-Haehan-Desktop": "1"}


def _setup(client, name="홍길동", email="Hong@Example.com"):
    return client.post(f"{AUTH}/desktop-setup", json={"name": name, "email": email}, headers=H)


def test_first_run_setup_creates_exactly_one_owner_and_logs_in(monkeypatch, tmp_path):
    _desktop(monkeypatch)
    client = make_client()
    assert client.get(f"{AUTH}/desktop-setup-status").json() == {"needs_setup": True}
    r = _setup(client)
    assert r.status_code == 201
    body = r.json()
    assert (
        body["user"]["email"] == "hong@example.com"
        and body["user"]["role"] == "owner"
        and body["user"]["name"] == "홍길동"
    )
    assert "password_hash" not in json.dumps(body)
    assert client.get(f"{AUTH}/desktop-setup-status").json() == {"needs_setup": False}
    # 발급된 토큰은 실제로 그 사용자로 인증된다
    me = client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["email"] == "hong@example.com" and me.json()["name"] == "홍길동"
    with user_db._conn() as con:
        rows = con.execute("SELECT role, enabled FROM users").fetchall()
    assert [(r["role"], r["enabled"]) for r in rows] == [("owner", 1)]
    # 감사: actor 는 이메일 그대로(식별 필드), email 필드는 마스킹
    ev = [e for e in _audit_events(tmp_path) if e["event"] == "desktop_setup" and e["outcome"] == "success"]
    assert len(ev) == 1 and ev[0]["actor_id"] == "hong@example.com" and "hong@example.com" not in ev[0]["email"]


def test_setup_has_no_password_path_to_login(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert _setup(client).status_code == 201
    for guess in ("", "password", "hong@example.com", "홍길동"):
        r = client.post(f"{API}/users/login", json={"email": "hong@example.com", "password": guess})
        assert r.status_code == 401


def test_second_setup_conflicts_and_creates_nothing(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert _setup(client).status_code == 201
    r2 = _setup(client, "다른사람", "other@example.com")
    assert r2.status_code == 409
    assert user_db.count_users() == 1  # 승인 대기 계정도 만들지 않는다


def test_concurrent_setup_creates_exactly_one_owner(monkeypatch):
    _desktop(monkeypatch)
    statuses: list[int] = []
    barrier = threading.Barrier(10)

    def worker(i: int) -> None:
        client = make_client()
        barrier.wait()
        statuses.append(_setup(client, f"사람{i}", f"p{i}@example.com").status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert sorted(statuses) == [201] + [409] * 9
    assert user_db.count_users() == 1


def test_setup_validation(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert client.post(f"{AUTH}/desktop-setup", json={"name": "  ", "email": "a@b.co"}, headers=H).status_code == 422
    assert (
        client.post(f"{AUTH}/desktop-setup", json={"name": "A", "email": "not-an-email"}, headers=H).status_code == 422
    )
    assert user_db.count_users() == 0


def test_posts_require_desktop_header(monkeypatch):
    _desktop(monkeypatch)
    client = make_client()
    assert client.post(f"{AUTH}/desktop-setup", json={"name": "A", "email": "a@b.co"}).status_code == 403
    assert client.post(f"{AUTH}/desktop-session").status_code == 403
    assert user_db.count_users() == 0


def test_session_after_restart_reuses_the_owner_and_audits(monkeypatch, tmp_path):
    _desktop(monkeypatch)
    client = make_client()
    setup = _setup(client).json()
    r = client.post(f"{AUTH}/desktop-session", headers=H)  # 앱을 다시 켠 시점
    assert r.status_code == 200
    assert r.json()["user"]["id"] == setup["user"]["id"] and r.json()["token"]
    ev = [e for e in _audit_events(tmp_path) if e["event"] == "desktop_session"]
    assert len(ev) == 1 and ev[0]["actor_id"] == "hong@example.com"


def test_session_on_empty_db_asks_for_setup(monkeypatch):
    _desktop(monkeypatch)
    r = make_client().post(f"{AUTH}/desktop-session", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "needs_setup"


# ── 이행된 기존 DB: 설정 화면 없이 기존 owner 로 자동 세션 ─────────────────────


def _mk(email: str, role: str, enabled: bool, created_at: str | None = None) -> dict:
    user = user_db.create_user(email, email.split("@")[0], "pw-demo-secret-1")
    with user_db._conn() as con:
        con.execute(
            "UPDATE users SET role=?, enabled=?, created_at=COALESCE(?, created_at) WHERE id=?",
            (role, 1 if enabled else 0, created_at, user["id"]),
        )
        con.commit()
    return user


def test_migrated_db_single_owner_gets_session_without_setup(monkeypatch):
    legacy = _mk("old-owner@example.com", "owner", True)
    _mk("staff@example.com", "user", True)
    _desktop(monkeypatch)
    client = make_client()
    assert client.get(f"{AUTH}/desktop-setup-status").json() == {"needs_setup": False}
    r = client.post(f"{AUTH}/desktop-session", headers=H)
    assert r.status_code == 200 and r.json()["user"]["id"] == legacy["id"]
    assert _setup(client).status_code == 409  # 이미 사용자가 있으니 설정 화면 흐름은 막힘


def test_migrated_db_multiple_owners_rule_last_used_then_first_created(monkeypatch):
    a = _mk("a@example.com", "owner", True, "2026-01-01T00:00:00+00:00")
    b = _mk("b@example.com", "owner", True, "2026-02-01T00:00:00+00:00")
    _mk("off@example.com", "owner", False, "2025-01-01T00:00:00+00:00")  # 비활성 owner 는 후보가 아니다
    _desktop(monkeypatch)
    client = make_client()
    # 쓴 기록이 없으면 가장 먼저 만든 활성 owner
    assert client.post(f"{AUTH}/desktop-session", headers=H).json()["user"]["id"] == a["id"]
    # 마지막으로 쓴 계정이 우선 — b 를 쓴 것으로 기록하면 이후 b
    user_db.touch_session(b["id"])
    assert client.post(f"{AUTH}/desktop-session", headers=H).json()["user"]["id"] == b["id"]


def test_users_exist_but_no_active_owner_is_not_silently_promoted(monkeypatch):
    _mk("pending@example.com", "user", False)
    _desktop(monkeypatch)
    client = make_client()
    r = client.post(f"{AUTH}/desktop-session", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "no_active_owner"
    assert _setup(client).status_code == 409
    assert user_db.count_users() == 1


# ── 서버 모드/표지 없음/외부 바인딩: 엔드포인트는 존재하지 않는다(404) ─────────────


@pytest.mark.parametrize("mode", ["server", "no_marker", "public_bind"])
def test_endpoints_are_404_outside_desktop_mode(monkeypatch, mode):
    _desktop(monkeypatch)
    if mode == "server":
        monkeypatch.setattr(config, "AUTH_ENABLED", True)
    elif mode == "no_marker":
        monkeypatch.delenv("HAEHAN_DESKTOP", raising=False)
    else:
        monkeypatch.setattr(config, "APP_HOST", "0.0.0.0")
    client = make_client()
    assert client.get(f"{AUTH}/desktop-setup-status").status_code == 404
    assert _setup(client).status_code == 404
    assert client.post(f"{AUTH}/desktop-session", headers=H).status_code == 404
    assert user_db.count_users() == 0  # 서버에서 누가 owner 를 가져갈 수 없다
