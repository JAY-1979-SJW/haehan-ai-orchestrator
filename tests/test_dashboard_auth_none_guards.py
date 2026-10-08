"""dashboard._require_auth 비-Basic 헤더 처리 + user_db.create_user 조회 실패 시험.

서버 기동 없이 Flask test_request_context / tmp DB 만 사용한다.
"""

from __future__ import annotations

import base64

import pytest

import orchestrator_v1.monitoring.dashboard as dashboard
from ai_orchestrator.auth import user_db

_USER = "tuser"
_PASS = "tpass-fixture"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ORCH_DASHBOARD_USER", _USER)
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", _PASS)


def _call(headers: dict[str, str]):
    app = dashboard.Flask(__name__)
    with app.test_request_context("/", headers=headers):
        return dashboard._require_auth()


def _basic(user: str, pw: str) -> dict[str, str]:
    tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {tok}"}


@pytest.mark.parametrize("hdr", ["Bearer abc123", "Digest foo", "Bearer", "Basic", "Basic !!!notbase64"])
def test_non_basic_header_is_401_not_500(hdr):
    resp = _call({"Authorization": hdr})
    assert resp is not None
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == 'Basic realm="haehan-orchestrator"'


def test_no_header_is_401():
    resp = _call({})
    assert resp is not None and resp.status_code == 401


def test_wrong_basic_credentials_rejected():
    for u, p in ((_USER, "wrong"), ("wrong", _PASS), ("", ""), (_USER, "")):
        resp = _call(_basic(u, p))
        assert resp is not None and resp.status_code == 401


def test_correct_basic_passes():
    assert _call(_basic(_USER, _PASS)) is None


def test_env_unset_is_503_even_with_empty_creds(monkeypatch):
    monkeypatch.delenv("ORCH_DASHBOARD_USER")
    resp = _call({"Authorization": "Bearer x"})
    assert resp is not None and resp.status_code == 503


def test_create_user_lookup_failure_raises_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_INITIALIZED", set())
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "u.db")
    monkeypatch.setattr(user_db, "_get_user_unfiltered", lambda _uid: None)
    with pytest.raises(RuntimeError, match="가입 직후 조회 실패"):
        user_db.create_user("x@example.com", "이름", "password123")


def test_create_user_normal_path_stays_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_INITIALIZED", set())
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "u2.db")
    user = user_db.create_user("y@example.com", "이름", "password123")
    assert user["email"] == "y@example.com"
    assert user["enabled"] == 0
