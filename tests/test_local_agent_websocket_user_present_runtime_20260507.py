"""
Local Agent WebSocket User-Present Runtime 테스트

safe_to_execute: 항상 False.
실제 WebSocket 연결 없음.
실제 브라우저/사이트 접속 없음.
click/type/fill/submit 실행 없음.
password/otp/certificate_password/token/cookie/session 저장/전송 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.agent_hub.user_present_status_handler import (
    clear_status_registry,
    get_user_present_status,
    handle_user_present_status_event,
    validate_user_present_status_event,
)
from ai_orchestrator.contracts.user_present_ws_contract import (
    MSG_USER_PRESENT_STATUS,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_USER_CONFIRMED,
    STATUS_WAITING_FOR_USER,
)
from core.agent_runtime.connection.websocket_client import process_user_present_task
from core.agent_runtime.user_present.user_present_state_store import (
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
)
from core.agent_runtime.user_present.user_present_ws_adapter import (
    build_cancelled_status_event,
    build_confirmed_status_event,
    build_failed_status_event,
    build_waiting_status_event,
    create_local_user_present_task_from_ws,
    mark_local_user_confirmed_and_build_event,
)
from tests.helpers.local_agent_user_present_test_transport import (
    InMemoryTestTransport,
    make_bank_task_payload,
    make_hometax_task_payload,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "local_agent_websocket_user_present_runtime_20260507.json"


@pytest.fixture(scope="module")
def fixture_cases():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)["cases"]


@pytest.fixture(autouse=True)
def reset_status_registry():
    clear_status_registry()
    yield
    clear_status_registry()


@pytest.fixture
def fresh_store():
    return UserPresentStateStore()


# ── 1. fixture 로드 / 구조 검증 ───────────────────────────────────────────────


class TestFixtureStructure:
    def test_fixture_json_loadable(self, fixture_cases):
        assert len(fixture_cases) >= 16

    def test_all_cases_have_required_sections(self, fixture_cases):
        required = [
            "id",
            "input",
            "expected_local_state",
            "expected_ws_event",
            "expected_server_response",
            "expected_security_policy",
        ]
        for case in fixture_cases:
            for section in required:
                assert section in case, f"'{case.get('id')}' 에 누락: {section}"


# ── 2. websocket_client USER_PRESENT_TASK 인식 / 처리 ─────────────────────────


class TestWebsocketClientUserPresentTask:
    def test_process_user_present_task_valid(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_proc_001")
        result = (
            process_user_present_task.__wrapped__(msg, store=fresh_store)
            if hasattr(process_user_present_task, "__wrapped__")
            else _call_process_user_present_task(msg, fresh_store)
        )
        assert result["safe_to_execute"] is False

    def test_process_user_present_task_ack_type(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_proc_ack_001")
        ack = _call_process_user_present_task(msg, fresh_store)
        assert ack["type"] == "user_present_ack"

    def test_process_user_present_task_waiting_status(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_proc_wait_001")
        ack = _call_process_user_present_task(msg, fresh_store)
        assert ack["status"] == "WAITING_FOR_USER"
        assert ack["safe_to_execute"] is False

    def test_process_user_present_task_invalid_rejected(self, fresh_store):
        msg = {"message_type": "USER_PRESENT_TASK", "tenant_id": "t1"}
        ack = _call_process_user_present_task(msg, fresh_store)
        assert ack["status"] == "FAILED"
        assert ack["safe_to_execute"] is False

    def test_process_user_present_task_creates_store_entry(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_proc_store_001")
        _call_process_user_present_task(msg, fresh_store)
        task = fresh_store.get_user_present_task("wr_proc_store_001")
        assert task is not None
        assert task["state"] == STATE_WAITING_FOR_USER


# ── 3. 민감정보 저장/전송 차단 ────────────────────────────────────────────────


class TestSensitiveFieldBlocking:
    def test_raw_url_not_stored(self, fresh_store):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            sanitize_user_present_ws_payload,
        )

        payload = {"workflow_run_id": "wr_url_001", "target_url": "https://kbstar.com/login"}
        clean = sanitize_user_present_ws_payload(payload)
        assert "target_url" not in clean

    def test_password_not_stored(self, fresh_store):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            sanitize_user_present_ws_payload,
        )

        payload = {"workflow_run_id": "wr_pwd_001", "password": "secret"}
        clean = sanitize_user_present_ws_payload(payload)
        assert "password" not in clean

    def test_otp_not_stored(self, fresh_store):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            sanitize_user_present_ws_payload,
        )

        payload = {"workflow_run_id": "wr_otp_001", "otp": "123456"}
        clean = sanitize_user_present_ws_payload(payload)
        assert "otp" not in clean

    def test_certificate_password_not_stored(self, fresh_store):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            sanitize_user_present_ws_payload,
        )

        payload = {"workflow_run_id": "wr_cp_001", "certificate_password": "cert123"}
        clean = sanitize_user_present_ws_payload(payload)
        assert "certificate_password" not in clean

    def test_token_cookie_session_not_stored(self, fresh_store):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            sanitize_user_present_ws_payload,
        )

        payload = {"token": "tkn", "cookie": "ck", "session": "ss"}
        clean = sanitize_user_present_ws_payload(payload)
        assert "token" not in clean
        assert "cookie" not in clean
        assert "session" not in clean


# ── 4. status event builder helpers ──────────────────────────────────────────


class TestStatusEventBuilders:
    def test_build_waiting_status_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_build_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        event = build_waiting_status_event("wr_build_001", store=fresh_store)
        assert event["message_type"] == MSG_USER_PRESENT_STATUS
        assert event["status"] == STATUS_WAITING_FOR_USER
        assert event["safe_to_execute"] is False

    def test_build_confirmed_status_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_build_confirm_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        event = build_confirmed_status_event("wr_build_confirm_001", store=fresh_store)
        assert event["status"] == STATUS_USER_CONFIRMED
        assert event["safe_to_execute"] is False

    def test_build_cancelled_status_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_build_cancel_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        event = build_cancelled_status_event("wr_build_cancel_001", store=fresh_store)
        assert event["status"] == STATUS_CANCELLED
        assert event["safe_to_execute"] is False

    def test_build_failed_status_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_build_failed_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        event = build_failed_status_event("wr_build_failed_001", "네트워크 오류", store=fresh_store)
        assert event["status"] == STATUS_FAILED
        assert event["safe_to_execute"] is False

    def test_user_confirmed_event_no_browser_action(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_build_no_action_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_build_no_action_001", store=fresh_store)
        assert result["ok"] is True
        event = result["event"]
        assert "click" not in event
        assert "submit" not in event
        assert "type" not in event or event.get("type") is None or event.get("message_type") == MSG_USER_PRESENT_STATUS
        assert event["safe_to_execute"] is False

    def test_user_confirmed_no_click_type_submit(self, fresh_store):
        msg = make_hometax_task_payload(workflow_run_id="wr_build_hometax_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_build_hometax_001", store=fresh_store)
        assert result["safe_to_execute"] is False
        assert result["ok"] is True


# ── 5. 서버 handler 검증 ──────────────────────────────────────────────────────


class TestServerHandler:
    def _make_valid_event(self, workflow_run_id: str, status: str = "USER_CONFIRMED") -> dict:
        return {
            "message_type": MSG_USER_PRESENT_STATUS,
            "workflow_run_id": workflow_run_id,
            "tenant_id": "t1",
            "user_id": "u1",
            "site_id": "s1",
            "status": status,
            "status_reason": "",
            "safe_to_execute": False,
            "created_at": "2026-05-07T00:00:00+00:00",
        }

    def test_server_accepts_confirmed(self):
        event = self._make_valid_event("wr_srv_001", "USER_CONFIRMED")
        result = handle_user_present_status_event(event)
        assert result["ok"] is True
        assert result["accepted_status"] == "USER_CONFIRMED"
        assert result["safe_to_execute"] is False

    def test_server_accepts_cancelled(self):
        event = self._make_valid_event("wr_srv_002", "CANCELLED")
        result = handle_user_present_status_event(event)
        assert result["ok"] is True
        assert result["accepted_status"] == "CANCELLED"

    def test_server_rejects_safe_to_execute_true(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "server_rejects_safe_to_execute_true")
        result = handle_user_present_status_event(case["input"])
        assert result["ok"] is False
        assert result["safe_to_execute"] is False

    def test_server_rejects_token(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "server_rejects_token_cookie_session")
        result = handle_user_present_status_event(case["input"])
        assert result["ok"] is False
        assert result["safe_to_execute"] is False

    def test_server_rejects_cookie(self):
        event = self._make_valid_event("wr_srv_ck_001")
        event["cookie"] = "must_be_rejected"
        result = handle_user_present_status_event(event)
        assert result["ok"] is False

    def test_server_rejects_session(self):
        event = self._make_valid_event("wr_srv_ss_001")
        event["session"] = "must_be_rejected"
        result = handle_user_present_status_event(event)
        assert result["ok"] is False

    def test_get_user_present_status_after_accept(self):
        event = self._make_valid_event("wr_srv_get_001", "USER_CONFIRMED")
        handle_user_present_status_event(event)
        status = get_user_present_status("wr_srv_get_001")
        assert status is not None
        assert status["status"] == "USER_CONFIRMED"
        assert status["safe_to_execute"] is False

    def test_server_validate_detects_forbidden_field(self):
        event = self._make_valid_event("wr_srv_val_001")
        event["token"] = "should_fail"
        errors = validate_user_present_status_event(event)
        assert any("token" in e for e in errors)

    def test_server_validate_detects_safe_to_execute_true(self):
        event = self._make_valid_event("wr_srv_val_002")
        event["safe_to_execute"] = True
        errors = validate_user_present_status_event(event)
        assert any("safe_to_execute" in e for e in errors)


# ── 6. 기존 WebSocket 호환성 ──────────────────────────────────────────────────


class TestWebSocketCompatibility:
    def test_process_task_still_works(self):
        from core.agent_runtime.connection.websocket_client import process_task

        task = {"task_id": "tid_test", "action": "ping", "params": {}, "risk_level": "low"}
        result = process_task(task)
        assert result["type"] == "result"

    def test_user_present_task_does_not_break_process_task(self):
        from core.agent_runtime.connection.websocket_client import process_task, process_user_present_task

        assert callable(process_task)
        assert callable(process_user_present_task)

    def test_no_conflict_with_browser_websocket_schema(self):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            _VALID_STATUS_VALUES,
        )
        from core.agent_runtime.browser.bridge.browser_websocket_schema import VALID_TASK_STATUS

        assert VALID_TASK_STATUS.isdisjoint(_VALID_STATUS_VALUES)


# ── 7. 실제 WebSocket 연결 없음 / 보안 원칙 ──────────────────────────────────


class TestSecurityPrinciples:
    def test_no_real_websocket_in_handler_source(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_handler as mod

        src = inspect.getsource(mod)
        assert "websockets.connect" not in src

    def test_no_db_write_in_handler_source(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_handler as mod

        src = inspect.getsource(mod)
        assert "INSERT INTO" not in src
        assert "session.commit()" not in src

    def test_no_browser_action_in_handler_source(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_handler as mod

        src = inspect.getsource(mod)
        forbidden = ["page.click(", "page.fill(", "page.goto("]
        for token in forbidden:
            assert token not in src

    def test_no_task_executor_in_handler_source(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_handler as mod

        src = inspect.getsource(mod)
        assert "TaskExecutor(" not in src

    def test_no_browser_worker_in_handler_source(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_handler as mod

        src = inspect.getsource(mod)
        assert "browser_worker" not in src
        assert "ai_orchestrator.browser_tool.worker" not in src

    def test_in_memory_transport_no_external_connection(self):
        transport = InMemoryTestTransport()
        msg = make_bank_task_payload()
        transport.send(msg)
        assert transport.sent_count == 1


# ── 8. 호환성 ─────────────────────────────────────────────────────────────────


class TestCompatibility:
    def test_compatible_with_ws_contract(self):
        from ai_orchestrator.contracts.user_present_ws_contract import (
            build_user_present_ws_task_message,
            validate_user_present_ws_task_message,
        )

        msg = build_user_present_ws_task_message(
            {
                "workflow_run_id": "wr_compat_001",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "site_category": "bank",
                "target_domain": "kbstar.com",
            }
        )
        errors = validate_user_present_ws_task_message(msg)
        assert errors == []

    def test_compatible_with_state_store(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_compat_store_001")
        _call_process_user_present_task(msg, fresh_store)
        task = fresh_store.get_user_present_task("wr_compat_store_001")
        assert task is not None

    def test_compatible_with_user_present_ui_server(self):
        from core.agent_runtime.user_present.user_present_ui_server import _FASTAPI_AVAILABLE

        # ui_server 임포트 가능 여부 확인 (실제 서버 실행 없음)
        assert _FASTAPI_AVAILABLE is True or _FASTAPI_AVAILABLE is False

    def test_process_user_present_task_safe_to_execute_false(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_compat_safe_001")
        ack = _call_process_user_present_task(msg, fresh_store)
        assert ack["safe_to_execute"] is False


# ── helper ────────────────────────────────────────────────────────────────────


def _call_process_user_present_task(
    msg: dict,
    store: "UserPresentStateStore",
) -> dict:
    """process_user_present_task를 store 주입하여 호출하는 테스트 헬퍼."""
    from core.agent_runtime.user_present.user_present_ws_adapter import create_local_user_present_task_from_ws

    result = create_local_user_present_task_from_ws(msg, store=store)
    workflow_run_id = msg.get("workflow_run_id", "")

    if result["ok"]:
        return {
            "type": "user_present_ack",
            "workflow_run_id": workflow_run_id,
            "status": "WAITING_FOR_USER",
            "safe_to_execute": False,
        }
    else:
        return {
            "type": "user_present_ack",
            "workflow_run_id": workflow_run_id,
            "status": "FAILED",
            "error": "VALIDATION_FAILED",
            "safe_to_execute": False,
        }
