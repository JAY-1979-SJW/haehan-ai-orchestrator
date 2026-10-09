"""
LOCAL_AGENT_WS_STATUS_AUTO_SEND_1 테스트

USER_PRESENT_STATUS 자동 전송 로직 검증.
실제 WebSocket 연결 없음. 브라우저 실행 없음. 외부 사이트 접속 없음.
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FIXTURE_PATH = REPO / "tests" / "fixtures" / "local_agent_ws_status_auto_send_20260507.json"

from core.agent_runtime.user_present.user_present_state_store import (  # noqa: E402
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
)
from core.agent_runtime.user_present.user_present_status_sender import (  # noqa: E402
    _FORBIDDEN_EVENT_FIELDS,
    _sent_statuses,
    collect_pending_user_present_status_events,
    mark_user_present_status_sent,
    reset_sent_statuses_for_testing,
    run_user_present_status_send_once,
    send_user_present_status_event,
)

# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_task(workflow_run_id: str, state: str) -> dict:
    return {
        "workflow_run_id": workflow_run_id,
        "tenant_id": "tenant-test",
        "user_id": "user-test",
        "site_id": "smoke.local",
        "target_url_redacted": "https://smoke.local/test",
        "target_url_hash": "sha256-test",
        "auth_method_label": "테스트",
        "state": state,
        "safe_to_execute": False,
        "safe_to_dispatch": False,
        "audit_required": True,
        "created_at": "2026-05-07T10:00:00+00:00",
        "updated_at": "2026-05-07T10:00:00+00:00",
        "confirmed_at": None,
        "cancelled_at": None,
    }


def _make_store(*tasks: dict) -> UserPresentStateStore:
    store = UserPresentStateStore()
    for t in tasks:
        with store._lock:
            store._store[t["workflow_run_id"]] = dict(t)
    return store


class MockWS:
    """비동기 WS mock — send/recv 추적."""

    def __init__(self):
        self.sent: list[str] = []
        self._recv_queue: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if self._recv_queue:
            return self._recv_queue.pop(0)
        raise TimeoutError()

    def push_recv(self, data: dict) -> None:
        self._recv_queue.append(json.dumps(data))


# ── STEP 6: fixture 무결성 ─────────────────────────────────────────────────────


class TestFixtureIntegrity(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_1_fixture_json_loadable(self):
        self.assertIn("cases", self.fixture)
        self.assertIsInstance(self.fixture["cases"], list)

    def test_2_all_cases_have_required_sections(self):
        required_ids = {
            "confirmed_status_pending_send",
            "cancelled_status_pending_send",
            "blocked_status_pending_send",
            "failed_status_pending_send",
            "waiting_for_user_not_repeated",
            "confirmed_sent_once",
            "cancelled_sent_once",
            "send_failure_keeps_pending",
            "safe_to_execute_true_rejected",
            "token_cookie_session_rejected",
            "password_otp_certificate_password_rejected",
            "server_ack_marks_sent",
            "duplicate_status_not_resent",
            "heartbeat_still_works",
            "existing_task_receive_still_works",
        }
        actual_ids = {c["id"] for c in self.fixture["cases"]}
        missing = required_ids - actual_ids
        self.assertEqual(missing, set(), f"fixture 케이스 누락: {missing}")

    def test_fixture_case_count(self):
        self.assertEqual(len(self.fixture["cases"]), 15)


# ── STEP 3-4: collect_pending_user_present_status_events ─────────────────────


class TestCollectPending(unittest.TestCase):
    def setUp(self):
        reset_sent_statuses_for_testing()

    def test_3_user_confirmed_is_collected(self):
        store = _make_store(_make_task("wf-c1", STATE_USER_CONFIRMED))
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "USER_CONFIRMED")

    def test_4_cancelled_is_collected(self):
        store = _make_store(_make_task("wf-c2", STATE_CANCELLED))
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "CANCELLED")

    def test_5_blocked_is_collected(self):
        store = _make_store(_make_task("wf-c3", STATE_BLOCKED))
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "BLOCKED")

    def test_6_failed_is_collected(self):
        store = _make_store(_make_task("wf-c4", STATE_FAILED))
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "FAILED")

    def test_7_waiting_for_user_not_collected(self):
        store = _make_store(_make_task("wf-w1", STATE_WAITING_FOR_USER))
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(events, [])

    def test_9_duplicate_status_not_collected_after_sent(self):
        store = _make_store(_make_task("wf-dup", STATE_USER_CONFIRMED))
        mark_user_present_status_sent("wf-dup", "USER_CONFIRMED")
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(events, [])


# ── mark_user_present_status_sent ─────────────────────────────────────────────


class TestSentMarker(unittest.TestCase):
    def setUp(self):
        reset_sent_statuses_for_testing()

    def test_8_mark_sent_records_workflow_and_status(self):
        result = mark_user_present_status_sent("wf-m1", "USER_CONFIRMED")
        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow_run_id"], "wf-m1")
        self.assertEqual(result["marked_status"], "USER_CONFIRMED")

    def test_12_server_ack_marks_sent(self):
        store = _make_store(_make_task("wf-ack-t", STATE_USER_CONFIRMED))
        # 전송 전: pending 있음
        before = collect_pending_user_present_status_events(store)
        self.assertEqual(len(before), 1)
        # 전송 성공 → marker 기록
        mark_user_present_status_sent("wf-ack-t", "USER_CONFIRMED")
        # 전송 후: pending 없음
        after = collect_pending_user_present_status_events(store)
        self.assertEqual(len(after), 0)

    def test_13_duplicate_not_resent_after_mark(self):
        reset_sent_statuses_for_testing()
        store = _make_store(_make_task("wf-dup2", STATE_CANCELLED))
        mark_user_present_status_sent("wf-dup2", "CANCELLED")
        events = collect_pending_user_present_status_events(store)
        self.assertEqual(events, [])


# ── send_user_present_status_event 검증 ──────────────────────────────────────


class TestSendValidation(unittest.TestCase):
    def setUp(self):
        reset_sent_statuses_for_testing()

    def _run(self, coro):
        return asyncio.run(coro)

    def _make_event(self, **extra) -> dict:
        base = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": "wf-v1",
            "tenant_id": "tenant-test",
            "user_id": "user-test",
            "site_id": "smoke.local",
            "status": "USER_CONFIRMED",
            "status_reason": "",
            "safe_to_execute": False,
            "created_at": "2026-05-07T10:00:00+00:00",
        }
        base.update(extra)
        return base

    def test_11_safe_to_execute_true_rejected(self):
        ws = MockWS()
        event = self._make_event(safe_to_execute=True)
        result = self._run(send_user_present_status_event(ws, event))
        self.assertFalse(result["ok"])
        self.assertFalse(result["sent"])
        self.assertTrue(any("BLOCKED_SAFE_TO_EXECUTE_TRUE" in e for e in result["errors"]))
        self.assertEqual(len(ws.sent), 0)

    def test_12_token_cookie_session_rejected(self):
        ws = MockWS()
        event = self._make_event(token="bad", cookie="bad", session="bad")
        result = self._run(send_user_present_status_event(ws, event))
        self.assertFalse(result["ok"])
        self.assertFalse(result["sent"])
        self.assertTrue(any("BLOCKED_SENSITIVE_FIELD" in e for e in result["errors"]))
        self.assertEqual(len(ws.sent), 0)

    def test_12b_password_otp_certificate_password_rejected(self):
        ws = MockWS()
        event = self._make_event(password="bad", otp="bad", certificate_password="bad")
        result = self._run(send_user_present_status_event(ws, event))
        self.assertFalse(result["ok"])
        self.assertFalse(result["sent"])
        self.assertTrue(any("BLOCKED_SENSITIVE_FIELD" in e for e in result["errors"]))
        self.assertEqual(len(ws.sent), 0)

    def test_valid_event_sends_and_marks(self):
        ws = MockWS()
        event = self._make_event(workflow_run_id="wf-valid-send")
        result = self._run(send_user_present_status_event(ws, event))
        self.assertTrue(result["ok"])
        self.assertTrue(result["sent"])
        self.assertEqual(len(ws.sent), 1)
        payload = json.loads(ws.sent[0])
        self.assertEqual(payload["type"], "user_present_status")
        self.assertEqual(payload["status"], "USER_CONFIRMED")
        # sent marker 기록됨
        self.assertEqual(_sent_statuses.get("wf-valid-send"), "USER_CONFIRMED")

    def test_payload_flat_structure(self):
        """서버 핸들러가 flat 구조로 event 필드를 기대함 — type + event_fields 병합."""
        ws = MockWS()
        event = self._make_event(workflow_run_id="wf-flat-001")
        asyncio.run(send_user_present_status_event(ws, event))
        payload = json.loads(ws.sent[0])
        self.assertIn("type", payload)
        self.assertIn("workflow_run_id", payload)
        self.assertIn("status", payload)
        self.assertNotIn("event", payload)  # nested "event" 키 없어야 함

    def test_10_send_failure_keeps_pending(self):
        """WS send 실패 시 sent marker 미기록."""

        class FailWS:
            async def send(self, data):
                raise ConnectionError("WS dead")

        ws = FailWS()
        event = self._make_event(workflow_run_id="wf-fail-send")
        result = self._run(send_user_present_status_event(ws, event))
        self.assertFalse(result["sent"])
        self.assertNotIn("wf-fail-send", _sent_statuses)


# ── run_user_present_status_send_once ─────────────────────────────────────────


class TestRunSendOnce(unittest.TestCase):
    def setUp(self):
        reset_sent_statuses_for_testing()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_run_once_sends_all_pending(self):
        store = _make_store(
            _make_task("wf-ro-1", STATE_USER_CONFIRMED),
            _make_task("wf-ro-2", STATE_CANCELLED),
        )
        ws = MockWS()
        result = self._run(run_user_present_status_send_once(ws, store))
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(ws.sent), 2)

    def test_run_once_skips_already_sent(self):
        store = _make_store(_make_task("wf-ro-skip", STATE_USER_CONFIRMED))
        mark_user_present_status_sent("wf-ro-skip", "USER_CONFIRMED")
        ws = MockWS()
        result = self._run(run_user_present_status_send_once(ws, store))
        self.assertEqual(result["sent"], 0)
        self.assertEqual(len(ws.sent), 0)

    def test_run_once_empty_store(self):
        store = UserPresentStateStore()
        ws = MockWS()
        result = self._run(run_user_present_status_send_once(ws, store))
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)


# ── 안전 정책 ──────────────────────────────────────────────────────────────────


class TestSecurityPolicy(unittest.TestCase):
    def test_14_heartbeat_path_coexists(self):
        """_STATUS_SENDER_AVAILABLE import 경로 확인."""
        from core.agent_runtime.connection import websocket_client

        self.assertTrue(hasattr(websocket_client, "_STATUS_SENDER_AVAILABLE"))
        self.assertTrue(websocket_client._STATUS_SENDER_AVAILABLE)

    def test_15_existing_task_receive_path_unchanged(self):
        """process_user_present_task 기존 경로 여전히 작동."""
        from core.agent_runtime.connection.websocket_client import process_user_present_task

        msg = {
            "message_type": "USER_PRESENT_TASK",
            "workflow_run_id": "wf-coexist-test",
            "tenant_id": "tenant-test",
            "user_id": "user-test",
            "site_id": "smoke.local",
            "site_category": "test",
            "target_url_redacted": "https://smoke.local/test",
            "target_url_hash": "sha256-test",
            "target_domain": "smoke.local",
            "auth_method_label": "테스트",
            "user_message_ko": "테스트 메시지",
            "required_user_actions": [],
            "blocked_ai_actions": [],
            "safe_to_execute": False,
            "created_at": "2026-05-07T10:00:00+00:00",
        }
        result = process_user_present_task(msg)
        self.assertEqual(result["status"], "WAITING_FOR_USER")
        self.assertFalse(result["safe_to_execute"])

    def test_17_general_task_path_unchanged(self):
        """process_task 기존 경로 여전히 작동 (forbidden action)."""
        from core.agent_runtime.connection.websocket_client import process_task

        task = {"task_id": "t-001", "action": "delete_file", "params": {}}
        result = process_task(task)
        self.assertEqual(result["error_code"], "ACTION_FORBIDDEN")

    def test_18_no_real_websocket_connection(self):
        """실제 WS 연결 없음 — websockets.connect 호출 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        self.assertNotIn("websockets.connect", src)
        self.assertNotIn("websockets.serve", src)

    def test_19_no_browser_execution(self):
        """브라우저 실행 코드 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        forbidden = ["playwright", "execute_click", "execute_type", "browser_worker", "ai_orchestrator.browser_tool.worker"]
        for kw in forbidden:
            self.assertNotIn(kw, src, f"금지 키워드 발견: {kw}")

    def test_20_no_click_type_fill_submit(self):
        """click/type/fill/submit 호출 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        for kw in [".click(", ".type(", ".fill(", ".submit("]:
            self.assertNotIn(kw, src, f"금지 호출 발견: {kw}")

    def test_21_no_task_executor_browser_worker(self):
        """task_executor/browser_worker 호출 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        for kw in ["task_executor", "browser_worker", "ai_orchestrator.browser_tool.worker"]:
            self.assertNotIn(kw, src)

    def test_22_no_db_write(self):
        """DB write 없음 — sqlite/sqlalchemy 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        for kw in ["sqlite3", "sqlalchemy", ".execute(", ".commit("]:
            self.assertNotIn(kw, src)

    def test_23_no_credential_output(self):
        """registration_code/device_token 출력(print/log) 없음."""
        import core.agent_runtime.user_present.user_present_status_sender as sender

        src = Path(sender.__file__).read_text(encoding="utf-8")
        # print/logger 출력 라인에 registration_code 포함 금지
        self.assertNotIn("registration_code", src)
        # device_token은 FORBIDDEN_EVENT_FIELDS 차단 목록으로만 허용 — logger.info 출력 금지
        import re

        log_lines = [
            ln
            for ln in src.splitlines()
            if re.search(r"(print|logger\.(info|warning|error|debug))", ln) and "device_token" in ln
        ]
        self.assertEqual(log_lines, [], f"device_token 로그 출력 발견: {log_lines}")

    def test_all_sent_events_have_safe_to_execute_false(self):
        """전송 event의 safe_to_execute는 항상 False."""
        reset_sent_statuses_for_testing()
        store = _make_store(_make_task("wf-ste", STATE_USER_CONFIRMED))
        events = collect_pending_user_present_status_events(store)
        for e in events:
            self.assertIs(e.get("safe_to_execute"), False)

    def test_forbidden_fields_coverage(self):
        """_FORBIDDEN_EVENT_FIELDS가 필수 민감키를 포함."""
        required = {"password", "otp", "certificate_password", "token", "cookie", "session"}
        self.assertTrue(required.issubset(_FORBIDDEN_EVENT_FIELDS))


if __name__ == "__main__":
    unittest.main()
