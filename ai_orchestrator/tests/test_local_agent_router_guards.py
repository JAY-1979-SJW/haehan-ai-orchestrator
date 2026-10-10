"""로컬 에이전트 router guards 모듈 테스트.

순수 helper 함수들과 상태 판별 로직의 정확성을 검증한다.
"""
import pytest
from ..agent_hub.models import LocalAgentTask
from ..agent_hub.router.guards import (
    is_capture_screenshot_task,
    task_is_dry_run,
    can_approve_task,
    can_reject_task,
    can_cancel_task,
    is_terminal_status,
    CANCELLABLE_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
)


class TestIsCaptureScreenshot:
    """is_capture_screenshot_task() 테스트."""

    def test_capture_screenshot_action_returns_true(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={}, risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert is_capture_screenshot_task(task) is True

    def test_other_action_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="open_url",
            params={}, risk_level="low", status="queued",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert is_capture_screenshot_task(task) is False

    def test_none_task_returns_false(self):
        assert is_capture_screenshot_task(None) is False


class TestTaskIsDryRun:
    """task_is_dry_run() 테스트."""

    def test_dry_run_true_returns_true(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={"options": {"dry_run": True}},
            risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert task_is_dry_run(task) is True

    def test_dry_run_false_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={"options": {"dry_run": False}},
            risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert task_is_dry_run(task) is False

    def test_no_options_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={},
            risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert task_is_dry_run(task) is False

    def test_no_params_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={},
            risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert task_is_dry_run(task) is False

    def test_none_task_returns_false(self):
        assert task_is_dry_run(None) is False

    def test_exception_in_params_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params="invalid",  # type: ignore
            risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert task_is_dry_run(task) is False


class TestCanApproveTask:
    """can_approve_task() 테스트."""

    def test_waiting_approval_and_high_risk_returns_true(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={}, risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_approve_task(task) is True

    def test_queued_and_high_risk_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={}, risk_level="high", status="queued",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_approve_task(task) is False

    def test_waiting_approval_and_low_risk_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="ping",
            params={}, risk_level="low", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_approve_task(task) is False

    def test_none_task_returns_false(self):
        assert can_approve_task(None) is False


class TestCanRejectTask:
    """can_reject_task() 테스트."""

    def test_waiting_approval_and_high_risk_returns_true(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={}, risk_level="high", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_reject_task(task) is True

    def test_queued_and_high_risk_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="capture_screenshot",
            params={}, risk_level="high", status="queued",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_reject_task(task) is False

    def test_waiting_approval_and_low_risk_returns_false(self):
        task = LocalAgentTask(
            task_id="lat-test", agent_id="la-test", action="ping",
            params={}, risk_level="low", status="waiting_approval",
            requested_by="admin", created_at="2026-05-04T00:00:00",
            updated_at="2026-05-04T00:00:00",
        )
        assert can_reject_task(task) is False

    def test_none_task_returns_false(self):
        assert can_reject_task(None) is False


class TestCanCancelTask:
    """can_cancel_task() 테스트."""

    @pytest.mark.parametrize("status", ["queued", "waiting_approval", "delivered", "running"])
    def test_cancellable_statuses_return_true(self, status):
        assert can_cancel_task(status) is True

    @pytest.mark.parametrize("status", ["completed", "failed", "rejected", "cancelled", "cancel_requested"])
    def test_non_cancellable_statuses_return_false(self, status):
        assert can_cancel_task(status) is False


class TestIsTerminalStatus:
    """is_terminal_status() 테스트."""

    @pytest.mark.parametrize("status", ["completed", "failed", "rejected", "cancelled"])
    def test_terminal_statuses_return_true(self, status):
        assert is_terminal_status(status) is True

    @pytest.mark.parametrize("status", ["queued", "waiting_approval", "delivered", "running", "cancel_requested"])
    def test_non_terminal_statuses_return_false(self, status):
        assert is_terminal_status(status) is False


class TestStatusMatrices:
    """상태 매트릭스 상수 테스트."""

    def test_cancellable_statuses_includes_expected(self):
        """취소 가능 상태가 예상 값을 포함."""
        expected = {"queued", "waiting_approval", "delivered", "running"}
        assert CANCELLABLE_TASK_STATUSES == expected

    def test_terminal_statuses_includes_expected(self):
        """종료 상태가 예상 값을 포함."""
        expected = {"completed", "failed", "rejected", "cancelled"}
        assert TERMINAL_TASK_STATUSES == expected

    def test_cancellable_and_terminal_disjoint(self):
        """취소 가능 상태와 종료 상태가 겹치지 않음."""
        assert CANCELLABLE_TASK_STATUSES.isdisjoint(TERMINAL_TASK_STATUSES)

    def test_cancel_requested_not_cancellable(self):
        """cancel_requested 상태는 다시 취소 불가."""
        assert "cancel_requested" not in CANCELLABLE_TASK_STATUSES
        assert "cancel_requested" not in TERMINAL_TASK_STATUSES


class TestImportSafety:
    """import 순환 참조 및 안전성 테스트."""

    def test_router_guards_imports_without_cycle(self):
        """router_guards 모듈이 순환 import 없이 로드됨."""
        # 이미 import된 상태에서 테스트 실행 중
        # 실패하면 순환 import 발생
        pass

    def test_guards_functions_not_none(self):
        """guard 함수들이 None이 아님."""
        assert is_capture_screenshot_task is not None
        assert task_is_dry_run is not None
        assert can_approve_task is not None
        assert can_reject_task is not None
        assert can_cancel_task is not None
        assert is_terminal_status is not None
