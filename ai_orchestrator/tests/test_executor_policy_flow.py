"""executor.py 정책 흐름 통합 테스트 (Stage 4B).

plan.allowed / requires_approval / rate_limits / execution_policy / whitelist / timeout
각 게이트에서 mock 기반으로 정책 강제를 검증한다.
실제 worker 호출은 발생하지 않고, 모든 차단/승인/실행 로직은 mock으로 확인한다.
"""

from unittest.mock import Mock, patch

from ai_orchestrator.core.models import ExecutionPlan, TaskRequest
from ai_orchestrator.tasks import executor


def _req(task_id="task-1", action="test_action", **kwargs):
    """테스트용 TaskRequest 생성 헬퍼"""
    defaults = {
        "task_id": task_id,
        "source": "manual",
        "action_type": action,
        "target": "target",
        "description": "test",
        "requested_by": "user",
        "payload": {},
    }
    defaults.update(kwargs)
    return TaskRequest(**defaults)


class TestExecutorPolicyBlockedPlan:
    """A. plan.allowed=False 테스트"""

    def test_blocked_plan_returns_blocked_immediately(self):
        """blocked plan은 worker 호출 없이 BLOCKED 반환"""
        plan = ExecutionPlan(
            task_id="task-1",
            allowed=False,
            requires_approval=False,
            steps=[],
            blocked_reasons=["차단 경로 일치"],
        )
        req = _req()
        worker = Mock(return_value="SHOULD_NOT_CALL")

        result = executor.execute(plan, req=req, risk_level="low", worker=worker)

        assert result.startswith("BLOCKED:")
        worker.assert_not_called()

    def test_blocked_plan_logs_reasons(self):
        """blocked_reasons가 로그에 기록됨"""
        plan = ExecutionPlan(
            task_id="task-2",
            allowed=False,
            requires_approval=False,
            steps=[],
            blocked_reasons=["이유1", "이유2"],
        )
        with patch("ai_orchestrator.tasks.executor.logger") as mock_logger:
            executor.execute(plan)
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "task-2" in call_args or "blocked_reasons" in call_args


class TestExecutorPolicyRequiresApproval:
    """B. plan.requires_approval=True 테스트"""

    def test_requires_approval_returns_pending(self):
        """requires_approval=True 시 PENDING_APPROVAL 반환, worker 호출 없음"""
        plan = ExecutionPlan(
            task_id="task-3",
            allowed=True,
            requires_approval=True,
            steps=[],
            blocked_reasons=[],
        )
        req = _req()
        worker = Mock(return_value="SHOULD_NOT_CALL")

        result = executor.execute(plan, req=req, risk_level="medium", worker=worker)

        assert result == "PENDING_APPROVAL"
        worker.assert_not_called()


class TestExecutorPolicyHighCriticalRisk:
    """C. risk_level high/critical 테스트"""

    def test_critical_risk_auto_blocked(self):
        """critical risk는 execute_task에서 자동 차단"""
        req = _req(task_id="task-4", action="critical_action")
        worker = Mock(return_value="SHOULD_NOT_CALL")

        result = executor.execute_task(req, risk_level="critical", worker=worker)

        assert "BLOCKED:" in result
        assert "critical_not_allowed" in result
        worker.assert_not_called()

    def test_high_risk_auto_blocked(self):
        """high risk는 execute_task에서 자동 차단"""
        req = _req(task_id="task-5", action="high_action")
        worker = Mock(return_value="SHOULD_NOT_CALL")

        result = executor.execute_task(req, risk_level="high", worker=worker)

        assert "BLOCKED:" in result
        assert "high_not_allowed" in result
        worker.assert_not_called()


class TestExecutorPolicyRateLimit:
    """D. check_rate_limits 차단 테스트"""

    def test_rate_limit_blocks_execution(self):
        """rate limit 실패 시 BLOCKED 반환, worker 호출 없음"""
        req = _req(task_id="task-6")
        worker = Mock(return_value="SHOULD_NOT_CALL")

        with patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_check:
            mock_check.return_value = (False, "rate_limited_action")

            result = executor.execute_task(req, risk_level="low", worker=worker)

            assert "BLOCKED:" in result
            assert "rate_limited_action" in result
            worker.assert_not_called()

    def test_rate_limit_recorded(self):
        """rate limit 차단 시 record_execution 호출"""
        req = _req(task_id="task-7")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_check,
            patch("ai_orchestrator.tasks.executor.record_execution") as mock_record,
        ):
            mock_check.return_value = (False, "rate_limited_user")

            executor.execute_task(req, risk_level="low")

            mock_record.assert_called()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["status"].startswith("BLOCKED:")


class TestExecutorPolicyExecutionPolicy:
    """E. check_execution_policy 차단 테스트"""

    def test_execution_policy_blocks_execution(self):
        """execution policy (cooldown/5min/night) 차단 시 BLOCKED 반환"""
        req = _req(task_id="task-8")
        worker = Mock(return_value="SHOULD_NOT_CALL")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (False, "task_cooldown")

            result = executor.execute_task(req, risk_level="medium", worker=worker)

            assert "BLOCKED:" in result
            assert "task_cooldown" in result
            worker.assert_not_called()

    def test_night_block_enforced(self):
        """야간 차단이 작동"""
        req = _req(task_id="task-9")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (False, "night_blocked")

            result = executor.execute_task(req, risk_level="medium")

            assert "night_blocked" in result


class TestExecutorPolicyWhitelist:
    """F. whitelist 차단 테스트"""

    def test_whitelist_blocks_non_allowed_action(self):
        """whitelist 미등록 action은 worker 미제공 시 차단"""
        req = _req(task_id="task-10", action="unknown_action")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (True, "")

            result = executor.execute_task(req, risk_level="low", worker=None)

            assert "BLOCKED:" in result
            assert "not_allowed_action" in result

    def test_whitelist_allows_registered_actions(self):
        """ALLOWED_ACTIONS에 등록된 액션은 통과 (워커는 mock)"""
        req = _req(task_id="task-11", action="get_server_status")
        mock_worker = Mock(return_value="mock_result")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
            patch("ai_orchestrator.tasks.executor.run_with_timeout") as mock_timeout,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (True, "")
            mock_timeout.return_value = "mock_result"

            result = executor.execute_task(req, risk_level="low", worker=mock_worker)

            assert result == "mock_result"

    def test_whitelist_bypass_with_explicit_worker(self):
        """worker 명시 제공 시 whitelist 검사 skip (테스트/예외 경로)"""
        req = _req(task_id="task-12", action="unknown_action")
        mock_worker = Mock(return_value="custom_result")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
            patch("ai_orchestrator.tasks.executor.run_with_timeout") as mock_timeout,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (True, "")
            mock_timeout.return_value = "custom_result"

            result = executor.execute_task(req, risk_level="low", worker=mock_worker)

            assert result == "custom_result"


class TestExecutorPolicyTimeout:
    """G. timeout 강제 테스트"""

    def test_timeout_blocks_execution(self):
        """timeout 발생 시 BLOCKED:execution_timeout 반환"""
        req = _req(task_id="task-13")

        def slow_worker(req):
            raise TimeoutError("exceeded timeout")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (True, "")

            result = executor.execute_task(req, risk_level="low", worker=slow_worker)

            assert "BLOCKED:" in result
            assert "execution_timeout" in result

    def test_timeout_recorded(self):
        """timeout 발생 시 record_execution 호출"""
        req = _req(task_id="task-14")

        def timeout_worker(req):
            raise TimeoutError("timeout")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
            patch("ai_orchestrator.tasks.executor.record_execution") as mock_record,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (True, "")

            executor.execute_task(req, risk_level="low", worker=timeout_worker)

            mock_record.assert_called()
            call_kwargs = mock_record.call_args[1]
            assert "execution_timeout" in call_kwargs["status"]


class TestExecutorPolicyFlow:
    """정책 흐름 순서 검증: 어느 게이트도 우회 불가"""

    def test_rate_limit_before_whitelist(self):
        """rate_limit이 whitelist 검사보다 먼저 실행"""
        req = _req(task_id="task-16", action="unknown_action")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (False, "rate_limited_action")
            mock_policy.return_value = (True, "")

            result = executor.execute_task(req, risk_level="low")

            assert "rate_limited_action" in result

    def test_execution_policy_before_whitelist(self):
        """execution_policy가 whitelist 검사보다 먼저 실행"""
        req = _req(task_id="task-17", action="unknown_action")

        with (
            patch("ai_orchestrator.tasks.executor.check_rate_limits") as mock_rate,
            patch("ai_orchestrator.tasks.executor.check_execution_policy") as mock_policy,
        ):
            mock_rate.return_value = (True, "")
            mock_policy.return_value = (False, "task_cooldown")

            result = executor.execute_task(req, risk_level="low")

            assert "task_cooldown" in result
