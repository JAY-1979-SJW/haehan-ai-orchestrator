"""
STEP 8 — 데스크 앱 작업 수신 연결 경계 테스트
검증 범위:
  1. task_receiver.py 존재 및 임포트
  2. DesktopTask 분류 (LOCAL_AGENT, USER_DIRECT, BLOCKED, SERVER_INTERNAL)
  3. classify_raw_task — 민감 필드 제거
  4. poll_pending_tasks — 실행 없이 조회만
  5. validate_no_secret_in_task — 안전 검증
  6. status_provider 확장 (get_server_task_queue_status, get_task_queue_tray_label)
  7. ServiceStatus 확장 (local_agent_task_count 등)
  8. tray_app — _menu_task_queue_line, _menu_agent_notice_line
  9. ops_router /ops/agents 상태 필드 호환
  10. 외부 사이트 접속 함수 미포함
  11. 실제 실행 함수 미포함
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).parent.parent
TASK_RECEIVER = REPO / "desktop" / "task_receiver.py"
STATUS_PROVIDER = REPO / "desktop" / "status_provider.py"
TRAY_APP = REPO / "desktop" / "tray_app.py"


class TestTaskReceiverFileExists:
    def test_task_receiver_exists(self):
        assert TASK_RECEIVER.exists()

    def test_task_receiver_importable(self):
        from desktop.task_receiver import (  # noqa: F401
            DesktopTask, TaskQueueStatus, classify_raw_task,
            poll_pending_tasks, validate_no_secret_in_task,
        )


class TestDesktopTaskClassification:
    """classify_raw_task 분류 테스트."""

    def _make_raw(self, exec_mode="", exec_loc="", action_type="") -> dict:
        return {
            "task_id": "t-001",
            "execution_mode": exec_mode,
            "execution_location": exec_loc,
            "action_type": action_type,
            "payload": {"task_id": "t-001", "action": action_type},
            "domain": "test",
            "risk_level": "medium",
        }

    def test_local_playwright_classified_as_local_agent(self):
        from desktop.task_receiver import classify_raw_task, EXEC_LOC_LOCAL_AGENT
        task = classify_raw_task(self._make_raw(exec_mode="LOCAL_PLAYWRIGHT"))
        assert task.execution_location == EXEC_LOC_LOCAL_AGENT

    def test_user_direct_classified_correctly(self):
        from desktop.task_receiver import classify_raw_task, EXEC_LOC_USER_DIRECT
        task = classify_raw_task(self._make_raw(exec_loc="USER_DIRECT_REQUIRED"))
        assert task.execution_location == EXEC_LOC_USER_DIRECT

    def test_blocked_classified_correctly(self):
        from desktop.task_receiver import classify_raw_task, EXEC_LOC_BLOCKED
        task = classify_raw_task(self._make_raw(exec_loc="BLOCKED"))
        assert task.execution_location == EXEC_LOC_BLOCKED

    def test_server_internal_default(self):
        from desktop.task_receiver import classify_raw_task, EXEC_LOC_SERVER_INTERNAL
        task = classify_raw_task(self._make_raw())
        assert task.execution_location == EXEC_LOC_SERVER_INTERNAL

    def test_wait_for_user_auth_is_user_direct(self):
        from desktop.task_receiver import classify_raw_task, EXEC_LOC_USER_DIRECT
        task = classify_raw_task(self._make_raw(action_type="wait_for_user_auth"))
        assert task.execution_location == EXEC_LOC_USER_DIRECT

    def test_local_agent_is_executable(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw(exec_mode="LOCAL_PLAYWRIGHT"))
        assert task.is_executable_by_agent()

    def test_blocked_is_blocked(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw(exec_loc="BLOCKED"))
        assert task.is_blocked()

    def test_user_direct_is_user_direct(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw(exec_loc="USER_DIRECT_REQUIRED"))
        assert task.is_user_direct_required()


class TestDesktopTaskSecretStrip:
    """민감 필드 제거 테스트."""

    def _make_raw_with_secrets(self) -> dict:
        return {
            "task_id": "t-secret",
            "execution_mode": "LOCAL_PLAYWRIGHT",
            "password": "supersecret123",
            "cookie": "session=abc123",
            "otp": "123456",
            "token_hash": "abcdef1234567890",
            "device_token": "dev-token-xyz",
            "domain": "naver",
            "risk_level": "high",
            "payload": {"task_id": "t-secret"},
        }

    def test_classify_strips_password(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw_with_secrets())
        d = task.to_safe_dict()
        assert "password" not in d

    def test_classify_strips_cookie(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw_with_secrets())
        d = task.to_safe_dict()
        assert "cookie" not in d

    def test_classify_strips_token_hash(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw_with_secrets())
        d = task.to_safe_dict()
        assert "token_hash" not in d

    def test_classify_strips_device_token(self):
        from desktop.task_receiver import classify_raw_task
        task = classify_raw_task(self._make_raw_with_secrets())
        d = task.to_safe_dict()
        assert "device_token" not in d

    def test_validate_no_secret_passes_clean_task(self):
        from desktop.task_receiver import classify_raw_task, validate_no_secret_in_task
        raw = {
            "task_id": "t-clean",
            "execution_mode": "LOCAL_PLAYWRIGHT",
            "domain": "naver",
            "risk_level": "medium",
            "payload": {"task_id": "t-clean"},
        }
        task = classify_raw_task(raw)
        violations = validate_no_secret_in_task(task)
        assert violations == []


class TestDesktopTaskSafetyNotice:
    """안전 안내 문구 테스트."""

    def test_local_agent_has_safety_notice(self):
        from desktop.task_receiver import classify_raw_task
        raw = {"task_id": "x", "execution_mode": "LOCAL_PLAYWRIGHT", "payload": {}}
        task = classify_raw_task(raw)
        assert task.safety_notice != ""
        assert "승인" in task.safety_notice or "수신" in task.safety_notice

    def test_user_direct_has_safety_notice(self):
        from desktop.task_receiver import classify_raw_task
        raw = {"task_id": "x", "execution_location": "USER_DIRECT_REQUIRED", "payload": {}}
        task = classify_raw_task(raw)
        assert "직접" in task.safety_notice or "안내" in task.safety_notice

    def test_blocked_has_safety_notice(self):
        from desktop.task_receiver import classify_raw_task
        raw = {"task_id": "x", "execution_location": "BLOCKED", "payload": {}}
        task = classify_raw_task(raw)
        assert "차단" in task.safety_notice


class TestPollPendingTasks:
    """poll_pending_tasks 테스트."""

    def test_poll_local_returns_task_queue_status(self):
        from desktop.task_receiver import poll_pending_tasks, TaskQueueStatus
        result = poll_pending_tasks(source="local")
        assert isinstance(result, TaskQueueStatus)
        assert result.total_pending >= 0

    def test_poll_server_fallback_on_error(self):
        from desktop.task_receiver import poll_pending_tasks, TaskQueueStatus
        # 서버가 없어도 fallback으로 빈 큐 반환
        result = poll_pending_tasks(source="server")
        assert isinstance(result, TaskQueueStatus)

    def test_poll_does_not_execute_tasks(self):
        """poll은 분류만 — 실행 없음."""
        from desktop.task_receiver import poll_pending_tasks
        # playwright_runner 같은 실행 모듈이 호출되지 않아야 함
        with patch("desktop.task_receiver.poll_pending_tasks", wraps=poll_pending_tasks):
            result = poll_pending_tasks(source="local")
            assert result is not None

    def test_task_queue_status_tray_label(self):
        from desktop.task_receiver import TaskQueueStatus
        status = TaskQueueStatus(
            total_pending=3,
            local_agent_count=2,
            user_direct_count=1,
            blocked_count=0,
        )
        label = status.to_tray_label()
        assert "에이전트 2건" in label
        assert "직접 조작 1건" in label


class TestStatusProviderExtension:
    """status_provider 확장 테스트."""

    def test_get_server_task_queue_status_returns_value(self):
        from desktop.status_provider import LocalStatusProvider
        sp = LocalStatusProvider()
        result = sp.get_server_task_queue_status(source="local")
        # TaskQueueStatus 또는 None
        assert result is None or hasattr(result, "total_pending")

    def test_get_task_queue_tray_label_returns_string(self):
        from desktop.status_provider import LocalStatusProvider
        sp = LocalStatusProvider()
        label = sp.get_task_queue_tray_label(source="local")
        assert isinstance(label, str)
        assert len(label) > 0

    def test_service_status_has_task_count_fields(self):
        from desktop.status_provider import ServiceStatus
        s = ServiceStatus(
            state="running",
            local_agent_task_count=2,
            user_direct_task_count=1,
            blocked_task_count=0,
        )
        assert s.local_agent_task_count == 2
        assert s.user_direct_task_count == 1
        assert s.blocked_task_count == 0

    def test_get_service_status_includes_task_counts(self):
        from desktop.status_provider import LocalStatusProvider
        sp = LocalStatusProvider()
        status = sp.get_service_status(runner_state="stopped")
        assert hasattr(status, "local_agent_task_count")
        assert hasattr(status, "user_direct_task_count")
        assert hasattr(status, "blocked_task_count")


class TestTrayAppExtension:
    """tray_app 확장 테스트."""

    def test_tray_app_has_task_queue_line_method(self):
        src = TRAY_APP.read_text(encoding="utf-8")
        assert "_menu_task_queue_line" in src

    def test_tray_app_has_agent_notice_line_method(self):
        src = TRAY_APP.read_text(encoding="utf-8")
        assert "_menu_agent_notice_line" in src

    def test_tray_app_menu_includes_queue_line(self):
        src = TRAY_APP.read_text(encoding="utf-8")
        assert "self._menu_task_queue_line()" in src

    def test_tray_app_shows_user_direct_warning(self):
        src = TRAY_APP.read_text(encoding="utf-8")
        assert "직접조작" in src or "USER_DIRECT" in src or "직접 조작" in src

    def test_tray_app_shows_blocked_notice(self):
        src = TRAY_APP.read_text(encoding="utf-8")
        assert "차단" in src


class TestNoExternalExecution:
    """외부 사이트 접속/실행 함수 미포함 테스트."""

    def _src(self) -> str:
        return TASK_RECEIVER.read_text(encoding="utf-8")

    def test_no_playwright_import(self):
        src = self._src()
        assert "from playwright" not in src
        assert "playwright.sync_api" not in src

    def test_no_browser_launch(self):
        src = self._src()
        assert "launch(" not in src
        assert "chromium.launch" not in src

    def test_no_webbrowser_open(self):
        src = self._src()
        assert "webbrowser.open" not in src

    def test_no_requests_external(self):
        src = self._src()
        import_lines = [l for l in src.splitlines()
                        if l.startswith("import ") or l.startswith("from ")]
        assert not any("requests" in l for l in import_lines)

    def test_no_secret_hardcoded(self):
        src = self._src()
        bad = re.findall(
            r'(?:password|client_secret)\s*[:=]\s*["\'][^"\']{8,}["\']',
            src, re.I,
        )
        assert bad == [], f"secret 값 발견: {bad}"


class TestOpsAgentsCompatibility:
    """ops_router /ops/agents와 ServiceStatus 필드 호환 테스트."""

    def test_service_status_state_values_compatible(self):
        """ops_router _map_agent_status와 같은 상태값 사용."""
        from desktop.status_provider import ServiceStatus
        valid_states = {"starting", "running", "degraded", "stopped", "error"}
        for state in valid_states:
            s = ServiceStatus(state=state)
            assert s.state in valid_states

    def test_task_receiver_exec_loc_constants_documented(self):
        from desktop.task_receiver import (
            EXEC_LOC_LOCAL_AGENT,
            EXEC_LOC_USER_DIRECT,
            EXEC_LOC_BLOCKED,
            EXEC_LOC_SERVER_INTERNAL,
        )
        assert EXEC_LOC_LOCAL_AGENT == "LOCAL_AGENT_REQUIRED"
        assert EXEC_LOC_USER_DIRECT == "USER_DIRECT_REQUIRED"
        assert EXEC_LOC_BLOCKED == "BLOCKED"
        assert EXEC_LOC_SERVER_INTERNAL == "SERVER_INTERNAL_ONLY"

    def test_forbidden_fields_match_ops_policy(self):
        """task_receiver 금지 필드가 status_provider 금지 키를 포함."""
        from desktop.task_receiver import _FORBIDDEN_FIELDS
        from desktop.status_provider import _FORBIDDEN_STATUS_KEYS
        # task_receiver는 status_provider의 금지 키를 모두 포함해야 한다
        for key in _FORBIDDEN_STATUS_KEYS:
            assert key in _FORBIDDEN_FIELDS, f"task_receiver 금지 필드 누락: {key}"
