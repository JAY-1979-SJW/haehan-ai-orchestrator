import inspect

from core.agent_runtime.connection import websocket_client
from core.agent_runtime.connection.actions import ActionResult
from core.agent_runtime.connection.websocket_client import _build_result_message


def test_ws_session_uses_thread_for_task_execution():
    # 작업 실행 호출은 직렬 경로(_handle_task_msg)와 병렬 경로(_run_task_parallel)로 분리됨(P1)
    for fn in (websocket_client._handle_task_msg, websocket_client._run_task_parallel):
        assert "await asyncio.to_thread(process_task, task)" in inspect.getsource(fn)


def test_ws_result_lifts_observe_and_audit_summary():
    result = ActionResult(
        success=True,
        summary="ok",
        data={
            "observe_summary": {
                "target_kind": "public_web",
                "status_category": "ok",
            },
            "audit_summary": {
                "event_counts": {"browser_open_completed": 1},
                "status_category_counts": {"ok": 1},
            },
        },
    )

    msg = _build_result_message({"task_id": "t-1"}, result)

    assert msg["observe_summary"]["status_category"] == "ok"
    assert msg["audit_summary"]["event_counts"]["browser_open_completed"] == 1
