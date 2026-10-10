"""성능 #5/#7 — 인메모리 구조 상한/TTL 시험 (네트워크 없음, 시각은 monkeypatch)."""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors.instagram import instagram_dm_router as igmod
from ai_orchestrator.server import universal_agent_task_api as api


@pytest.fixture(autouse=True)
def _clean():
    api.clear_all()
    igmod._oauth_states.clear()
    yield
    api.clear_all()
    igmod._oauth_states.clear()


def _clock(monkeypatch, mod, start=1000.0):
    box = {"t": start}
    monkeypatch.setattr(mod.time, "time", lambda: box["t"])
    return box


def _new_task():
    return api.create_task(action="open_url", target_url="https://example.com/")["task_id"]


def test_terminal_task_expires_after_ttl(monkeypatch):
    box = _clock(monkeypatch, api)
    tid = _new_task()
    assert api.update_task_result(tid, "COMPLETED", {"data": "ok"}) is True
    assert api.get_task(tid) is not None
    box["t"] += api._TERMINAL_TTL_SEC + 1
    assert api.get_task(tid) is None


def test_terminal_cap_removes_oldest_terminal(monkeypatch):
    box = _clock(monkeypatch, api)
    monkeypatch.setattr(api, "_TERMINAL_MAX", 3)
    ids = []
    for _ in range(5):
        tid = _new_task()
        api.update_task_result(tid, "FAILED")
        ids.append(tid)
        box["t"] += 1
    assert [api.get_task(t) is not None for t in ids] == [False, False, True, True, True]


def test_waiting_and_unknown_status_tasks_are_never_pruned(monkeypatch):
    box = _clock(monkeypatch, api)
    monkeypatch.setattr(api, "_TERMINAL_MAX", 0)
    waiting = _new_task()
    running = _new_task()
    api.update_task_result(running, "RUNNING")
    done = _new_task()
    api.update_task_result(done, "COMPLETED")
    box["t"] += api._TERMINAL_TTL_SEC * 10
    assert api.get_task(done) is None
    assert api.get_task(waiting) is not None
    assert api.get_task(running) is not None
    assert [t["task_id"] for t in api.list_pending_local_agent_tasks()] == [waiting]


def test_oauth_state_ttl_and_cap(monkeypatch):
    box = _clock(monkeypatch, igmod)
    igmod._oauth_state_add("old")
    box["t"] += igmod._OAUTH_STATE_TTL_SEC + 1
    igmod._oauth_state_add("new")
    assert list(igmod._oauth_states) == ["new"]  # 만료분 청소

    monkeypatch.setattr(igmod, "_OAUTH_STATE_MAX", 3)
    for i in range(5):
        igmod._oauth_state_add(f"s{i}")
    assert list(igmod._oauth_states) == ["s2", "s3", "s4"]  # 가장 오래된 것부터 제거


def test_oauth_callback_rejects_expired_state(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    box = _clock(monkeypatch, igmod)
    app = FastAPI()
    app.include_router(igmod.instagram_dm_router)
    client = TestClient(app)
    igmod._oauth_state_add("st")
    box["t"] += igmod._OAUTH_STATE_TTL_SEC + 1
    r = client.get("/instagram-dm/oauth/callback", params={"state": "st", "code": "c"})
    assert r.status_code == 400
    assert "state" in r.json()["detail"]
    r2 = client.get("/instagram-dm/oauth/callback", params={"state": "nope", "code": "c"})
    assert r2.status_code == 400
