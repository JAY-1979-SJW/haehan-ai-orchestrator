from local_agent.actions import ActionResult
from local_agent.websocket_client import _build_result_message


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
