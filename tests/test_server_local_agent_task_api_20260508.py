"""서버 로컬 에이전트 task API 테스트"""

from __future__ import annotations

import pytest

from ai_orchestrator.contracts.local_task_protocol import STATUS_COMPLETED, build_result
from ai_orchestrator.server.local_agent_task_api import (
    create_local_browser_task,
    get_pending_local_agent_task,
    get_task_status,
    mark_task_assigned,
    receive_local_agent_result,
    sanitize_task_for_local_agent,
)
from ai_orchestrator.server.task_queue_schema import (
    TASK_STATE_ASSIGNED,
    TASK_STATE_PENDING,
    clear_store,
)


def setup_function():
    clear_store()


# ── create_local_browser_task ──────────────────────────────────────────────────


def test_create_task_basic():
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr/notice")
    assert r["task_id"]
    assert r["state"] == TASK_STATE_PENDING


def test_create_task_no_sensitive_fields():
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    payload = r["payload"]
    for f in ("cookie", "session", "password", "otp", "token"):
        assert f not in payload


def test_create_task_server_does_not_open_browser():
    """서버가 외부 URL을 직접 열지 않음을 verify."""
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr/notice")
    # task record만 생성되고 실행 없음
    assert r["state"] == TASK_STATE_PENDING
    assert r.get("result") is None


def test_create_task_invalid_action():
    with pytest.raises(ValueError):
        create_local_browser_task("auto_bid_submit", "https://www.g2b.go.kr")


# ── get_pending_local_agent_task ───────────────────────────────────────────────


def test_get_pending_returns_tasks():
    create_local_browser_task("open_url", "https://www.g2b.go.kr")
    tasks = get_pending_local_agent_task()
    assert len(tasks) >= 1


def test_get_pending_task_payload_safe():
    create_local_browser_task("read_page", "https://www.g2b.go.kr")
    tasks = get_pending_local_agent_task()
    for t in tasks:
        for f in ("cookie", "session", "password", "otp"):
            assert f not in t.get("payload", {})


# ── mark_task_assigned ─────────────────────────────────────────────────────────


def test_mark_assigned():
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    ok = mark_task_assigned(r["task_id"])
    assert ok is True
    status = get_task_status(r["task_id"])
    assert status["state"] == TASK_STATE_ASSIGNED


# ── receive_local_agent_result ─────────────────────────────────────────────────


def test_receive_result_accepted():
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    tid = r["task_id"]
    result = build_result(tid, True, STATUS_COMPLETED, title_hint="공고")
    resp = receive_local_agent_result(tid, result)
    assert resp["accepted"] is True


def test_receive_result_sensitive_blocked():
    r = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    tid = r["task_id"]
    bad_result = build_result(tid, True, STATUS_COMPLETED)
    bad_result["cookie"] = "sess=abc"
    resp = receive_local_agent_result(tid, bad_result)
    assert resp["accepted"] is False
    assert resp["block_reason"]


# ── sanitize_task_for_local_agent ─────────────────────────────────────────────


def test_sanitize_task_clean():
    from ai_orchestrator.contracts.local_task_protocol import build_task

    t = build_task("open_url", "https://www.g2b.go.kr")
    safe = sanitize_task_for_local_agent(t)
    assert safe["action"] == "open_url"


def test_sanitize_task_with_forbidden_raises():
    from ai_orchestrator.contracts.local_task_protocol import build_task

    t = build_task("open_url", "https://www.g2b.go.kr")
    t["cookie"] = "abc"
    with pytest.raises(ValueError):
        sanitize_task_for_local_agent(t)
