"""로컬 에이전트 task client 테스트"""

from __future__ import annotations

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
)
from ai_orchestrator.server.local_agent_task_api import create_local_browser_task
from ai_orchestrator.server.task_queue_schema import clear_store
from core.agent_runtime.runtime.task_client import poll_and_run_once


def _dummy_runner_ok(task):
    from ai_orchestrator.contracts.local_task_protocol import STATUS_COMPLETED, build_result

    return build_result(
        task_id=task["task_id"],
        ok=True,
        status=STATUS_COMPLETED,
        current_url_host="www.g2b.go.kr",
        title_hint="공고 목록",
        message_ko="완료",
    )


def _dummy_runner_fail(task):
    raise RuntimeError("network_error")


def setup_function():
    clear_store()


# TC-1: pending task 없으면 None 반환
def test_poll_no_task_returns_none():
    result = poll_and_run_once(_dummy_runner_ok)
    assert result is None


# TC-2: task 수신 후 실행
def test_poll_runs_task():
    create_local_browser_task("open_url", "https://www.g2b.go.kr/notice")
    result = poll_and_run_once(_dummy_runner_ok)
    assert result is not None
    assert result["status"] == STATUS_COMPLETED


# TC-3: runner 실패 → STATUS_FAILED
def test_poll_runner_exception_failed():
    create_local_browser_task("read_page", "https://www.g2b.go.kr")
    result = poll_and_run_once(_dummy_runner_fail)
    assert result["status"] == "FAILED"


# TC-4: 차단 action task → BLOCKED
def test_poll_blocked_action():
    record = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    tid = record["task_id"]
    # payload를 직접 조작해 차단 action 삽입
    from ai_orchestrator.server.task_queue_schema import _task_store

    _task_store[tid]["payload"]["action"] = "auto_bid_submit"
    result = poll_and_run_once(_dummy_runner_ok)
    assert result["status"] == STATUS_BLOCKED


# TC-5: 결과에 cookie 없음
def test_poll_result_no_cookie():
    create_local_browser_task("open_url", "https://www.g2b.go.kr/notice")
    result = poll_and_run_once(_dummy_runner_ok)
    assert result.get("cookie_exported") is False
    assert result.get("password_collected") is False


# TC-6: LOCAL_PLAYWRIGHT 아닌 mode → BLOCKED
def test_poll_wrong_execution_mode():
    record = create_local_browser_task("open_url", "https://www.g2b.go.kr")
    tid = record["task_id"]
    from ai_orchestrator.server.task_queue_schema import _task_store

    _task_store[tid]["payload"]["execution_mode"] = "SERVER_BROWSER"
    result = poll_and_run_once(_dummy_runner_ok)
    assert result["status"] == STATUS_BLOCKED
