"""앱 AI 에이전트 작업 분배 P1 — 로컬 에이전트 동시 실행 (기준서 2026-10-02_app_agent_dispatch).

실제 서버·브라우저·claude 를 쓰지 않고 가짜 ws / 가짜 process_task(sleep)로 검증한다.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from ai_orchestrator.agent_hub.registry import agent as reg_agent
from ai_orchestrator.agent_hub.router import ws as server_ws
from core.agent_runtime.connection import websocket_client as client


class FakeClientWS:
    """recv 큐 + send 기록. running 을 받으면 running_ack 를 큐에 돌려준다(서버 흉내)."""

    def __init__(self, tasks: list[dict], *, serial_server: bool = False, auto_ack: bool = True):
        self.q: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.auto_ack = auto_ack
        self.backlog = list(tasks) if serial_server else []
        for t in [] if serial_server else tasks:
            self.q.put_nowait(json.dumps({"type": "task", "task": t}))
        if serial_server and self.backlog:
            self._push_next()

    def _push_next(self):
        if self.backlog:
            self.q.put_nowait(json.dumps({"type": "task", "task": self.backlog.pop(0)}))

    async def recv(self):
        item = await self.q.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send(self, raw: str):
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg["type"] == "result":
            self._push_next()
        if msg["type"] == "running" and self.auto_ack:
            self.q.put_nowait(json.dumps({"type": "running_ack", "task_id": msg["task_id"]}))


async def _drive(parallel: bool, n: int, work_sec: float) -> tuple[float, list[dict]]:
    ws = FakeClientWS([{"task_id": f"t{i}"} for i in range(n)], serial_server=not parallel)

    def fake_process(task: dict) -> dict:
        time.sleep(work_sec)
        return {"type": "result", "task_id": task["task_id"], "success": True}

    orig = client.process_task
    client.process_task = fake_process
    started = time.monotonic()
    loop_task = asyncio.create_task(client._message_loop(ws, "ag", 5, parallel, {}, set()))
    try:
        while sum(1 for m in ws.sent if m["type"] == "result") < n:
            await asyncio.sleep(0.02)
            assert time.monotonic() - started < 10
        elapsed = time.monotonic() - started
    finally:
        client.process_task = orig
        loop_task.cancel()
    return elapsed, ws.sent


def test_parallel_runs_tasks_concurrently():
    elapsed, sent = asyncio.run(_drive(True, 3, 0.4))
    assert elapsed < 0.9  # 직렬이면 1.2초 이상
    assert {m["task_id"] for m in sent if m["type"] == "result"} == {"t0", "t1", "t2"}


def test_serial_mode_unchanged():
    elapsed, sent = asyncio.run(_drive(False, 2, 0.3))
    assert elapsed >= 0.6
    types = [m["type"] for m in sent]
    assert types == ["running", "result", "running", "result"]


def test_running_error_gives_up_without_executing():
    async def run() -> list[str]:
        ws = FakeClientWS([], auto_ack=False)
        ran: list[str] = []
        orig = client.process_task
        client.process_task = lambda t: ran.append(t["task_id"]) or {"type": "result", "task_id": t["task_id"]}  # type: ignore[assignment,func-returns-value]
        loop_task = asyncio.create_task(client._message_loop(ws, "ag", 5, True, {}, set()))
        try:
            ws.q.put_nowait(json.dumps({"type": "task", "task": {"task_id": "bad"}}))
            await asyncio.sleep(0.1)
            # 서버가 running_ack 대신 TASK_NOT_FOUND 로 응답 → 실행하지 않아야 함
            ws.q.put_nowait(json.dumps({"type": "error", "error": "TASK_NOT_FOUND", "task_id": "bad"}))
            await asyncio.sleep(0.2)
        finally:
            client.process_task = orig
            loop_task.cancel()
        return ran

    assert asyncio.run(run()) == []


def test_max_parallel_clamped(monkeypatch):
    monkeypatch.setattr(client.config, "MAX_PARALLEL", 99, raising=False)
    assert client._max_parallel() == 3
    monkeypatch.setattr(client.config, "MAX_PARALLEL", 0, raising=False)
    assert client._max_parallel() == 1


@pytest.mark.parametrize(
    ("given", "expected"),
    [(None, 1), ("x", 1), (0, 1), (1, 1), (2, 2), (3, 3), (9, 3), (-5, 1), ("2", 2)],
)
def test_server_capacity_clamp(given, expected):
    assert reg_agent.set_agent_capacity("cap-test", given) == expected
    assert reg_agent.get_agent_capacity("cap-test") == expected
    reg_agent.clear_agent_capacity("cap-test")
    assert reg_agent.get_agent_capacity("cap-test") == 1


class FakeServerWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data: dict):
        self.sent.append(data)


def _patch_push(monkeypatch, capacity: int, active: int, pending: int):
    tasks = [SimpleNamespace(task_id=f"q{i}") for i in range(pending)]
    monkeypatch.setattr(server_ws._reg, "get_agent_capacity", lambda _a: capacity)
    monkeypatch.setattr(server_ws._reg, "get_active_task_count", lambda _a: active)
    monkeypatch.setattr(server_ws._reg, "list_pending_for_agent", lambda _a: tasks)
    monkeypatch.setattr(
        server_ws._reg,
        "mark_delivered",
        lambda _a, tid: SimpleNamespace(
            status="delivered",
            task_id=tid,
            risk_level="low",
            action="run_claude_agent",
            to_dispatch=lambda: {"task_id": tid},
        ),
    )


@pytest.mark.parametrize(
    ("capacity", "active", "pending", "expected_sent"),
    [(1, 0, 3, 1), (1, 1, 3, 0), (2, 0, 3, 2), (2, 1, 3, 1), (3, 3, 3, 0), (3, 1, 1, 1)],
)
def test_push_queued_respects_capacity(monkeypatch, capacity, active, pending, expected_sent):
    _patch_push(monkeypatch, capacity, active, pending)
    ws = FakeServerWS()
    assert asyncio.run(server_ws._push_queued(ws, "ag")) == expected_sent
    assert len(ws.sent) == expected_sent
