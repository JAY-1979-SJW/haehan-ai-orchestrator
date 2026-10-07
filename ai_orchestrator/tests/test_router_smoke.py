import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app

client = TestClient(app, raise_server_exceptions=True)

_LOW_RISK_TASK = {
    "task_id": "SMOKE-001",
    "source": "manual",
    "action_type": "read_file",
    "target": "/tmp/smoke.log",  # noqa: S108
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


def test_health_instance_id_null_when_unset(monkeypatch):
    monkeypatch.delenv("HAEHAN_INSTANCE_ID", raising=False)
    body = client.get("/api/v1/health").json()
    assert body["instance_id"] is None
    assert body["status"] == "ok"  # 기존 필드 유지(하위 호환)


def test_health_instance_id_echoes_app_token(monkeypatch):
    monkeypatch.setenv("HAEHAN_INSTANCE_ID", "0123456789abcdef0123456789abcdef")
    assert client.get("/api/v1/health").json()["instance_id"] == "0123456789abcdef0123456789abcdef"


def test_health_instance_id_rejects_malformed(monkeypatch):
    monkeypatch.setenv("HAEHAN_INSTANCE_ID", "bad value; <script>")
    assert client.get("/api/v1/health").json()["instance_id"] is None


def test_parent_watchdog_fires_when_parent_gone(monkeypatch):
    import subprocess
    import threading

    from ai_orchestrator.server import desktop_entry

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()  # 이미 끝난 PID = 사라진 부모
    monkeypatch.setenv("HAEHAN_PARENT_PID", str(child.pid))
    fired = threading.Event()
    t = desktop_entry.start_parent_watchdog(poll_seconds=0.05, on_gone=fired.set)
    assert t is not None
    assert fired.wait(5)


def test_parent_watchdog_off_without_env(monkeypatch):
    from ai_orchestrator.server import desktop_entry

    monkeypatch.delenv("HAEHAN_PARENT_PID", raising=False)
    assert desktop_entry.start_parent_watchdog() is None
