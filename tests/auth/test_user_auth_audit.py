"""user_auth_router 감사 로그 테스트."""

import importlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.auth import auth_audit, user_db
from ai_orchestrator.core import config

_gauth = None
PW = "Sup3rSecretPw!"
EMAIL = "alice@example.com"


@pytest.fixture
def env(tmp_path, monkeypatch):
    import tools.gates.auth as gauth
    ur = importlib.reload(importlib.import_module("ai_orchestrator.auth.user_auth_router"))
    global _gauth
    _gauth = gauth
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth_audit, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    user_db.init_db()
    app = FastAPI()
    app.include_router(ur.user_auth_router)
    app.dependency_overrides[_gauth.get_current_user] = lambda: {"actor": "adm", "role": "owner"}
    return TestClient(app), app, tmp_path / "audit.jsonl"


def _rows(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _signup(c):
    return c.post("/users/signup", json={"email": EMAIL, "name": "A", "password": PW}).json()["user"]["id"]


def test_login_success_and_fail(env):
    c, _, log = env
    uid = _signup(c)
    assert c.post(f"/users/{uid}/approve").status_code == 200
    assert c.post("/users/login", json={"email": EMAIL, "password": PW}).status_code == 200
    assert c.post("/users/login", json={"email": EMAIL, "password": "wrongwrong"}).status_code == 401
    ev = [(r["event"], r["outcome"]) for r in _rows(log)]
    assert ("login", "success") in ev and ("login", "fail_401") in ev
    assert ("approve", "success") in ev and ("signup", "success") in ev


def test_pending_403_logged(env):
    c, _, log = env
    _signup(c)
    assert c.post("/users/login", json={"email": EMAIL, "password": PW}).status_code == 403
    assert ("login", "pending_403") in [(r["event"], r["outcome"]) for r in _rows(log)]


def test_non_admin_approve_403(env):
    c, app, _ = env
    app.dependency_overrides[_gauth.get_current_user] = lambda: {"actor": "v", "role": "viewer"}
    assert c.post("/users/x/approve").status_code == 403


def test_approve_404_logged(env):
    c, _, log = env
    assert c.post("/users/nope/approve").status_code == 404
    assert ("approve", "not_found") in [(r["event"], r["outcome"]) for r in _rows(log)]


def test_masking(env):
    c, _, log = env
    uid = _signup(c)
    c.post(f"/users/{uid}/approve")
    tok = c.post("/users/login", json={"email": EMAIL, "password": PW}).json()["token"]
    text = log.read_text(encoding="utf-8")
    assert EMAIL not in text and PW not in text and tok not in text
    assert "a***@example.com" in text


def test_audit_failure_does_not_break_login(env, monkeypatch):
    c, _, _ = env
    uid = _signup(c)
    c.post(f"/users/{uid}/approve")
    monkeypatch.setattr(auth_audit, "_get_audit_path", lambda: (_ for _ in ()).throw(OSError("x")))
    assert c.post("/users/login", json={"email": EMAIL, "password": PW}).status_code == 200
