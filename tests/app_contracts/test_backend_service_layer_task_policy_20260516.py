"""Service Layer — TaskQueueService + ExecutionPolicyService 단위 테스트.

coverage:
- TaskQueueService: forbidden field strip, location count, validate
- ExecutionPolicyService: classification→decision, is_* helpers, decide_full
- PolicyDecision: to_dict 구조
- TaskQueueSummary: to_dict, tray_label
- 싱글턴 패턴
- security: forbidden field 차단 확인
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import guards
# ---------------------------------------------------------------------------


def test_services_package_importable():
    from ai_orchestrator.services import (
        ExecutionPolicyService,
        TaskQueueService,
    )

    assert TaskQueueService is not None
    assert ExecutionPolicyService is not None


def test_task_queue_service_singleton():
    from ai_orchestrator.services import get_task_queue_service

    a = get_task_queue_service()
    b = get_task_queue_service()
    assert a is b


def test_execution_policy_service_singleton():
    from ai_orchestrator.services import get_execution_policy_service

    a = get_execution_policy_service()
    b = get_execution_policy_service()
    assert a is b


# ---------------------------------------------------------------------------
# _FORBIDDEN_FIELDS strip
# ---------------------------------------------------------------------------


class TestForbiddenFieldStrip:
    def setup_method(self):
        from ai_orchestrator.services import get_task_queue_service

        self.svc = get_task_queue_service()

    def test_validate_clean_task_has_no_violations(self):
        task = {"task_id": "t1", "title": "계좌 조회", "provider": "bank"}
        violations = self.svc.validate_no_forbidden_fields(task)
        assert violations == []

    def test_validate_detects_top_level_forbidden(self):
        task = {"task_id": "t1", "token": "abc123"}
        violations = self.svc.validate_no_forbidden_fields(task)
        assert "token" in violations

    def test_validate_detects_payload_forbidden(self):
        task = {"task_id": "t1", "payload": {"password": "secret"}}
        violations = self.svc.validate_no_forbidden_fields(task)
        assert "payload.password" in violations

    def test_validate_case_insensitive(self):
        task = {"task_id": "t1", "TOKEN": "abc"}
        violations = self.svc.validate_no_forbidden_fields(task)
        assert "TOKEN" in violations

    def test_strip_removes_cookie(self):
        from ai_orchestrator.services.task_queue_service import _strip_forbidden

        raw = {"task_id": "t1", "cookie": "sess=abc", "title": "test"}
        result = _strip_forbidden(raw)
        assert "cookie" not in result
        assert result["title"] == "test"

    def test_strip_removes_nested_secret(self):
        from ai_orchestrator.services.task_queue_service import _strip_forbidden

        raw = {"task_id": "t1", "payload": {"access_token": "tok", "action": "read"}}
        result = _strip_forbidden(raw)
        assert "access_token" not in result["payload"]
        assert result["payload"]["action"] == "read"


# ---------------------------------------------------------------------------
# TaskQueueSummary
# ---------------------------------------------------------------------------


class TestTaskQueueSummary:
    def test_to_dict_keys(self):
        from ai_orchestrator.services.task_queue_service import TaskQueueSummary

        s = TaskQueueSummary(total_pending=5, server_internal_count=3, local_agent_count=1, user_direct_count=1)
        d = s.to_dict()
        assert set(d.keys()) == {
            "total_pending",
            "server_internal_count",
            "local_agent_count",
            "user_direct_count",
            "blocked_count",
        }

    def test_tray_label_empty(self):
        from ai_orchestrator.services.task_queue_service import TaskQueueSummary

        s = TaskQueueSummary()
        assert s.tray_label() == "수신 작업: 대기 없음"

    def test_tray_label_with_agent(self):
        from ai_orchestrator.services.task_queue_service import TaskQueueSummary

        s = TaskQueueSummary(local_agent_count=2)
        assert "에이전트 2건" in s.tray_label()

    def test_tray_label_with_blocked(self):
        from ai_orchestrator.services.task_queue_service import TaskQueueSummary

        s = TaskQueueSummary(blocked_count=1)
        assert "차단 1건" in s.tray_label()


# ---------------------------------------------------------------------------
# PolicyDecision
# ---------------------------------------------------------------------------


class TestPolicyDecision:
    def test_to_dict_has_required_keys(self):
        from ai_orchestrator.services.execution_policy_service import PolicyDecision

        d = PolicyDecision(
            execution_location="SERVER_INTERNAL_ONLY",
            server_executable=True,
            requires_local_agent=False,
            requires_user_direct=False,
            requires_oauth_setup=False,
            is_external_app_hold=False,
            is_blocked=False,
            requires_secret_redaction=False,
            reason="test",
        ).to_dict()
        required = {
            "execution_location",
            "server_executable",
            "requires_local_agent",
            "requires_user_direct",
            "requires_oauth_setup",
            "is_external_app_hold",
            "is_blocked",
            "requires_secret_redaction",
            "reason",
            "classification",
            "risk_level",
        }
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# ExecutionPolicyService — classification helpers
# ---------------------------------------------------------------------------


class TestExecutionPolicyClassificationHelpers:
    def setup_method(self):
        from ai_orchestrator.services import get_execution_policy_service

        self.svc = get_execution_policy_service()

    def test_server_readonly_is_server_executable(self):
        assert self.svc.is_server_executable("SERVER_READONLY_ALLOWED") is True

    def test_local_agent_required_classification(self):
        assert self.svc.is_local_agent_required("LOCAL_AGENT_REQUIRED") is True
        assert self.svc.is_local_agent_required("SERVER_READONLY_ALLOWED") is False

    def test_user_direct_required_classification(self):
        assert self.svc.is_user_direct_required("USER_DIRECT_REQUIRED") is True
        assert self.svc.is_user_direct_required("IN_SCOPE") is False

    def test_oauth_required_classification(self):
        assert self.svc.is_oauth_required("OFFICIAL_API_OR_OAUTH_REQUIRED") is True
        assert self.svc.is_oauth_required("IN_SCOPE") is False

    def test_external_app_hold_classification(self):
        assert self.svc.is_external_app_hold("EXTERNAL_APP_HOLD") is True
        assert self.svc.is_external_app_hold("IN_SCOPE") is False

    def test_blocked_classification_hold(self):
        assert self.svc.is_blocked_classification("EXTERNAL_APP_HOLD") is True

    def test_blocked_classification_future(self):
        assert self.svc.is_blocked_classification("FUTURE_INTEGRATION") is True

    def test_blocked_classification_quarantine(self):
        assert self.svc.is_blocked_classification("QUARANTINE_OR_HOLD") is True

    def test_in_scope_not_blocked(self):
        assert self.svc.is_blocked_classification("IN_SCOPE") is False


# ---------------------------------------------------------------------------
# ExecutionPolicyService — classification_to_decision
# ---------------------------------------------------------------------------


class TestClassificationToDecision:
    def setup_method(self):
        from ai_orchestrator.services import get_execution_policy_service

        self.svc = get_execution_policy_service()

    def _decide(self, cls):
        return self.svc._classification_to_decision(cls)

    def test_in_scope_server_executable(self):
        d = self._decide("IN_SCOPE")
        assert d.server_executable is True
        assert d.is_blocked is False
        assert d.requires_local_agent is False

    def test_local_agent_required(self):
        d = self._decide("LOCAL_AGENT_REQUIRED")
        assert d.requires_local_agent is True
        assert d.execution_location == "LOCAL_AGENT_REQUIRED"
        assert d.requires_secret_redaction is True

    def test_user_direct_required(self):
        d = self._decide("USER_DIRECT_REQUIRED")
        assert d.requires_user_direct is True
        assert d.execution_location == "USER_DIRECT_REQUIRED"
        assert d.requires_secret_redaction is True

    def test_oauth_required(self):
        d = self._decide("OFFICIAL_API_OR_OAUTH_REQUIRED")
        assert d.requires_oauth_setup is True
        assert d.server_executable is True  # OAuth 완료 후 서버 실행 가능
        assert d.is_blocked is False

    def test_external_app_hold_blocked(self):
        d = self._decide("EXTERNAL_APP_HOLD")
        assert d.is_external_app_hold is True
        assert d.is_blocked is True
        assert d.execution_location == "BLOCKED"

    def test_future_integration_blocked(self):
        d = self._decide("FUTURE_INTEGRATION")
        assert d.is_blocked is True
        assert d.execution_location == "BLOCKED"

    def test_quarantine_blocked(self):
        d = self._decide("QUARANTINE_OR_HOLD")
        assert d.is_blocked is True
        assert d.execution_location == "BLOCKED"


# ---------------------------------------------------------------------------
# decide_full — explicit execution_location path
# ---------------------------------------------------------------------------


class TestDecideFull:
    def setup_method(self):
        from ai_orchestrator.services import get_execution_policy_service

        self.svc = get_execution_policy_service()

    def test_explicit_server_internal(self):
        task = {"execution_location": "SERVER_INTERNAL_ONLY"}
        d = self.svc.decide_full(task)
        assert d.execution_location == "SERVER_INTERNAL_ONLY"
        assert d.server_executable is True

    def test_explicit_blocked(self):
        task = {"execution_location": "BLOCKED"}
        d = self.svc.decide_full(task)
        assert d.is_blocked is True

    def test_explicit_local_agent(self):
        task = {"execution_location": "LOCAL_AGENT_REQUIRED"}
        d = self.svc.decide_full(task)
        assert d.requires_local_agent is True
        assert d.requires_secret_redaction is True

    def test_no_location_defaults_server(self):
        task = {"task_id": "t1", "title": "조회"}
        d = self.svc.decide_full(task)
        # guard 미설정 환경에서 기본 SERVER_INTERNAL_ONLY 반환
        assert d.execution_location in (
            "SERVER_INTERNAL_ONLY",
            "LOCAL_AGENT_REQUIRED",
            "USER_DIRECT_REQUIRED",
            "BLOCKED",
        )
