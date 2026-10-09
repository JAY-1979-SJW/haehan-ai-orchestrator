"""
Local Agent WebSocket User-Present Integration 테스트

safe_to_execute: 항상 False.
실제 WebSocket 연결 없음.
실제 브라우저/사이트 접속 없음.
password/otp/certificate_password/token/cookie/session 전송 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.contracts.user_present_ws_contract import (
    MSG_USER_PRESENT_TASK,
    STATUS_CANCELLED,
    STATUS_USER_CONFIRMED,
    STATUS_WAITING_FOR_USER,
    build_user_present_ws_status_event,
    build_user_present_ws_task_message,
    sanitize_user_present_ws_payload,
    validate_user_present_ws_status_event,
    validate_user_present_ws_task_message,
)
from core.agent_runtime.user_present.user_present_state_store import (
    STATE_BLOCKED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
)
from core.agent_runtime.user_present.user_present_ws_adapter import (
    create_local_user_present_task_from_ws,
    mark_local_user_cancelled_and_build_event,
    mark_local_user_confirmed_and_build_event,
)
from tests.helpers.local_agent_user_present_test_transport import (
    InMemoryTestTransport,
    make_bank_task_payload,
    make_hometax_task_payload,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "local_agent_websocket_user_present_integration_20260507.json"


@pytest.fixture(scope="module")
def fixture_cases():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)["cases"]


@pytest.fixture
def fresh_store():
    store = UserPresentStateStore()
    return store


@pytest.fixture
def transport():
    return InMemoryTestTransport()


# ── 1. fixture 로드 / 구조 검증 ───────────────────────────────────────────────


class TestFixtureStructure:
    def test_fixture_json_loadable(self, fixture_cases):
        assert len(fixture_cases) >= 16

    def test_all_cases_have_required_sections(self, fixture_cases):
        required_sections = [
            "id",
            "input",
            "expected_task_message",
            "expected_local_task",
            "expected_status_event",
            "expected_security_policy",
        ]
        for case in fixture_cases:
            for section in required_sections:
                assert section in case, f"케이스 '{case.get('id')}' 에 누락된 섹션: {section}"


# ── 2. USER_PRESENT_TASK message 생성 ─────────────────────────────────────────


class TestUserPresentTaskMessage:
    def test_task_message_created_for_bank(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "bank_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["message_type"] == MSG_USER_PRESENT_TASK
        assert msg["safe_to_execute"] is False

    def test_task_message_created_for_hometax(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "hometax_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["message_type"] == MSG_USER_PRESENT_TASK

    def test_task_message_created_for_card(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "card_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["message_type"] == MSG_USER_PRESENT_TASK

    def test_task_message_created_for_gov24(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "gov24_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["message_type"] == MSG_USER_PRESENT_TASK

    def test_task_message_created_for_certificate(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "certificate_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["message_type"] == MSG_USER_PRESENT_TASK


# ── 3. message validation ─────────────────────────────────────────────────────


class TestTaskMessageValidation:
    def test_valid_message_passes(self):
        msg = make_bank_task_payload()
        errors = validate_user_present_ws_task_message(msg)
        assert errors == []

    def test_workflow_run_id_missing_fails(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "invalid_message_missing_workflow_run_id")
        errors = validate_user_present_ws_task_message(case["input"])
        assert any("workflow_run_id" in e for e in errors)

    def test_tenant_id_missing_fails(self):
        msg = make_bank_task_payload()
        msg["tenant_id"] = ""
        errors = validate_user_present_ws_task_message(msg)
        assert any("tenant_id" in e for e in errors)

    def test_user_id_missing_fails(self):
        msg = make_bank_task_payload()
        msg["user_id"] = ""
        errors = validate_user_present_ws_task_message(msg)
        assert any("user_id" in e for e in errors)

    def test_site_id_missing_field_detected(self):
        msg = dict(make_bank_task_payload())
        del msg["site_id"]
        errors = validate_user_present_ws_task_message(msg)
        assert any("site_id" in e for e in errors)


# ── 4. 민감정보 전송 차단 ─────────────────────────────────────────────────────


class TestSensitiveFieldBlocking:
    def test_password_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_password")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "password" not in clean

    def test_otp_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_otp")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "otp" not in clean

    def test_certificate_password_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_certificate_password")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "certificate_password" not in clean

    def test_token_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_token_cookie_session")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "token" not in clean

    def test_cookie_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_token_cookie_session")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "cookie" not in clean

    def test_session_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_token_cookie_session")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "session" not in clean

    def test_raw_target_url_blocked_in_sanitize(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "bank_user_present_task_message")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "target_url" not in clean

    def test_target_url_redacted_present(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "bank_user_present_task_message")
        msg = build_user_present_ws_task_message(case["input"])
        assert "target_url_redacted" in msg
        assert "target_url_hash" in msg
        assert "target_url" not in msg

    def test_cross_tenant_data_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "cross_tenant_payload_rejected")
        clean = sanitize_user_present_ws_payload(case["input"])
        assert "cross_tenant_data" not in clean
        assert "other_tenant_data" not in clean

    def test_password_blocked_in_task_message(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_password")
        msg = build_user_present_ws_task_message(case["input"])
        assert "password" not in msg

    def test_otp_blocked_in_task_message(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_otp")
        msg = build_user_present_ws_task_message(case["input"])
        assert "otp" not in msg

    def test_certificate_password_blocked_in_task_message(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "payload_hides_certificate_password")
        msg = build_user_present_ws_task_message(case["input"])
        assert "certificate_password" not in msg


# ── 5. local state_store 연동 ─────────────────────────────────────────────────


class TestLocalStateStore:
    def test_waiting_for_user_task_created(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_ws_test_001")
        result = create_local_user_present_task_from_ws(msg, store=fresh_store)
        assert result["ok"] is True
        assert result["task"]["state"] == STATE_WAITING_FOR_USER
        assert result["task"]["safe_to_execute"] is False

    def test_invalid_message_no_task_created(self, fresh_store):
        msg = {"tenant_id": "t1"}  # workflow_run_id 누락
        result = create_local_user_present_task_from_ws(msg, store=fresh_store)
        assert result["ok"] is False
        assert result["task"] is None

    def test_user_confirm_creates_confirmed_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_ws_confirm_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_ws_confirm_001", store=fresh_store)
        assert result["ok"] is True
        assert result["event"]["status"] == STATUS_USER_CONFIRMED
        assert result["event"]["safe_to_execute"] is False

    def test_user_cancel_creates_cancelled_event(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_ws_cancel_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_cancelled_and_build_event("wr_ws_cancel_001", store=fresh_store)
        assert result["ok"] is True
        assert result["event"]["status"] == STATUS_CANCELLED

    def test_blocked_task_confirm_fails(self, fresh_store):
        # BLOCKED 상태로 직접 task 생성 (WAITING → BLOCKED 전이 없이)
        task = fresh_store.create_user_present_task(  # noqa: F841
            {
                "workflow_run_id": "wr_ws_blocked_001",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
            }
        )
        fresh_store._update_state("wr_ws_blocked_001", STATE_BLOCKED)
        result = mark_local_user_confirmed_and_build_event("wr_ws_blocked_001", store=fresh_store)
        assert result["ok"] is False

    def test_cancelled_task_confirm_fails(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_ws_cancel_confirm_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        mark_local_user_cancelled_and_build_event("wr_ws_cancel_confirm_001", store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_ws_cancel_confirm_001", store=fresh_store)
        assert result["ok"] is False

    def test_user_confirmed_no_browser_action(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_ws_no_action_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_ws_no_action_001", store=fresh_store)
        # event에 browser action 관련 필드 없음
        event = result["event"]
        assert "click" not in event
        assert "type" not in event
        assert "submit" not in event
        assert event["safe_to_execute"] is False

    def test_user_confirmed_no_click_type_submit(self, fresh_store):
        msg = make_hometax_task_payload(workflow_run_id="wr_ws_hometax_confirm_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_ws_hometax_confirm_001", store=fresh_store)
        assert result["ok"] is True
        assert result["safe_to_execute"] is False


# ── 6. safe_to_execute 불변 속성 ──────────────────────────────────────────────


class TestSafeToExecuteInvariant:
    def test_task_message_safe_to_execute_always_false(self):
        msg = build_user_present_ws_task_message(
            {
                "workflow_run_id": "wr1",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "site_category": "bank",
                "target_domain": "kbstar.com",
                "safe_to_execute": True,  # 입력에 True가 들어와도
            }
        )
        assert msg["safe_to_execute"] is False  # 항상 False

    def test_status_event_safe_to_execute_always_false(self):
        event = build_user_present_ws_status_event(
            {
                "workflow_run_id": "wr1",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "status": STATUS_USER_CONFIRMED,
                "safe_to_execute": True,
            }
        )
        assert event["safe_to_execute"] is False

    def test_safe_to_execute_false_from_fixture(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "safe_to_execute_always_false")
        msg = build_user_present_ws_task_message(case["input"])
        assert msg["safe_to_execute"] is False

    def test_local_task_safe_to_execute_always_false(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_safe_invariant_001")
        result = create_local_user_present_task_from_ws(msg, store=fresh_store)
        assert result["task"]["safe_to_execute"] is False

    def test_confirmed_event_safe_to_execute_false(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_safe_confirm_001")
        create_local_user_present_task_from_ws(msg, store=fresh_store)
        result = mark_local_user_confirmed_and_build_event("wr_safe_confirm_001", store=fresh_store)
        assert result["safe_to_execute"] is False


# ── 7. in-memory test transport ───────────────────────────────────────────────


class TestInMemoryTransport:
    def test_no_real_websocket_connection(self, transport):
        assert transport.sent_count == 0
        assert transport.received_count == 0

    def test_send_receive_in_memory(self, transport):
        msg = make_bank_task_payload()
        transport.send(msg)
        assert transport.sent_count == 1
        assert transport.get_sent_messages()[0]["message_type"] == MSG_USER_PRESENT_TASK

    def test_push_inbound_and_receive(self, transport):
        msg = make_bank_task_payload()
        transport.push_inbound(msg)
        received = transport.receive()
        assert received is not None
        assert received["workflow_run_id"] == msg["workflow_run_id"]

    def test_transport_has_no_ws_url(self):
        import inspect

        from tests.helpers import local_agent_user_present_test_transport as mod

        src = inspect.getsource(mod)
        assert "websockets.connect" not in src
        assert "asyncio_websocket" not in src

    def test_get_sent_by_type(self, transport):
        msg = make_bank_task_payload()
        transport.send(msg)
        user_present_msgs = transport.get_sent_by_type(MSG_USER_PRESENT_TASK)
        assert len(user_present_msgs) == 1


# ── 8. 호환성 검증 ────────────────────────────────────────────────────────────


class TestCompatibility:
    def test_compatible_with_dispatch_dryrun(self):
        from ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun import (
            DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
            evaluate_browser_engine_routing_dispatch_dryrun,
        )

        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {
                "site_category": "bank",
                "target_domain": "kbstar.com",
                "operation_type": "read",
                "requires_certificate": True,
                "production_mode": False,
            }
        )
        assert result["dispatch_decision"] == DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
        # 해당 케이스에서 user-present task message 생성 가능
        msg = build_user_present_ws_task_message(
            {
                "workflow_run_id": "wr_compat_001",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "site_category": "bank",
                "target_domain": "kbstar.com",
                "target_url": "https://kbstar.com/",
            }
        )
        assert msg["message_type"] == MSG_USER_PRESENT_TASK
        assert msg["safe_to_execute"] is False

    def test_compatible_with_user_present_state_store(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_compat_store_001")
        result = create_local_user_present_task_from_ws(msg, store=fresh_store)
        assert result["ok"] is True
        task = fresh_store.get_user_present_task("wr_compat_store_001")
        assert task is not None
        assert task["state"] == STATE_WAITING_FOR_USER

    def test_ws_schema_no_conflict_with_browser_websocket_schema(self):
        from core.agent_runtime.browser.bridge.browser_websocket_schema import VALID_TASK_STATUS

        # browser_websocket_schema의 task status와 user_present status는 별개 enum
        assert "USER_CONFIRMED" not in VALID_TASK_STATUS
        assert "WAITING_FOR_USER" not in VALID_TASK_STATUS

    def test_validate_status_event_passes(self):
        event = build_user_present_ws_status_event(
            {
                "workflow_run_id": "wr1",
                "tenant_id": "t1",
                "user_id": "u1",
                "site_id": "s1",
                "status": STATUS_WAITING_FOR_USER,
                "status_reason": "",
            }
        )
        errors = validate_user_present_ws_status_event(event)
        assert errors == []


# ── 9. 보안 원칙 준수 ─────────────────────────────────────────────────────────


class TestSecurityPrinciples:
    def test_no_real_websocket_in_contract_source(self):
        import inspect

        import ai_orchestrator.contracts.user_present_ws_contract as mod

        src = inspect.getsource(mod)
        assert "websockets.connect" not in src
        assert "ws://" not in src
        assert "wss://" not in src

    def test_no_real_websocket_in_adapter_source(self):
        import inspect

        import core.agent_runtime.user_present.user_present_ws_adapter as mod

        src = inspect.getsource(mod)
        assert "websockets.connect" not in src
        assert "ws://" not in src

    def test_no_db_write_in_contract_source(self):
        import inspect

        import ai_orchestrator.contracts.user_present_ws_contract as mod

        src = inspect.getsource(mod)
        assert "INSERT INTO" not in src
        assert "session.commit()" not in src

    def test_no_browser_action_in_adapter_source(self):
        import inspect

        import core.agent_runtime.user_present.user_present_ws_adapter as mod

        src = inspect.getsource(mod)
        forbidden = ["page.click(", "page.fill(", "page.goto(", "page.type("]
        for token in forbidden:
            assert token not in src, f"금지된 코드 발견: {token}"

    def test_no_task_executor_in_adapter_source(self):
        import inspect

        import core.agent_runtime.user_present.user_present_ws_adapter as mod

        src = inspect.getsource(mod)
        assert "TaskExecutor(" not in src

    def test_user_visible_payload_sanitized(self, fresh_store):
        msg = make_bank_task_payload(workflow_run_id="wr_sanitize_visible_001")
        msg["internal_policy"] = "should_be_removed"
        result = create_local_user_present_task_from_ws(msg, store=fresh_store)
        assert result["ok"] is True
        sanitized = fresh_store.sanitize_user_present_task_for_user(result["task"])
        assert "internal_policy" not in sanitized
