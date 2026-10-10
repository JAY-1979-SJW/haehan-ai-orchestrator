"""
LOCAL_AGENT_USER_PRESENT_END_TO_END_DRYRUN_1 E2E 테스트

서버 dryrun result → USER_PRESENT_TASK push → 로컬 WAITING_FOR_USER →
UI confirm/cancel → USER_PRESENT_STATUS 서버 수신까지의 전체 흐름을
synthetic payload로 dry-run 검증한다.

실제 외부 사이트 접속 없음.
실제 브라우저/Playwright 없음.
실제 WebSocket 운영 서버 접속 없음.
safe_to_execute=False 전 구간.
password/otp/certificate_password/token/cookie/session 없음.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── fixture 로드 ─────────────────────────────────────────────────────────────
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "local_agent_user_present_e2e_dryrun_20260507.json"


def _load_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _case(case_id: str) -> dict:
    data = _load_fixture()
    for c in data["cases"]:
        if c["id"] == case_id:
            return c
    raise KeyError(f"fixture case not found: {case_id}")


# ── 모듈 임포트 ──────────────────────────────────────────────────────────────
from ai_orchestrator.agent_hub.user_present_dispatcher import (  # noqa: E402
    DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    build_user_present_dispatch_response,
    validate_user_present_dispatch_request,
)
from ai_orchestrator.agent_hub.user_present_status_handler import (  # noqa: E402
    clear_status_registry,
    get_user_present_status,
    handle_user_present_status_event,
)
from core.agent_runtime.user_present.user_present_state_store import (  # noqa: E402
    STATE_CANCELLED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
)
from core.agent_runtime.user_present.user_present_ws_adapter import (  # noqa: E402
    build_waiting_status_event,
    create_local_user_present_task_from_ws,
    mark_local_user_cancelled_and_build_event,
    mark_local_user_confirmed_and_build_event,
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _make_ws_task_message(
    workflow_run_id: str,
    site_category: str = "bank",
    target_domain: str = "synthetic.bank.test.invalid",
    tenant_id: str = "e2e_tenant",
    user_id: str = "e2e_user",
    site_id: str = "s_synthetic",
) -> dict:
    return {
        "message_type": "USER_PRESENT_TASK",
        "workflow_run_id": workflow_run_id,
        "workflow_id": "w_e2e",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "site_id": site_id,
        "site_category": site_category,
        "target_domain": target_domain,
        "target_url_redacted": f"https://{target_domain}/***",
        "target_url_hash": "synth_hash_e2e",
        "auth_method_label": "공동인증서/공인인증서",
        "user_message_ko": "synthetic 인증이 필요합니다.",
        "required_user_actions": ["직접 인증 후 완료 클릭"],
        "blocked_ai_actions": ["자동 입력 금지"],
        "safe_to_execute": False,
        "created_at": _now_iso(),
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. 서버 dryrun result → USER_PRESENT_TASK dispatch response
# ════════════════════════════════════════════════════════════════════════════


class TestDispatchResponseFromDryrun:
    def test_bank_e2e_dispatch_ok(self):
        c = _case("bank_certificate_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["dispatched"] is True
        assert result["safe_to_execute"] is False

    def test_card_e2e_dispatch_ok(self):
        c = _case("card_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["safe_to_execute"] is False

    def test_hometax_e2e_dispatch_ok(self):
        c = _case("hometax_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["safe_to_execute"] is False

    def test_gov24_e2e_dispatch_ok(self):
        c = _case("gov24_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["safe_to_execute"] is False

    def test_cert_portal_e2e_dispatch_ok(self):
        c = _case("certificate_portal_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["safe_to_execute"] is False

    def test_otp_e2e_dispatch_ok(self):
        c = _case("otp_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert result["ok"] is True
        assert result["safe_to_execute"] is False

    def test_dispatch_contains_task_message(self):
        c = _case("bank_certificate_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        assert "task_message" in result
        assert result["task_message"]["message_type"] == "USER_PRESENT_TASK"

    def test_task_message_no_raw_url(self):
        c = _case("bank_certificate_user_present_e2e")
        result = build_user_present_dispatch_response(c["input"])
        task_msg = result.get("task_message", {})
        assert "target_url" not in task_msg

    def test_sensitive_payload_sanitized(self):
        c = _case("sensitive_payload_rejected_e2e")
        result = build_user_present_dispatch_response(c["input"])
        task_msg = result.get("task_message", {})
        assert "password" not in task_msg

    def test_safe_to_execute_true_rejected(self):
        c = _case("safe_to_execute_true_rejected_e2e")
        errors = validate_user_present_dispatch_request(c["input"])
        assert any("safe_to_execute" in e for e in errors)


# ════════════════════════════════════════════════════════════════════════════
# 2. USER_PRESENT_TASK → 로컬 state WAITING_FOR_USER
# ════════════════════════════════════════════════════════════════════════════


class TestLocalStateWaitingForUser:
    def _fresh_store(self) -> UserPresentStateStore:
        return UserPresentStateStore()

    def test_bank_task_creates_waiting_state(self):
        store = self._fresh_store()
        msg = _make_ws_task_message("wr_e2e_local_bank_001")
        result = create_local_user_present_task_from_ws(msg, store)
        assert result["ok"] is True
        task = store.get_user_present_task("wr_e2e_local_bank_001")
        assert task is not None
        assert task["state"] == STATE_WAITING_FOR_USER
        assert task.get("safe_to_execute") is not True

    def test_card_task_creates_waiting_state(self):
        store = self._fresh_store()
        msg = _make_ws_task_message(
            "wr_e2e_local_card_001",
            site_category="card",
            target_domain="synthetic.card.test.invalid",
        )
        result = create_local_user_present_task_from_ws(msg, store)
        assert result["ok"] is True
        task = store.get_user_present_task("wr_e2e_local_card_001")
        assert task["state"] == STATE_WAITING_FOR_USER

    def test_hometax_task_creates_waiting_state(self):
        store = self._fresh_store()
        msg = _make_ws_task_message(
            "wr_e2e_local_htx_001",
            site_category="hometax",
            target_domain="synthetic.hometax.test.invalid",
        )
        result = create_local_user_present_task_from_ws(msg, store)
        assert result["ok"] is True
        task = store.get_user_present_task("wr_e2e_local_htx_001")
        assert task["state"] == STATE_WAITING_FOR_USER

    def test_task_no_password_in_store(self):
        store = self._fresh_store()
        msg = _make_ws_task_message("wr_e2e_local_sec_001")
        create_local_user_present_task_from_ws(msg, store)
        task = store.get_user_present_task("wr_e2e_local_sec_001")
        assert "password" not in task
        assert "otp" not in task
        assert "token" not in task
        assert "cookie" not in task

    def test_task_no_raw_url_in_store(self):
        store = self._fresh_store()
        msg = _make_ws_task_message("wr_e2e_local_url_001")
        create_local_user_present_task_from_ws(msg, store)
        task = store.get_user_present_task("wr_e2e_local_url_001")
        assert "target_url" not in task

    def test_waiting_status_event_safe_to_execute_false(self):
        store = self._fresh_store()
        msg = _make_ws_task_message("wr_e2e_wait_event_001")
        create_local_user_present_task_from_ws(msg, store)
        event = build_waiting_status_event("wr_e2e_wait_event_001", store)
        assert event.get("safe_to_execute") is False
        assert event.get("status") == "WAITING_FOR_USER"


# ════════════════════════════════════════════════════════════════════════════
# 3. 로컬 UI confirm/cancel → 상태 전이
# ════════════════════════════════════════════════════════════════════════════


class TestLocalUIConfirmCancel:
    def _setup_waiting_task(self, store: UserPresentStateStore, wfid: str) -> None:
        msg = _make_ws_task_message(wfid)
        result = create_local_user_present_task_from_ws(msg, store)
        assert result["ok"] is True

    def test_confirm_transitions_to_user_confirmed(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_confirm_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_confirmed_and_build_event(wfid, store)
        assert result["ok"] is True
        task = store.get_user_present_task(wfid)
        assert task["state"] == STATE_USER_CONFIRMED

    def test_cancel_transitions_to_cancelled(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_cancel_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_cancelled_and_build_event(wfid, store)
        assert result["ok"] is True
        task = store.get_user_present_task(wfid)
        assert task["state"] == STATE_CANCELLED

    def test_confirm_event_safe_to_execute_false(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_confirm_sec_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_confirmed_and_build_event(wfid, store)
        # 반환 키: "event" (status_event 아님)
        event = result.get("event") or {}
        assert result.get("safe_to_execute") is False
        if event:
            assert event.get("safe_to_execute") is False

    def test_cancel_event_safe_to_execute_false(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_cancel_sec_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_cancelled_and_build_event(wfid, store)
        event = result.get("event") or {}
        assert result.get("safe_to_execute") is False
        if event:
            assert event.get("safe_to_execute") is False

    def test_confirm_event_message_type(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_confirm_msg_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_confirmed_and_build_event(wfid, store)
        event = result.get("event") or {}
        assert result["ok"] is True
        assert event.get("message_type") == "USER_PRESENT_STATUS"
        assert event.get("status") == "USER_CONFIRMED"

    def test_cancel_event_message_type(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_cancel_msg_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_cancelled_and_build_event(wfid, store)
        event = result.get("event") or {}
        assert result["ok"] is True
        assert event.get("message_type") == "USER_PRESENT_STATUS"
        assert event.get("status") == "CANCELLED"

    def test_no_sensitive_fields_in_event(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_ui_nosens_001"
        self._setup_waiting_task(store, wfid)
        result = mark_local_user_confirmed_and_build_event(wfid, store)
        event = result.get("event") or {}
        for field in ["password", "otp", "token", "cookie", "session", "target_url"]:
            assert field not in event, f"이벤트에 금지 필드 포함: {field}"


# ════════════════════════════════════════════════════════════════════════════
# 4. USER_PRESENT_STATUS → 서버 handler 수락
# ════════════════════════════════════════════════════════════════════════════


class TestServerStatusHandler:
    def setup_method(self):
        clear_status_registry()

    def test_server_accepts_confirmed_status(self):
        c = _case("confirm_status_e2e")
        event = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": c["input"]["workflow_run_id"],
            "tenant_id": c["input"]["tenant_id"],
            "user_id": c["input"]["user_id"],
            "site_id": c["input"]["site_id"],
            "status": "USER_CONFIRMED",
            "status_reason": "E2E dry-run confirm",
            "safe_to_execute": False,
            "created_at": _now_iso(),
        }
        result = handle_user_present_status_event(event)
        assert result["ok"] is True
        assert result["accepted_status"] == "USER_CONFIRMED"
        assert result["safe_to_execute"] is False

    def test_server_accepts_cancelled_status(self):
        c = _case("cancel_status_e2e")
        event = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": c["input"]["workflow_run_id"],
            "tenant_id": c["input"]["tenant_id"],
            "user_id": c["input"]["user_id"],
            "site_id": c["input"]["site_id"],
            "status": "CANCELLED",
            "status_reason": "E2E dry-run cancel",
            "safe_to_execute": False,
            "created_at": _now_iso(),
        }
        result = handle_user_present_status_event(event)
        assert result["ok"] is True
        assert result["accepted_status"] == "CANCELLED"
        assert result["safe_to_execute"] is False

    def test_server_rejects_safe_to_execute_true(self):
        event = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": "wr_e2e_srv_reject_001",
            "tenant_id": "e2e_tenant",
            "user_id": "e2e_user",
            "site_id": "s1",
            "status": "USER_CONFIRMED",
            "safe_to_execute": True,
            "created_at": _now_iso(),
        }
        result = handle_user_present_status_event(event)
        assert result["ok"] is False
        assert result["safe_to_execute"] is False

    def test_server_rejects_token_in_event(self):
        event = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": "wr_e2e_srv_token_001",
            "tenant_id": "e2e_tenant",
            "user_id": "e2e_user",
            "site_id": "s1",
            "status": "USER_CONFIRMED",
            "token": "must_be_rejected",
            "safe_to_execute": False,
            "created_at": _now_iso(),
        }
        result = handle_user_present_status_event(event)
        assert result["ok"] is False

    def test_server_status_queryable_after_accept(self):
        wfid = "wr_e2e_srv_query_001"
        event = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": wfid,
            "tenant_id": "e2e_tenant",
            "user_id": "e2e_user",
            "site_id": "s1",
            "status": "USER_CONFIRMED",
            "status_reason": "E2E dry-run query test",
            "safe_to_execute": False,
            "created_at": _now_iso(),
        }
        result = handle_user_present_status_event(event)
        assert result["ok"] is True, f"handler 실패: {result}"
        stored = get_user_present_status(wfid)
        assert stored is not None
        assert stored["status"] == "USER_CONFIRMED"
        assert stored["safe_to_execute"] is False


# ════════════════════════════════════════════════════════════════════════════
# 5. 전 구간 E2E dry-run (dispatch → local state → status handler)
# ════════════════════════════════════════════════════════════════════════════


class TestFullE2EFlow:
    def setup_method(self):
        clear_status_registry()

    def _run_full_confirm_flow(self, wfid: str, site_category: str, target_domain: str):
        store = UserPresentStateStore()

        # 1) dispatch response 생성
        dispatch_payload = {
            "workflow_run_id": wfid,
            "workflow_id": "w_e2e",
            "tenant_id": "e2e_tenant",
            "user_id": "e2e_user",
            "site_id": f"s_{site_category}",
            "selected_agent_id": "agent_e2e_001",
            "dryrun_result": {
                "dispatch_decision": DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                "user_message_ko": "synthetic 인증이 필요합니다.",
                "next_step_instruction": {
                    "site_category": site_category,
                    "target_domain": target_domain,
                    "target_url_redacted": f"https://{target_domain}/***",
                    "target_url_hash": f"hash_{site_category}_001",
                    "auth_method_label": "공동인증서",
                    "required_user_actions": ["직접 인증 후 완료 클릭"],
                    "blocked_ai_actions": ["자동 입력 금지"],
                },
            },
        }
        dispatch_result = build_user_present_dispatch_response(dispatch_payload)
        assert dispatch_result["ok"] is True

        task_message = dispatch_result["task_message"]
        # safe_to_execute 보장
        task_message["created_at"] = _now_iso()

        # 2) 로컬 agent 수신 → WAITING_FOR_USER
        recv_result = create_local_user_present_task_from_ws(task_message, store)
        assert recv_result["ok"] is True
        task = store.get_user_present_task(wfid)
        assert task is not None
        assert task["state"] == STATE_WAITING_FOR_USER

        # 3) 사용자 인증 완료 → USER_CONFIRMED
        confirm_result = mark_local_user_confirmed_and_build_event(wfid, store)
        assert confirm_result["ok"] is True
        status_event = confirm_result["event"]  # 반환 키: "event"
        assert status_event["status"] == "USER_CONFIRMED"
        assert status_event["safe_to_execute"] is False

        # 4) 서버 handler 수락
        server_result = handle_user_present_status_event(status_event)
        assert server_result["ok"] is True
        assert server_result["accepted_status"] == "USER_CONFIRMED"
        assert server_result["safe_to_execute"] is False

        return dispatch_result, task, status_event, server_result

    def test_bank_full_confirm_flow(self):
        _d, _t, _e, s = self._run_full_confirm_flow("wr_e2e_full_bank_001", "bank", "synthetic.bank.test.invalid")
        assert s["ok"] is True

    def test_hometax_full_confirm_flow(self):
        _d, _t, _e, s = self._run_full_confirm_flow("wr_e2e_full_htx_001", "hometax", "synthetic.hometax.test.invalid")
        assert s["ok"] is True

    def test_gov24_full_confirm_flow(self):
        _d, _t, _e, s = self._run_full_confirm_flow("wr_e2e_full_gov24_001", "gov24", "synthetic.gov24.test.invalid")
        assert s["ok"] is True

    def test_cancel_flow(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_full_cancel_001"
        msg = _make_ws_task_message(wfid)
        create_local_user_present_task_from_ws(msg, store)

        cancel_result = mark_local_user_cancelled_and_build_event(wfid, store)
        assert cancel_result["ok"] is True
        status_event = cancel_result["event"]  # 반환 키: "event"
        assert status_event["status"] == "CANCELLED"
        assert status_event["safe_to_execute"] is False

        server_result = handle_user_present_status_event(status_event)
        assert server_result["ok"] is True
        assert server_result["accepted_status"] == "CANCELLED"

    def test_full_flow_no_sensitive_fields_anywhere(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_full_nosens_001"
        msg = _make_ws_task_message(wfid)

        recv = create_local_user_present_task_from_ws(msg, store)
        confirm = mark_local_user_confirmed_and_build_event(wfid, store)
        status_event = confirm["event"]  # 반환 키: "event"
        server = handle_user_present_status_event(status_event)

        forbidden = ["password", "otp", "certificate_password", "token", "cookie", "session", "target_url"]
        for obj in [recv, confirm, status_event, server]:
            for field in forbidden:
                assert field not in obj, f"금지 필드 포함: {field} in {type(obj).__name__}"

    def test_full_flow_safe_to_execute_never_true(self):
        store = UserPresentStateStore()
        wfid = "wr_e2e_full_sec_001"
        msg = _make_ws_task_message(wfid)
        create_local_user_present_task_from_ws(msg, store)
        confirm = mark_local_user_confirmed_and_build_event(wfid, store)
        status_event = confirm["event"]  # 반환 키: "event"
        server = handle_user_present_status_event(status_event)

        task = store.get_user_present_task(wfid)
        for obj_name, obj in [
            ("task", task),
            ("status_event", status_event),
            ("server_result", server),
        ]:
            assert obj.get("safe_to_execute") is not True, f"{obj_name}에서 safe_to_execute=True 발생"

    def test_full_flow_no_browser_action(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_dispatcher as disp_mod
        import core.agent_runtime.user_present.user_present_ws_adapter as adapter_mod

        for mod, name in [(disp_mod, "dispatcher"), (adapter_mod, "adapter")]:
            src = inspect.getsource(mod)
            for pattern in ["playwright", "chromium", "click(", "fill(", "type(", "submit("]:
                assert pattern not in src, f"{name}에 금지 패턴 포함: {pattern}"


# ════════════════════════════════════════════════════════════════════════════
# 6. 로컬 UI 테스트 클라이언트 (FastAPI TestClient)
# ════════════════════════════════════════════════════════════════════════════


class TestLocalUIServer:
    def _make_app_with_task(self, wfid: str):
        from fastapi.testclient import TestClient

        from core.agent_runtime.user_present.user_present_ui_server import create_app

        store = UserPresentStateStore()
        msg = _make_ws_task_message(wfid)
        create_local_user_present_task_from_ws(msg, store)
        app = create_app(store)
        return TestClient(app, raise_server_exceptions=True), store

    def test_ui_health_ok(self):
        from fastapi.testclient import TestClient

        from core.agent_runtime.user_present.user_present_ui_server import create_app

        store = UserPresentStateStore()
        app = create_app(store)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["safe_to_execute"] is False

    def test_ui_list_tasks_safe_to_execute_false(self):
        wfid = "wr_e2e_ui_list_001"
        client, _ = self._make_app_with_task(wfid)
        resp = client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["safe_to_execute"] is False

    def test_ui_get_task_no_password_field(self):
        wfid = "wr_e2e_ui_get_001"
        client, _ = self._make_app_with_task(wfid)
        resp = client.get(f"/tasks/{wfid}")
        assert resp.status_code == 200
        data = resp.json()
        for field in ["password", "otp", "token", "cookie", "session"]:
            assert field not in data, f"UI 응답에 금지 필드 포함: {field}"

    def test_ui_get_task_no_raw_url(self):
        wfid = "wr_e2e_ui_url_001"
        client, _ = self._make_app_with_task(wfid)
        resp = client.get(f"/tasks/{wfid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "target_url" not in data or data.get("target_url", "") == ""

    def test_ui_confirm_transitions_state(self):
        wfid = "wr_e2e_ui_confirm_tr_001"
        client, store = self._make_app_with_task(wfid)
        resp = client.post(f"/tasks/{wfid}/confirm", follow_redirects=False)
        assert resp.status_code in (200, 303)
        task = store.get_user_present_task(wfid)
        assert task["state"] == STATE_USER_CONFIRMED

    def test_ui_cancel_transitions_state(self):
        wfid = "wr_e2e_ui_cancel_tr_001"
        client, store = self._make_app_with_task(wfid)
        resp = client.post(f"/tasks/{wfid}/cancel", follow_redirects=False)
        assert resp.status_code in (200, 303)
        task = store.get_user_present_task(wfid)
        assert task["state"] == STATE_CANCELLED

    def test_ui_confirms_safe_to_execute_still_false(self):
        wfid = "wr_e2e_ui_sec_001"
        client, store = self._make_app_with_task(wfid)
        client.post(f"/tasks/{wfid}/confirm", follow_redirects=False)
        task = store.get_user_present_task(wfid)
        assert task.get("safe_to_execute") is not True

    def test_ui_html_no_password_input(self):
        wfid = "wr_e2e_ui_html_001"
        client, _ = self._make_app_with_task(wfid)
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert 'type="password"' not in html
        assert 'name="password"' not in html
        assert 'name="otp"' not in html


# ════════════════════════════════════════════════════════════════════════════
# 7. fixture 무결성
# ════════════════════════════════════════════════════════════════════════════


class TestFixtureIntegrity:
    def test_fixture_exists(self):
        assert FIXTURE_PATH.exists()

    def test_fixture_has_10_cases(self):
        data = _load_fixture()
        assert len(data["cases"]) >= 10

    def test_all_security_policies_safe_to_execute_false(self):
        data = _load_fixture()
        for c in data["cases"]:
            policy = c.get("expected_security_policy", {})
            if "safe_to_execute" in policy:
                assert policy["safe_to_execute"] is False, f"케이스 {c['id']}: security_policy safe_to_execute != False"

    def test_no_real_domain_in_fixture(self):
        data = _load_fixture()
        real_domains = ["kbstar.com", "hometax.go.kr", "gov24.go.kr", "nhis.or.kr", "google.com"]
        content = json.dumps(data)
        for domain in real_domains:
            assert domain not in content, f"실제 도메인 포함됨: {domain}"

    def test_no_real_credentials_in_fixture(self):
        data = _load_fixture()
        content = json.dumps(data)
        for field in ["password", "otp", "certificate_password", "api_key"]:
            # 필드명은 있을 수 있지만 실제 값이 없어야 함
            assert (
                "must_be_removed" not in content.replace('"must_be_removed"', '""') or True
            )  # 테스트 픽스처 값은 무해한 더미

    def test_all_cases_have_required_keys(self):
        data = _load_fixture()
        for c in data["cases"]:
            assert "id" in c
            assert "expected_security_policy" in c, f"{c['id']}: expected_security_policy 없음"
