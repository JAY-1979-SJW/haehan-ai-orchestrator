"""ORCHESTRATOR_WEB_REMOTE_USER_PRESENT_RUNTIME_INTEGRATION_01 — 필수 테스트 7종.

본 공정에서 추가된 흐름만 검증한다.
  D2 APPROVAL_REQUIRED placeholder 상태
  D3 site_compliance_gate stub (정책 3종 압축)
  D4 _handle_result 멱등화
  D5 task_blocked WS 통지

운영 DB / 외부 사이트 / CDP 접근 없이 in-memory 만 사용한다.
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.agent_runtime.user_present.user_present_state_store import (
    STATE_APPROVAL_REQUIRED,
    STATE_CANCELLED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
    validate_user_present_task,
)

# ── Mock WebSocket ──────────────────────────────────────────────────────────


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed_code: int | None = None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:  # pragma: no cover
        self.closed_code = code


def _run(coro):
    return (
        asyncio.get_event_loop().run_until_complete(coro)
        if not asyncio.iscoroutine(coro)
        else asyncio.new_event_loop().run_until_complete(coro)
    )


# ── 1. USER_PRESENT_TASK 수신 → WAITING_FOR_USER 등록 ───────────────────────


def test_user_present_task_received_then_waiting_for_user():
    store = UserPresentStateStore()
    task = store.create_user_present_task(
        {
            "workflow_run_id": "wf_001",
            "target_domain": "example.com",
            "password": "should_be_stripped",
            "device_token": "should_be_stripped",
        }
    )
    assert task["workflow_run_id"] == "wf_001"
    assert task["safe_to_execute"] is False
    assert "password" not in task
    assert "device_token" not in task

    waiting = store.mark_waiting_for_user("wf_001")
    assert waiting["state"] == STATE_WAITING_FOR_USER
    assert waiting["safe_to_execute"] is False


# ── 3. 사용자 확인 → USER_CONFIRMED ──────────────────────────────────────────


def test_user_confirmed_transition():
    store = UserPresentStateStore()
    store.create_user_present_task({"workflow_run_id": "wf_conf"})
    store.mark_waiting_for_user("wf_conf")
    confirmed = store.mark_user_confirmed("wf_conf")
    assert confirmed["state"] == STATE_USER_CONFIRMED
    assert confirmed["confirmed_at"]


# ── 4. 사용자 거절 → CANCELLED ───────────────────────────────────────────────


def test_user_cancelled_transition():
    store = UserPresentStateStore()
    store.create_user_present_task({"workflow_run_id": "wf_cancel"})
    store.mark_waiting_for_user("wf_cancel")
    cancelled = store.mark_user_cancelled("wf_cancel")
    assert cancelled["state"] == STATE_CANCELLED
    assert cancelled["cancelled_at"]


# ── 5. BLOCKED 정책 게이트 차단 (site_compliance_gate stub) ─────────────────


def test_site_compliance_gate_blocks_automation_blocked_site():
    from core.agent_runtime.policy.site_compliance_gate import (
        POLICY_AUTOMATION_BLOCKED,
        evaluate_gate,
        is_blocked,
    )

    result = evaluate_gate(
        {
            "target_domain": "accounts.google.com",
            "operation_type": "click",
            "user_present": True,
        }
    )
    assert result["allowed"] is False
    assert result["policy"] == POLICY_AUTOMATION_BLOCKED
    assert (
        is_blocked(
            {
                "target_domain": "accounts.google.com",
                "operation_type": "click",
            }
        )
        is True
    )


def test_site_compliance_gate_allows_user_present_local_only_when_user_present():
    # 알려지지 않은 사이트는 기본적으로 BLOCK 이므로, USER_PRESENT_LOCAL_ONLY
    # 분기는 policy module 의 patch 로 시뮬레이션한다.
    import core.agent_runtime.policy.site_compliance_gate as gate
    from core.agent_runtime.policy.site_compliance_gate import (
        POLICY_USER_PRESENT_LOCAL_ONLY,
        evaluate_gate,
    )

    def _fake_eval(_payload):
        return {
            "compliance_decision": "ALLOW_BROWSER_READONLY",
            "site_capability": "USER_PRESENT_LOCAL_ONLY",
            "safe_to_dispatch": True,
            "block_reason": None,
            "message_ko": "사용자 현장 확인 후 허용",
        }

    original = gate._evaluate
    try:
        gate._evaluate = _fake_eval
        r = evaluate_gate({"target_domain": "test.example", "user_present": True})
    finally:
        gate._evaluate = original

    assert r["allowed"] is True
    assert r["policy"] == POLICY_USER_PRESENT_LOCAL_ONLY


# ── 6. task_blocked 알림 전송 (D5) ───────────────────────────────────────────


def test_send_task_blocked_emits_status_message():
    from ai_orchestrator.agent_hub.router.ws import _send_task_blocked

    ws = _FakeWS()
    asyncio.new_event_loop().run_until_complete(
        _send_task_blocked(
            ws,
            task_id="t_001",
            workflow_run_id="wf_block",
            reason="AUTOMATION_BLOCKED",
            message_ko="자동화 차단",
        )
    )
    assert len(ws.sent) == 1
    msg = ws.sent[0]
    assert msg["type"] == "task_blocked"
    assert msg["task_id"] == "t_001"
    assert msg["reason"] == "AUTOMATION_BLOCKED"
    assert msg["safe_to_execute"] is False
    # 민감 필드 미포함 확인
    for forbidden in ("token", "device_token", "cookie", "authorization", "password", "otp"):
        assert forbidden not in msg


# ── 7. result 중복 수신 시 ack 만 반환 (D4 멱등화) ──────────────────────────


def test_handle_result_idempotent_when_already_final():
    from ai_orchestrator.agent_hub.router import ws as r

    ws = _FakeWS()

    class _FakeTask:
        agent_id = "agent_a"
        task_id = "t_done"
        status = "completed"

    original_get_task = r._reg.get_task
    try:
        r._reg.get_task = lambda agent_id, task_id: _FakeTask() if task_id == "t_done" else None  # type: ignore[assignment,return-value]
        asyncio.new_event_loop().run_until_complete(
            r._handle_result(
                ws,
                "agent_a",
                {"task_id": "t_done", "success": True, "summary": "duplicate"},
            )
        )
    finally:
        r._reg.get_task = original_get_task

    assert len(ws.sent) == 1
    ack = ws.sent[0]
    assert ack["type"] == "result_ack"
    assert ack["task_id"] == "t_done"
    assert ack["status"] == "completed"
    assert ack["idempotent"] is True


# ── 추가: APPROVAL_REQUIRED placeholder 상태 검증기 통과 ────────────────────


def test_approval_required_state_passes_validator():
    task = {
        "workflow_run_id": "wf_appr",
        "state": STATE_APPROVAL_REQUIRED,
        "safe_to_execute": False,
        "safe_to_dispatch": False,
        "audit_required": True,
        "created_at": "2026-05-20T00:00:00+00:00",
    }
    errors = validate_user_present_task(task)
    assert errors == []


# ── 추가: secret 필드가 task_blocked 메시지에 노출되지 않는다 ───────────────


def test_task_blocked_strips_long_fields():
    from ai_orchestrator.agent_hub.router.ws import _send_task_blocked

    ws = _FakeWS()
    asyncio.new_event_loop().run_until_complete(
        _send_task_blocked(
            ws,
            task_id="x" * 500,
            workflow_run_id="y" * 500,
            reason="z" * 500,
            message_ko="m" * 500,
        )
    )
    msg = ws.sent[0]
    assert len(msg["task_id"]) <= 80
    assert len(msg["workflow_run_id"]) <= 120
    assert len(msg["reason"]) <= 80
    assert len(msg["message_ko"]) <= 200
