"""AI 에이전트 작업 분배 P3 — 라우터(HTTP) 시험: 관리자 전용·승인 흐름. 가짜 큐 + 임시 DB."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.agent_dispatch import agent_dispatch_router as router_mod
from ai_orchestrator.agent_dispatch import agent_dispatch_service as svc
from ai_orchestrator.agent_dispatch import agent_dispatch_store as store
from tests.site_work.test_agent_dispatch_service import FakeReg, T, plan_json
from tools.gates.auth import get_current_user


def _as(role: str) -> TestClient:
    app = FastAPI()
    app.include_router(router_mod.agent_dispatch_router)
    app.dependency_overrides[get_current_user] = lambda: {"role": role, "actor": f"{role}-user"}
    return TestClient(app)


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "dispatch.db")
    fake = FakeReg()
    monkeypatch.setattr(svc, "_reg", fake)
    monkeypatch.setattr(svc, "_low_memory", lambda: False)
    started: list[bool] = []
    monkeypatch.setattr(router_mod.runner, "ensure_running", lambda: started.append(True) or True)
    fake.runner_started = started
    return fake


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_non_admin_forbidden_everywhere(reg, role):
    c = _as(role)
    did = "0" * 32
    calls = [
        c.post("/ai-agent/dispatch", json={"goal": "x"}),
        c.get("/ai-agent/dispatch"),
        c.get(f"/ai-agent/dispatch/{did}"),
        c.post(f"/ai-agent/dispatch/{did}/approve"),
        c.post(f"/ai-agent/dispatch/{did}/cancel"),
    ]
    assert [r.status_code for r in calls] == [403] * 5
    assert reg.enqueued == []  # 거부된 요청은 아무 작업도 큐에 넣지 않는다


def test_admin_flow_create_view_approve_cancel(reg):
    c = _as("admin")
    r = c.post("/ai-agent/dispatch", json={"goal": "점검", "max_parallel": 3})
    assert r.status_code == 200
    did = r.json()["id"]

    assert c.get(f"/ai-agent/dispatch/{did}").json()["status"] == "planning"
    assert c.post(f"/ai-agent/dispatch/{did}/approve").status_code == 400  # 계획 중 승인 불가

    reg.finish(reg.enqueued[0]["task_id"], plan_json(T("a"), T("b")))
    d = c.get(f"/ai-agent/dispatch/{did}").json()
    assert d["status"] == "proposed" and d["waves"] == [["a", "b"]] and d["max_parallel"] == 3
    assert reg.runner_started == []  # 승인 전에는 러너를 띄우지 않는다

    assert c.post(f"/ai-agent/dispatch/{did}/approve").json()["status"] == "running"
    assert reg.runner_started == [True]
    assert c.post(f"/ai-agent/dispatch/{did}/approve").status_code == 400  # 중복 승인 불가

    assert c.post(f"/ai-agent/dispatch/{did}/cancel").json()["status"] == "cancelled"
    assert [i["id"] for i in c.get("/ai-agent/dispatch").json()["items"]] == [did]


def test_validation_and_not_found(reg):
    c = _as("owner")
    assert c.post("/ai-agent/dispatch", json={"goal": "  "}).status_code == 400
    assert c.get(f"/ai-agent/dispatch/{'1' * 32}").status_code == 404
    assert c.get("/ai-agent/dispatch/not-a-valid-id").status_code == 422


def test_runner_ticks_running_dispatches_and_stops_when_idle(monkeypatch):
    from ai_orchestrator.agent_dispatch import agent_dispatch_runner as runner

    monkeypatch.setattr(runner, "TICK_INTERVAL_SEC", 0.01)
    queue = [["d1"], ["d1", "d2"], [], []]  # 마지막 []는 두 번째 기동용
    ticked: list[str] = []
    monkeypatch.setattr(runner.store, "running_dispatch_ids", lambda: queue.pop(0))

    def fake_tick(did):
        ticked.append(did)
        if did == "d1" and len(ticked) == 1:
            raise RuntimeError("한 분배안 오류가 러너를 멈추면 안 된다")

    monkeypatch.setattr(runner.service, "tick", fake_tick)
    monkeypatch.setattr(runner, "_thread", None)
    assert runner.ensure_running() is True
    runner._thread.join(timeout=5)
    assert not runner._thread.is_alive()
    assert ticked == ["d1", "d1", "d2"]
    assert runner.ensure_running() is True  # 끝난 뒤에는 다시 띄울 수 있다
    runner._thread.join(timeout=5)
