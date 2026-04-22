import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from fastapi.testclient import TestClient
from ai_orchestrator.server import app

client = TestClient(app, raise_server_exceptions=True)

_LOW_RISK_TASK = {
    "task_id": "SMOKE-001",
    "source": "manual",
    "action_type": "read_file",
    "target": "/tmp/smoke.log",
    "description": "라우터 스모크 테스트",
    "requested_by": "test",
}


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
