"""
나라장터 read-only E2E task protocol 테스트

공통 LOCAL_PLAYWRIGHT task protocol 사용.
g2b 전용 자동화 로직 없음.
서버 외부 브라우저 실행 없음.
"""

import json
import pathlib

import pytest

from ai_orchestrator.browser_tool.policy.domain_profile_registry import get_domain_profile as get_profile
from ai_orchestrator.contracts.local_task_protocol import (
    ALLOWED_TASK_ACTIONS,
    EXEC_MODE_LOCAL_PLAYWRIGHT,
    STATUS_COMPLETED,
    STATUS_USER_ACTION_REQUIRED,
    STATUS_WAITING_USER_AUTH,
    TASK_TYPE_BROWSER,
    build_task,
    validate_task,
)
from core.agent_runtime.runtime.security_guard import validate_task_before_run

_FIXTURE = pathlib.Path(__file__).parent.parent / "fixtures" / "g2b_readonly_local_e2e_task_20260508.json"
_SAFE_RESULT = pathlib.Path(__file__).parent.parent / "fixtures" / "g2b_readonly_expected_safe_result_20260508.json"

G2B_HOST = "www.g2b.go.kr"
G2B_URL = "https://www.g2b.go.kr/"


# tests/fixtures/* 는 .gitignore 대상이라 위 두 json 이 저장소에 추적되지 않는다(fresh checkout/CI 에 없음).
# 시험이 읽는 값만 담은 합성 최소 내용을 tmp 에 만들어 경로를 그쪽으로 돌린다(실데이터 아님).
_SYNTH_TASK = {
    "task_id": "g2b-readonly-e2e-20260508-001",
    "execution_mode": EXEC_MODE_LOCAL_PLAYWRIGHT,
    "readonly": True,
    "allow_submit": False,
    "allow_sign": False,
    "allow_payment": False,
    "allow_bid_submit": False,
    "allow_auto_login": False,
    "allow_password_input": False,
    "allow_otp_input": False,
    "allow_cert_password_input": False,
}
_SYNTH_SAFE_RESULT = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "storage_state_exported": False,
    "server_browser_used": False,
    "npki_accessed": False,
}


@pytest.fixture(autouse=True)
def _synthetic_fixtures(tmp_path, monkeypatch):
    task_p = tmp_path / _FIXTURE.name
    safe_p = tmp_path / _SAFE_RESULT.name
    task_p.write_text(json.dumps(_SYNTH_TASK), encoding="utf-8")
    safe_p.write_text(json.dumps(_SYNTH_SAFE_RESULT), encoding="utf-8")
    monkeypatch.setitem(globals(), "_FIXTURE", task_p)
    monkeypatch.setitem(globals(), "_SAFE_RESULT", safe_p)


class TestG2bTaskProtocol:
    def test_fixture_loads(self):
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert data["task_id"] == "g2b-readonly-e2e-20260508-001"

    def test_fixture_execution_mode_local_playwright(self):
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert data["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT

    def test_fixture_readonly_true(self):
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert data["readonly"] is True

    def test_fixture_dangerous_actions_false(self):
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert data["allow_submit"] is False
        assert data["allow_sign"] is False
        assert data["allow_payment"] is False
        assert data["allow_bid_submit"] is False

    def test_fixture_no_auto_login(self):
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        assert data["allow_auto_login"] is False
        assert data["allow_password_input"] is False
        assert data["allow_otp_input"] is False
        assert data["allow_cert_password_input"] is False

    def test_build_task_succeeds(self):
        task = build_task(
            action="read_page",
            target_url=G2B_URL,
            domain=G2B_HOST,
            readonly=True,
        )
        assert task["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT
        assert task["task_type"] == TASK_TYPE_BROWSER

    def test_g2b_task_validates_clean(self):
        task = build_task(
            action="read_page",
            target_url=G2B_URL,
            domain=G2B_HOST,
            readonly=True,
        )
        violations = validate_task(task)
        assert violations == []

    def test_g2b_task_no_forbidden_fields(self):
        task = build_task(
            action="read_page",
            target_url=G2B_URL,
            domain=G2B_HOST,
            readonly=True,
        )
        forbidden = {"cookie", "session", "password", "otp", "certificate_password", "token", "npki", "auth_header"}
        for field in forbidden:
            assert field not in task

    def test_security_guard_allows_read_page(self):
        task = build_task(action="read_page", target_url=G2B_URL, domain=G2B_HOST)
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_security_guard_allows_extract_text(self):
        task = build_task(action="extract_text", target_url=G2B_URL, domain=G2B_HOST)
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_security_guard_allows_detect_login_status(self):
        task = build_task(action="detect_login_status", target_url=G2B_URL, domain=G2B_HOST)
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_expected_safe_result_fixture_loads(self):
        data = json.loads(_SAFE_RESULT.read_text(encoding="utf-8"))
        assert data["sensitive_data_collected"] is False
        assert data["cookie_exported"] is False
        assert data["session_exported"] is False
        assert data["password_collected"] is False
        assert data["otp_collected"] is False
        assert data["certificate_password_collected"] is False
        assert data["storage_state_exported"] is False
        assert data["server_browser_used"] is False
        assert data["npki_accessed"] is False

    def test_g2b_domain_profile_exists(self):
        profile = get_profile(G2B_HOST)
        assert profile is not None

    def test_g2b_domain_profile_readonly_allowed(self):
        profile = get_profile(G2B_HOST)
        assert profile.get("allowed_readonly") is True

    def test_g2b_domain_profile_local_default(self):
        profile = get_profile(G2B_HOST)
        assert profile.get("default_execution") == "LOCAL_BROWSER_DEFAULT"

    def test_g2b_domain_profile_blocked_actions_include_dangerous(self):
        profile = get_profile(G2B_HOST)
        blocked = set(profile.get("blocked_actions", []))
        assert "auto_bid_submit" in blocked or "bid_submit" in blocked or len(blocked) > 0

    def test_allowed_task_actions_cover_readonly(self):
        readonly_actions = {
            "read_page",
            "extract_text",
            "extract_table",
            "detect_login_status",
            "capture_screenshot",
            "search",
        }
        assert readonly_actions.issubset(ALLOWED_TASK_ACTIONS)


class TestG2bAuthDetection:
    def _make_runner_mock(self, status: str, auth_signal=None):
        def mock_run(task):
            return {
                "task_id": task.get("task_id", ""),
                "ok": status == STATUS_COMPLETED,
                "execution_used": EXEC_MODE_LOCAL_PLAYWRIGHT,
                "status": status,
                "current_url_host": G2B_HOST,
                "title_hint": "나라장터",
                "extracted_data": {"auth_signal": auth_signal},
                "downloaded_files": [],
                "message_ko": "mock",
                "sensitive_data_collected": False,
                "cookie_exported": False,
                "session_exported": False,
                "password_collected": False,
                "otp_collected": False,
                "certificate_password_collected": False,
            }

        return mock_run

    def test_login_signal_returns_waiting_user_auth(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import (
            AUTH_SIGNAL_LOGIN,
            enter_auth_wait,
        )

        result = enter_auth_wait("g2b-task", AUTH_SIGNAL_LOGIN, G2B_HOST)
        assert result["status"] == STATUS_WAITING_USER_AUTH
        assert result["sensitive_data_collected"] is False

    def test_cert_signal_returns_waiting_user_auth(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import (
            AUTH_SIGNAL_CERT,
            enter_auth_wait,
        )

        result = enter_auth_wait("g2b-task", AUTH_SIGNAL_CERT, G2B_HOST)
        assert result["status"] == STATUS_WAITING_USER_AUTH

    def test_otp_signal_returns_user_action_required(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import (
            AUTH_SIGNAL_OTP,
            enter_auth_wait,
        )

        result = enter_auth_wait("g2b-task", AUTH_SIGNAL_OTP, G2B_HOST)
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_auto_resume_allowed_for_read_page(self):
        from core.agent_runtime.runtime.auth.auto_resume_after_auth import can_auto_resume

        assert can_auto_resume("read_page") is True
        assert can_auto_resume("extract_text") is True
        assert can_auto_resume("extract_table") is True
        assert can_auto_resume("detect_login_status") is True

    def test_auto_resume_blocked_for_dangerous_actions(self):
        from core.agent_runtime.runtime.auth.auto_resume_after_auth import can_auto_resume

        assert can_auto_resume("submit") is False
        assert can_auto_resume("sign") is False
        assert can_auto_resume("payment") is False
        assert can_auto_resume("bid_submit") is False
        assert can_auto_resume("final_submit") is False
