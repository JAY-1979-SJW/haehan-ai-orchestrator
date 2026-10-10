"""
auth_wait_controller 테스트
"""

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_AUTH_CANCELLED,
    STATUS_AUTH_COMPLETED,
    STATUS_AUTH_TIMEOUT,
    STATUS_AUTO_RESUME_READY,
    STATUS_USER_ACTION_REQUIRED,
    STATUS_WAITING_USER_AUTH,
)
from core.agent_runtime.runtime.auth.auth_wait_controller import (
    AUTH_SIGNAL_CERT,
    AUTH_SIGNAL_LOGIN,
    AUTH_SIGNAL_OTP,
    AuthWaitState,
    build_auth_completed_result,
    build_auto_resume_ready_result,
    build_cancel_result,
    build_timeout_result,
    enter_auth_wait,
)

TASK_ID = "test-task-001"


class TestEnterAuthWait:
    def test_login_required_returns_waiting_user_auth(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_LOGIN, "example.com")
        assert result["status"] == STATUS_WAITING_USER_AUTH

    def test_cert_auth_required_returns_waiting_user_auth(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_CERT, "example.com")
        assert result["status"] == STATUS_WAITING_USER_AUTH

    def test_otp_required_returns_user_action_required(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_OTP, "example.com")
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_guide_message_included(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_LOGIN)
        assert "인증이 필요합니다" in result["message_ko"]
        assert "비밀번호" in result["message_ko"]
        assert "OTP" in result["message_ko"]
        assert "인증서 비밀번호" in result["message_ko"]
        assert "자동으로 계속 진행" in result["message_ko"]

    def test_no_auto_input_flags(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_LOGIN)
        assert result.get("password_auto_input") is False
        assert result.get("otp_auto_input") is False
        assert result.get("cert_password_auto_input") is False

    def test_sensitive_data_not_collected(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_LOGIN)
        assert result.get("sensitive_data_collected") is False

    def test_ok_is_false(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_LOGIN)
        assert result["ok"] is False

    def test_task_id_preserved(self):
        result = enter_auth_wait(TASK_ID, AUTH_SIGNAL_CERT)
        assert result["task_id"] == TASK_ID


class TestTimeoutResult:
    def test_auth_timeout_status(self):
        result = build_timeout_result(TASK_ID, "example.com")
        assert result["status"] == STATUS_AUTH_TIMEOUT
        assert result["ok"] is False

    def test_timeout_message_includes_cancel(self):
        result = build_timeout_result(TASK_ID)
        assert "초과" in result["message_ko"]


class TestCancelResult:
    def test_auth_cancelled_status(self):
        result = build_cancel_result(TASK_ID)
        assert result["status"] == STATUS_AUTH_CANCELLED
        assert result["ok"] is False


class TestAuthCompletedResult:
    def test_auth_completed_status(self):
        result = build_auth_completed_result(TASK_ID, "example.com", ["login_required"])
        assert result["status"] == STATUS_AUTH_COMPLETED
        assert result["ok"] is True

    def test_signals_cleared_included(self):
        result = build_auth_completed_result(TASK_ID, signals_cleared=["cert_auth_required"])
        assert "cert_auth_required" in result.get("signals_cleared", [])

    def test_safe_to_resume_true(self):
        result = build_auth_completed_result(TASK_ID)
        assert result.get("safe_to_resume") is True

    def test_sensitive_data_not_collected(self):
        result = build_auth_completed_result(TASK_ID)
        assert result.get("sensitive_data_collected") is False


class TestAutoResumeReady:
    def test_auto_resume_ready_status(self):
        result = build_auto_resume_ready_result(TASK_ID, resumable_action="read_page")
        assert result["status"] == STATUS_AUTO_RESUME_READY
        assert result["ok"] is True


class TestAuthWaitState:
    def test_initial_not_cancelled(self):
        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=300)
        assert not state.is_cancelled()

    def test_cancel_sets_cancelled(self):
        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=300)
        state.cancel()
        assert state.is_cancelled()

    def test_not_timed_out_immediately(self):
        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=300)
        assert not state.is_timed_out()

    def test_timed_out_when_timeout_zero(self):
        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=0)
        assert state.is_timed_out()


class TestWaitForCompletion:
    def test_returns_cancel_result_when_cancelled(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import wait_for_completion

        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=300)
        state.cancel()
        result = wait_for_completion(state, lambda: {"auth_completed": False})
        assert result["status"] == STATUS_AUTH_CANCELLED

    def test_returns_timeout_result_when_timed_out(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import wait_for_completion

        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=0)
        result = wait_for_completion(state, lambda: {"auth_completed": False})
        assert result["status"] == STATUS_AUTH_TIMEOUT

    def test_returns_completed_when_detector_signals(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import wait_for_completion

        state = AuthWaitState(TASK_ID, AUTH_SIGNAL_LOGIN, timeout_sec=300)
        result = wait_for_completion(
            state,
            lambda: {"auth_completed": True, "signals_cleared": ["login_required"]},
            poll_interval_sec=0,
        )
        assert result["status"] == STATUS_AUTH_COMPLETED
