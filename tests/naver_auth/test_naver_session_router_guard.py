"""네이버 세션 라우터의 /live·/ensure — 권한, 알 수 없는 계정 거부, out 일 때만 로그인. 브라우저·파이프라인은 가짜."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_auth import session_guard as G
from ai_orchestrator.connectors.naver_auth import session_router as R
from tools.gates.auth import get_current_user

NOW = datetime(2026, 10, 1, 9, 0, 0)


class Fake:
    def __init__(self, state="out", alias="skyjwsin"):
        self.state, self.alias = state, alias
        self.login_calls: list[str] = []
        self.attempts: list[dict] = []
        self.after_login = "in"

    def deps(self):
        def detect():
            current = self.state
            if self.login_calls:
                current = self.after_login
            return {"state": current, "cookie": current == "in"}

        def run_login(target):
            self.login_calls.append(target)
            return {"ok": True, "logged_in": True, "message": "ok"}

        return G.GuardDeps(
            now=lambda: NOW,
            detect=detect,
            read_alias=lambda: self.alias,
            run_login=run_login,
            save_attempt=self.attempts.append,
        )


@pytest.fixture
def api():
    fake = Fake()
    role = {"role": "owner"}
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": role["role"]}
    app.dependency_overrides[R.get_guard_deps] = fake.deps
    return TestClient(app), fake, role


def test_live_is_read_only_and_reports_state_and_account(api):
    client, fake, _ = api
    fake.state = "in"
    body = client.get("/naver/session/live").json()
    assert body["state"] == "in" and body["account"] == "verified" and body["target"] == "skyjwsin"
    assert body["targets"] == ["skyjwshin", "skyjwsin"]  # 화면의 계정 선택 목록(등록된 블로그 계정)
    assert fake.login_calls == []


def test_live_never_logs_in_even_when_logged_out(api):
    client, fake, _ = api
    assert client.get("/naver/session/live").json()["state"] == "out"
    assert fake.login_calls == []


def test_ensure_logs_in_the_default_account_when_logged_out(api):
    client, fake, _ = api
    body = client.post("/naver/session/ensure").json()
    assert fake.login_calls == ["skyjwsin"] and body["action"] == "logged_in"
    assert fake.attempts and fake.attempts[0]["target"] == "skyjwsin"


def test_ensure_uses_the_requested_account(api):
    client, fake, _ = api
    fake.alias = "beautiful-light"
    body = client.post("/naver/session/ensure", json={"username": "skyjwshin"}).json()
    assert fake.login_calls == ["skyjwshin"] and body["account"] == "verified"


@pytest.mark.parametrize("state", ["in", "unavailable"])
def test_ensure_leaves_logged_in_or_unreachable_sessions_alone(api, state):
    client, fake, _ = api
    fake.state = state
    body = client.post("/naver/session/ensure").json()
    assert fake.login_calls == [] and body["action"] == "none"


def test_ensure_with_allow_attempt_false_only_observes(api):
    client, fake, _ = api
    body = client.post("/naver/session/ensure", json={"allow_attempt": False}).json()
    assert fake.login_calls == [] and body["reason"] == "attempt_not_allowed"


def test_second_ensure_logs_in_again_without_throttling(api):
    client, fake, _ = api
    client.post("/naver/session/ensure")
    fake.login_calls.clear()
    fake.after_login = "out"  # 첫 시도 후에도 out 인 상황을 다시 만든다
    fake.state = "out"
    body = client.post("/naver/session/ensure").json()
    assert fake.login_calls != [] and body["action"] != "wait"


@pytest.mark.parametrize("name", ["bigsun2024", "naver", "skyjswin", "../x", ""])
def test_unregistered_accounts_are_rejected_before_anything_runs(api, name):
    client, fake, _ = api
    assert client.post("/naver/session/ensure", json={"username": name}).status_code == 400
    assert client.get("/naver/session/live", params={"target": name}).status_code == 400
    assert fake.login_calls == []


@pytest.mark.parametrize("role", ["viewer", "user", ""])
def test_non_admin_roles_are_rejected(api, role):
    client, fake, state = api
    state["role"] = role
    assert client.get("/naver/session/live").status_code == 403
    assert client.post("/naver/session/ensure").status_code == 403
    assert fake.login_calls == []


def test_existing_endpoints_are_still_registered():
    """기존 호출자 보호: /login·/status 등은 그대로 있어야 한다."""
    app = FastAPI()
    app.include_router(R.router)
    paths = app.openapi()["paths"]
    for suffix in ("/sessions", "/status", "/accounts", "/login", "/live", "/ensure"):
        assert f"/naver/session{suffix}" in paths, suffix
    assert set(paths["/naver/session/live"]) == {"get"} and set(paths["/naver/session/ensure"]) == {"post"}


def test_main_router_still_includes_the_session_router():
    from ai_orchestrator.routers.registry import router

    app = FastAPI()
    app.include_router(router)
    assert "/api/v1/naver/session/ensure" in app.openapi()["paths"]
