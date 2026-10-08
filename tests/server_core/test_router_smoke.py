import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app
from ai_orchestrator.core import config

client = TestClient(app, raise_server_exceptions=True)

_LOW_RISK_TASK = {
    "task_id": "SMOKE-001",
    "source": "manual",
    "action_type": "read_file",
    "target": "/tmp/smoke.log",  # noqa: S108
    "description": "라우터 스모크 테스트",
    "requested_by": "test",
}


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    """이 스모크 시험은 인증 없이 라우터 연결만 확인한다.

    config.AUTH_ENABLED 기본값은(.env 없을 때) "true" 다(운영 기본값) — 인증 토큰 없이 호출하면
    401 이 되어 이 시험이 원래 확인하려던 "라우팅이 올바른가" 를 가린다. 대상 AUTH_ENABLED=False
    (데스크톱/무인증 모드)로 명시해 인증과 무관하게 라우팅만 검증한다.
    """
    monkeypatch.setattr(config, "AUTH_ENABLED", False)


def test_health_200():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "service" in body


def test_logs_200():
    r = client.get("/api/v1/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_logs_limit_capped():
    """limit=9999 을 넘겨도 500 이하로 클램핑 — 에러 없이 200 반환"""
    r = client.get("/api/v1/logs?limit=9999")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_tasks_post_200():
    r = client.post("/api/v1/tasks", json=_LOW_RISK_TASK)
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == "SMOKE-001"
    assert "status" in body
    assert "risk_level" in body
    assert "allowed" in body


def test_approve_unknown_token_404():
    """존재하지 않는 token_id → 404"""
    r = client.post(
        "/api/v1/tasks/SMOKE-001/approve",
        params={"token_id": "00000000-0000-0000-0000-000000000000"},
        json={"approved_by": "tester"},
    )
    assert r.status_code == 404
