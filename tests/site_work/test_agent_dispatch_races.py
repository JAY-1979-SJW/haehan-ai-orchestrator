"""AI 에이전트 작업 분배 — 적대적 검증(2026-10-02)에서 재현된 경쟁·실패 시나리오 회귀 시험.

취소와 tick 의 경쟁, 오래된 스냅샷 덮어쓰기, 큐 등록 뒤 기록 실패에 의한 이중 큐잉, 시작 중 끊김,
분배 전체 시간 초과, 러너 수명을 가짜 큐 + 임시 DB 로 검증한다.
"""

from __future__ import annotations

import threading
import time

import pytest

from ai_orchestrator.agent_dispatch import agent_dispatch_policy as pol
from ai_orchestrator.agent_dispatch import agent_dispatch_store as store
from ai_orchestrator.agent_dispatch import agent_dispatch_service as svc
from ai_orchestrator.agent_dispatch import agent_dispatch_runner as runner
from tests.site_work.test_agent_dispatch_service import FakeReg, T, make_proposed


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "dispatch.db")
    reg = FakeReg()
    monkeypatch.setattr(svc, "_reg", reg)
    monkeypatch.setattr(svc, "_low_memory", lambda: False)
    return reg


def states(did):
    return {t["tid"]: t["state"] for t in svc.view(did)["subtasks"]}


# ── 취소 ↔ tick 경쟁 ─────────────────────────────────────────────────────
def test_cancel_during_tick_cancels_what_the_tick_started(env):
    """리뷰어 재현: tick 도중 취소가 끼면 분배안은 cancelled 인데 큐 작업이 새로 등록되고 취소 요청은 0건이었다."""
    did = make_proposed(env, T("a"), T("b"))
    svc.approve(did, "admin")
    cancel_thread: list[threading.Thread] = []
    original = env.get_agent_capacity

    def hook(agent_id):
        if not cancel_thread:  # tick 이 락을 잡은 채 시작 직전인 시점에 취소 요청이 들어온다
            t = threading.Thread(target=lambda: svc.cancel(did, "admin"))
            cancel_thread.append(t)
            t.start()
            time.sleep(0.2)  # 취소가 락 앞에서 기다리게 한다
        return original(agent_id)

    env.get_agent_capacity = hook
    svc.tick(did)
    cancel_thread[0].join(timeout=10)

    assert svc.view(did)["status"] == store.CANCELLED
    started = [e["task_id"] for e in env.enqueued[1:]]
    assert started and set(env.cancelled) == set(started)  # tick 이 시작한 작업은 모두 취소 요청됨
    assert set(states(did).values()) == {pol.SKIPPED}
    assert svc.tick(did) == store.CANCELLED


def test_stale_snapshot_cannot_overwrite_skipped_state(env):
    """리뷰어 재현: 오래된 스냅샷으로 skipped 가 done 으로 덮였다(취소 후 상태 ['done'])."""
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")
    svc.tick(did)
    stale = store.get_dispatch(did)["subtasks"]  # a 가 running 이던 시점의 스냅샷
    svc.cancel(did, "admin")
    env.finish(env.enqueued[1]["task_id"], "늦게 도착한 결과")
    svc._sync_running(did, stale)
    assert states(did) == {"a": pol.SKIPPED}


def test_claim_is_refused_in_cancelled_dispatch(env):
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")
    sub = store.get_dispatch(did)["subtasks"][0]
    svc.cancel(did, "admin")
    before = len(env.enqueued)
    assert store.claim_subtask(did, "a") is False
    svc._start_subtask(did, sub, {"a": sub}, "ag1")
    assert len(env.enqueued) == before  # 취소된 분배안에서는 큐에 넣지 않는다


def test_claim_only_from_pending_and_only_when_running(env):
    did = make_proposed(env, T("a"))
    assert store.claim_subtask(did, "a") is False  # 아직 proposed(미승인)
    svc.approve(did, "admin")
    assert store.claim_subtask(did, "a") is True
    assert store.claim_subtask(did, "a") is False  # 두 번 선점 불가


# ── 이중 큐잉 ───────────────────────────────────────────────────────────
def test_no_double_enqueue_when_recording_fails(env, monkeypatch):
    """리뷰어 재현: 큐 등록 직후 기록이 실패하면 같은 하위 작업이 다음 tick 에서 다시 큐에 들어갔다."""
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")

    def boom(*_a, **_k):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(store, "mark_subtask_running", boom)
    svc.tick(did)
    assert len(env.enqueued) == 2  # 계획 1 + 하위 1
    assert env.cancelled == [env.enqueued[1]["task_id"]]  # 고아가 된 큐 작업은 취소 요청
    assert states(did) == {"a": pol.FAILED}
    monkeypatch.undo()
    svc.tick(did)
    assert len(env.enqueued) == 2  # 재큐잉 없음


def test_enqueue_failure_marks_failed_without_retry(env, monkeypatch):
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")
    calls = []

    def fail_enqueue(**kw):
        calls.append(kw)
        raise RuntimeError("queue down")

    monkeypatch.setattr(env, "enqueue_task", fail_enqueue)
    svc.tick(did)
    svc.tick(did)
    assert len(calls) == 1 and states(did) == {"a": pol.FAILED}


def test_stale_starting_is_failed_not_retried(env):
    """시작 선점 뒤 프로세스가 끊긴 경우: 비용 중복을 피하려고 재시도하지 않고 실패 처리."""
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")
    assert store.claim_subtask(did, "a")
    before = len(env.enqueued)
    svc.tick(did)
    assert states(did) == {"a": pol.FAILED}
    assert len(env.enqueued) == before
    assert svc.view(did)["status"] == store.FAILED


def test_starting_counts_as_active_for_scheduling():
    tasks = [
        {"id": "a", "read_only": False, "resources": ["path:C:/x"], "depends_on": []},
        {"id": "b", "read_only": False, "resources": ["path:C:/x"], "depends_on": []},
        {"id": "c", "read_only": False, "resources": ["path:C:/y"], "depends_on": []},
    ]
    start, _ = pol.next_step(tasks, {"a": pol.STARTING}, max_parallel=2)
    assert start == ["c"]  # a 가 시작 중이면 같은 경로의 b 는 대기, 한도 2 중 1칸 사용


# ── 전체 시간 초과 ──────────────────────────────────────────────────────
def test_dispatch_timeout_stops_everything(env, monkeypatch):
    did = make_proposed(env, T("a"), T("b"))
    svc.approve(did, "admin")
    svc.tick(did)
    started = {e["task_id"] for e in env.enqueued[1:]}
    monkeypatch.setattr(svc, "DISPATCH_TIMEOUT_SEC", -1)
    assert svc.tick(did) == store.FAILED
    d = svc.view(did)
    assert "시간 초과" in d["note"] and set(env.cancelled) == started
    assert set(states(did).values()) == {pol.SKIPPED}


def test_timeout_not_triggered_normally(env):
    did = make_proposed(env, T("a"))
    svc.approve(did, "admin")
    assert svc.tick(did) == store.RUNNING
    assert svc._timed_out({"approved_at": None}) is False
    assert svc._timed_out({"approved_at": "깨진 값"}) is False


# ── 러너 ────────────────────────────────────────────────────────────────
def test_runner_survives_storage_errors(monkeypatch):
    monkeypatch.setattr(runner, "TICK_INTERVAL_SEC", 0.01)
    answers = [RuntimeError("locked"), RuntimeError("locked"), ["d1"], []]
    ticked: list[str] = []

    def fake_ids():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(runner.store, "running_dispatch_ids", fake_ids)
    monkeypatch.setattr(runner.service, "tick", lambda did: ticked.append(did))
    monkeypatch.setattr(runner, "_thread", None)
    assert runner.ensure_running() is True
    runner._thread.join(timeout=5)
    assert ticked == ["d1"] and not runner._thread.is_alive()  # 오류 두 번을 넘기고 정상 진행


def test_runner_gives_up_after_persistent_storage_errors(monkeypatch):
    monkeypatch.setattr(runner, "TICK_INTERVAL_SEC", 0.001)
    monkeypatch.setattr(runner, "MAX_CONSECUTIVE_DB_ERRORS", 3)
    calls = []

    def always_fail():
        calls.append(1)
        raise RuntimeError("locked")

    monkeypatch.setattr(runner.store, "running_dispatch_ids", always_fail)
    monkeypatch.setattr(runner, "_thread", None)
    runner.ensure_running()
    runner._thread.join(timeout=5)
    assert len(calls) == 3 and not runner._thread.is_alive()  # 무한 반복하지 않고 끝남(다음 조회 때 재시작)


def test_resume_running_starts_runner_only_when_needed(monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(runner, "ensure_running", lambda: started.append(True) or True)
    monkeypatch.setattr(runner.store, "running_dispatch_ids", lambda: [])
    assert runner.resume_running() is False and started == []
    monkeypatch.setattr(runner.store, "running_dispatch_ids", lambda: ["d1"])
    assert runner.resume_running() is True and started == [True]
    monkeypatch.setattr(runner.store, "running_dispatch_ids", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert runner.resume_running() is False  # 저장소 오류는 재개 실패일 뿐 예외로 번지지 않는다


def test_server_startup_resume_never_blocks_boot(monkeypatch):
    import importlib.util
    from pathlib import Path

    import ai_orchestrator

    # server.py 는 asgi.py 로 옮겨졌다(패키지 server/ 와의 이름 충돌 해소) — 실제 진입점 파일을 같은 방식으로 불러온다.
    path = Path(ai_orchestrator.__file__).parent / "asgi.py"
    spec = importlib.util.spec_from_file_location("ai_orchestrator._server_module_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def boom():
        raise RuntimeError("resume failed")

    monkeypatch.setattr(runner, "resume_running", boom)
    module._resume_agent_dispatch()  # 예외 없이 끝나야 한다(기동을 막지 않음)
    assert module._start_user_job_loops.__doc__  # 래퍼가 존재하고 lifespan 이 이를 호출한다
    assert "_start_user_job_loops()" in path.read_text(encoding="utf-8")
