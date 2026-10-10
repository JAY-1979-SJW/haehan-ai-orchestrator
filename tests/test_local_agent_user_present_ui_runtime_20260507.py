"""
로컬 Agent 사용자 직접 인증 UI 런타임 테스트 (2026-05-07)

테스트 대상:
- core/agent_runtime/user_present/user_present_state_store.py
- core/agent_runtime/user_present/user_present_ui_server.py

정책:
- safe_to_execute 항상 False
- HTML에 비밀번호/OTP/인증서 input 없음
- click/type/submit 코드 없음
- 민감 필드 sanitize 확인
- 상태 전이 규칙 준수
"""

from __future__ import annotations

import json
import pathlib

import pytest

# ── state store import ───────────────────────────────────────────────────────
from core.agent_runtime.user_present.user_present_state_store import (
    _USER_FORBIDDEN_KEYS,
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_TASK_RECEIVED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
    validate_user_present_task,
)

# ── FastAPI test client ───────────────────────────────────────────────────────

try:
    from fastapi.testclient import TestClient

    from core.agent_runtime.user_present.user_present_ui_server import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        create_app,
        run_server,
    )

    _UI_AVAILABLE = True
except ImportError:
    _UI_AVAILABLE = False


# ── fixture 로드 ─────────────────────────────────────────────────────────────

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "local_agent_user_present_ui_runtime_20260507.json"


@pytest.fixture(scope="session")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def store():
    s = UserPresentStateStore()
    yield s
    s.clear()


@pytest.fixture
def client(store):
    if not _UI_AVAILABLE:
        pytest.skip("fastapi not available")
    app = create_app(store, enable_html_ui=True)
    return TestClient(app, raise_server_exceptions=True)


def _make_task(store: UserPresentStateStore, wfid: str = "wf_test_001", **kwargs) -> dict:
    payload = {"workflow_run_id": wfid, "task_title": "테스트 작업", "site_category": "bank", **kwargs}
    return store.create_user_present_task(payload)


# ── STORE TESTS ───────────────────────────────────────────────────────────────


class TestStoreCreate:
    def test_create_sets_task_received_state(self, store):
        task = _make_task(store)
        assert task["state"] == STATE_TASK_RECEIVED

    def test_create_safe_to_execute_false(self, store):
        task = _make_task(store)
        assert task["safe_to_execute"] is False

    def test_create_safe_to_dispatch_false(self, store):
        task = _make_task(store)
        assert task["safe_to_dispatch"] is False

    def test_create_audit_required_true(self, store):
        task = _make_task(store)
        assert task["audit_required"] is True

    def test_create_strips_password(self, store):
        task = _make_task(store, password="secret123")
        assert "password" not in task

    def test_create_strips_otp(self, store):
        task = _make_task(store, otp="123456")
        assert "otp" not in task

    def test_create_strips_token(self, store):
        task = _make_task(store, token="bearer_xyz")
        assert "token" not in task

    def test_create_strips_cookie(self, store):
        task = _make_task(store, cookie="session=abc")
        assert "cookie" not in task

    def test_create_strips_certificate_password(self, store):
        task = _make_task(store, certificate_password="cert1234")
        assert "certificate_password" not in task

    def test_create_has_required_fields(self, store):
        task = _make_task(store)
        for field in [
            "workflow_run_id",
            "state",
            "safe_to_execute",
            "safe_to_dispatch",
            "audit_required",
            "created_at",
        ]:
            assert field in task

    def test_create_preserves_workflow_run_id(self, store):
        task = _make_task(store, wfid="wf_custom_999")
        assert task["workflow_run_id"] == "wf_custom_999"


class TestStoreStateTransitions:
    def test_mark_waiting_for_user(self, store):
        _make_task(store, wfid="wf_t1")
        task = store.mark_waiting_for_user("wf_t1")
        assert task["state"] == STATE_WAITING_FOR_USER

    def test_mark_waiting_safe_to_execute_false(self, store):
        _make_task(store, wfid="wf_t2")
        task = store.mark_waiting_for_user("wf_t2")
        assert task["safe_to_execute"] is False

    def test_confirm_from_waiting(self, store):
        _make_task(store, wfid="wf_t3")
        store.mark_waiting_for_user("wf_t3")
        task = store.mark_user_confirmed("wf_t3")
        assert task["state"] == STATE_USER_CONFIRMED

    def test_confirm_from_task_received_raises(self, store):
        _make_task(store, wfid="wf_t4")
        with pytest.raises(ValueError):
            store.mark_user_confirmed("wf_t4")

    def test_confirm_from_cancelled_raises(self, store):
        _make_task(store, wfid="wf_t5")
        store.mark_waiting_for_user("wf_t5")
        store.mark_user_cancelled("wf_t5")
        with pytest.raises(ValueError):
            store.mark_user_confirmed("wf_t5")

    def test_cancel_from_waiting(self, store):
        _make_task(store, wfid="wf_t6")
        store.mark_waiting_for_user("wf_t6")
        task = store.mark_user_cancelled("wf_t6")
        assert task["state"] == STATE_CANCELLED

    def test_cancel_from_task_received(self, store):
        _make_task(store, wfid="wf_t7")
        task = store.mark_user_cancelled("wf_t7")
        assert task["state"] == STATE_CANCELLED

    def test_cancel_from_confirmed_raises(self, store):
        _make_task(store, wfid="wf_t8")
        store.mark_waiting_for_user("wf_t8")
        store.mark_user_confirmed("wf_t8")
        with pytest.raises(ValueError):
            store.mark_user_cancelled("wf_t8")

    def test_confirmed_safe_to_execute_false(self, store):
        _make_task(store, wfid="wf_t9")
        store.mark_waiting_for_user("wf_t9")
        task = store.mark_user_confirmed("wf_t9")
        assert task["safe_to_execute"] is False

    def test_cancel_from_blocked(self, store):
        _make_task(store, wfid="wf_t10")
        store._update_state("wf_t10", STATE_BLOCKED)
        task = store.mark_user_cancelled("wf_t10")
        assert task["state"] == STATE_CANCELLED


class TestStoreSanitize:
    def test_sanitize_removes_password(self, store):
        task = {"workflow_run_id": "x", "state": "WAITING_FOR_USER", "password": "secret"}
        result = store.sanitize_user_present_task_for_user(task)
        assert "password" not in result

    def test_sanitize_removes_otp(self, store):
        task = {"workflow_run_id": "x", "state": "WAITING_FOR_USER", "otp": "123456"}
        result = store.sanitize_user_present_task_for_user(task)
        assert "otp" not in result

    def test_sanitize_removes_all_forbidden_keys(self, store):
        task = dict.fromkeys(_USER_FORBIDDEN_KEYS, "val")
        task["workflow_run_id"] = "x"
        result = store.sanitize_user_present_task_for_user(task)
        for key in _USER_FORBIDDEN_KEYS:
            assert key not in result

    def test_sanitize_preserves_safe_fields(self, store):
        task = {
            "workflow_run_id": "x",
            "state": "WAITING_FOR_USER",
            "task_title": "작업",
            "site_name": "은행",
            "created_at": "2026-05-07T00:00:00Z",
        }
        result = store.sanitize_user_present_task_for_user(task)
        assert result["workflow_run_id"] == "x"
        assert result["task_title"] == "작업"
        assert result["site_name"] == "은행"


class TestValidateTask:
    def test_valid_task_no_errors(self, store):
        task = _make_task(store, wfid="wf_v1")
        errors = validate_user_present_task(task)
        assert errors == []

    def test_missing_field_reports_error(self):
        task = {"workflow_run_id": "x", "state": "TASK_RECEIVED", "safe_to_execute": False, "safe_to_dispatch": False}
        errors = validate_user_present_task(task)
        assert any("audit_required" in e for e in errors)

    def test_safe_to_execute_true_reports_error(self):
        task = {
            "workflow_run_id": "x",
            "state": "TASK_RECEIVED",
            "safe_to_execute": True,
            "safe_to_dispatch": False,
            "audit_required": True,
            "created_at": "2026-05-07T00:00:00Z",
        }
        errors = validate_user_present_task(task)
        assert any("safe_to_execute" in e for e in errors)

    def test_forbidden_key_in_task_reports_error(self):
        task = {
            "workflow_run_id": "x",
            "state": "TASK_RECEIVED",
            "safe_to_execute": False,
            "safe_to_dispatch": False,
            "audit_required": True,
            "created_at": "2026-05-07T00:00:00Z",
            "password": "secret",
        }
        errors = validate_user_present_task(task)
        assert any("password" in e for e in errors)


# ── UI SERVER TESTS ───────────────────────────────────────────────────────────


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestServerConstants:
    def test_default_host_is_localhost(self):
        assert DEFAULT_HOST == "127.0.0.1"

    def test_default_port_is_18080(self):
        assert DEFAULT_PORT == 18080

    def test_run_server_rejects_0000(self):
        with pytest.raises(ValueError, match="0.0.0.0"):  # noqa: RUF043
            run_server(host="0.0.0.0", port=18080, store=UserPresentStateStore())


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestHealthEndpoint:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_safe_to_execute_false(self, client):
        r = client.get("/health")
        assert r.json()["safe_to_execute"] is False

    def test_health_host_field(self, client):
        r = client.get("/health")
        assert r.json()["host"] == "127.0.0.1"


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestTasksEndpoint:
    def test_list_tasks_empty(self, client):
        r = client.get("/tasks")
        data = r.json()
        assert data["tasks"] == []
        assert data["count"] == 0

    def test_list_tasks_safe_to_execute_false(self, client):
        r = client.get("/tasks")
        assert r.json()["safe_to_execute"] is False

    def test_list_tasks_with_task_no_sensitive(self, client, store):
        store.create_user_present_task(
            {
                "workflow_run_id": "wf_ui_01",
                "task_title": "은행 인증",
                "site_category": "bank",
                "password": "leaked",
                "otp": "111111",
            }
        )
        r = client.get("/tasks")
        tasks = r.json()["tasks"]
        assert len(tasks) == 1
        assert "password" not in tasks[0]
        assert "otp" not in tasks[0]

    def test_get_task_not_found(self, client):
        r = client.get("/tasks/nonexistent_wfid")
        assert r.status_code == 404

    def test_get_task_safe_to_execute_false(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_02", "site_category": "bank"})
        r = client.get("/tasks/wf_ui_02")
        assert r.json()["safe_to_execute"] is False


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestConfirmEndpoint:
    def test_confirm_from_waiting_redirects(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_03", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_03")
        r = client.post("/tasks/wf_ui_03/confirm", follow_redirects=False)
        assert r.status_code == 303

    def test_confirm_transitions_to_confirmed(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_04", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_04")
        client.post("/tasks/wf_ui_04/confirm")
        task = store.get_user_present_task("wf_ui_04")
        assert task["state"] == STATE_USER_CONFIRMED

    def test_confirm_from_task_received_returns_409(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_05", "site_category": "bank"})
        r = client.post("/tasks/wf_ui_05/confirm")
        assert r.status_code == 409

    def test_confirm_not_found_returns_404(self, client):
        r = client.post("/tasks/does_not_exist/confirm")
        assert r.status_code == 404


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestCancelEndpoint:
    def test_cancel_from_waiting_redirects(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_06", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_06")
        r = client.post("/tasks/wf_ui_06/cancel", follow_redirects=False)
        assert r.status_code == 303

    def test_cancel_transitions_to_cancelled(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_07", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_07")
        client.post("/tasks/wf_ui_07/cancel")
        task = store.get_user_present_task("wf_ui_07")
        assert task["state"] == STATE_CANCELLED

    def test_cancel_not_found_returns_404(self, client):
        r = client.post("/tasks/does_not_exist/cancel")
        assert r.status_code == 404


@pytest.mark.skipif(not _UI_AVAILABLE, reason="fastapi not available")
class TestIndexHtml:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_index_no_password_input_field(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_08", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_08")
        html = client.get("/").text
        assert 'type="password"' not in html
        assert "type='password'" not in html

    def test_index_no_otp_input_field(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_09", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_09")
        html = client.get("/").text
        assert 'name="otp"' not in html
        assert "name='otp'" not in html

    def test_index_no_certificate_password_input(self, client, store):
        store.create_user_present_task({"workflow_run_id": "wf_ui_10", "site_category": "bank"})
        store.mark_waiting_for_user("wf_ui_10")
        html = client.get("/").text
        assert 'name="certificate_password"' not in html


# ── 소스코드 정책 검사 ────────────────────────────────────────────────────────


class TestSourceCodePolicy:
    """소스 코드 내 금지 패턴 부재 검증."""

    SOURCE_FILES = [
        pathlib.Path(__file__).parent.parent / "core" / "agent_runtime" / "user_present" / "user_present_state_store.py",
        pathlib.Path(__file__).parent.parent / "core" / "agent_runtime" / "user_present" / "user_present_ui_server.py",
    ]

    def _read_all_source(self):
        return "\n".join(f.read_text(encoding="utf-8") for f in self.SOURCE_FILES)

    def test_no_playwright_click(self):
        src = self._read_all_source()
        assert "page.click(" not in src

    def test_no_playwright_type(self):
        src = self._read_all_source()
        assert "page.type(" not in src

    def test_no_playwright_fill(self):
        src = self._read_all_source()
        assert "page.fill(" not in src

    def test_no_playwright_submit(self):
        src = self._read_all_source()
        assert "page.submit(" not in src

    def test_no_cookie_extraction_code(self):
        src = self._read_all_source()
        assert "extract_cookie(" not in src
        assert "get_cookies(" not in src

    def test_no_otp_input_code(self):
        src = self._read_all_source()
        assert "input_otp(" not in src
        assert "fill_otp(" not in src

    def test_no_db_write(self):
        src = self._read_all_source()
        assert "db.write(" not in src
        assert "session.commit(" not in src

    def test_fixture_file_exists(self):
        assert FIXTURE_PATH.exists(), f"fixture 파일 없음: {FIXTURE_PATH}"

    def test_fixture_has_cases(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        assert len(data["cases"]) >= 16
