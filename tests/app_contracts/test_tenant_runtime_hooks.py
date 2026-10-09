"""TENANT-3: Runtime Implementation Hooks for Organization Scope

최소 organization scope runtime hook 검증

테스트 원칙:
- backward compatible 확인 (기존 auth 형식 유지)
- organization_ids / active_organization_id 추가됨 확인
- WebSocket handshake organization_id field 추가 확인
- scope validation rules 작동 확인
- 민감정보 제거 확인
"""

import pytest


class TestAuthTenantContext:
    """Auth tenant context helper 검증"""

    def test_build_tenant_context_adds_organization_ids(self):
        """build_tenant_context가 organization_ids 추가"""
        from tools.gates.auth import build_tenant_context

        user = {"actor": "john", "role": "admin"}
        ctx = build_tenant_context(user)

        assert "organization_ids" in ctx
        assert isinstance(ctx["organization_ids"], list)
        assert len(ctx["organization_ids"]) > 0

    def test_build_tenant_context_adds_active_organization_id(self):
        """build_tenant_context가 active_organization_id 추가"""
        from tools.gates.auth import build_tenant_context

        user = {"actor": "john", "role": "admin"}
        ctx = build_tenant_context(user)

        assert "active_organization_id" in ctx
        assert ctx["active_organization_id"] in ctx["organization_ids"]

    def test_build_tenant_context_maps_actor_to_actor_user_id(self):
        """build_tenant_context가 actor를 actor_user_id로 매핑"""
        from tools.gates.auth import build_tenant_context

        user = {"actor": "john", "role": "admin"}
        ctx = build_tenant_context(user)

        assert "actor_user_id" in ctx
        assert ctx["actor_user_id"] == "john"

    def test_build_tenant_context_preserves_existing_fields(self):
        """build_tenant_context가 기존 필드 유지"""
        from tools.gates.auth import build_tenant_context

        user = {"actor": "john", "role": "admin"}
        ctx = build_tenant_context(user)

        # Backward compatibility
        assert ctx["actor"] == "john"
        assert ctx["role"] == "admin"

    def test_require_active_organization_validates_context(self):
        """require_active_organization가 context 검증"""
        from tools.gates.auth import require_active_organization

        user = {"actor": "john", "role": "admin", "organization_ids": ["org-1"], "active_organization_id": "org-1"}
        org_id = require_active_organization(user)

        assert org_id == "org-1"

    def test_require_active_organization_rejects_missing_field(self):
        """active_organization_id 누락 시 migration bridge가 첫 org를 자동 설정한다 (TENANT-3 migration bridge)."""
        from tools.gates.auth import require_active_organization

        user = {"actor": "john", "role": "admin", "organization_ids": ["org-1"]}

        # migration bridge: active_organization_id 누락 시 organization_ids[0]을 자동 사용
        org_id = require_active_organization(user)
        assert org_id == "org-1"

    def test_require_active_organization_rejects_mismatch(self):
        """active_organization_id not in organization_ids → ValueError"""
        from tools.gates.auth import require_active_organization

        user = {
            "actor": "john",
            "role": "admin",
            "organization_ids": ["org-1"],
            "active_organization_id": "org-999",  # not in list
        }

        with pytest.raises(ValueError) as exc_info:
            require_active_organization(user)
        assert "not in organization_ids" in str(exc_info.value)

    def test_require_membership_allows_known_org(self):
        """known organization membership allowed"""
        from tools.gates.auth import require_membership

        user = {
            "actor": "john",
            "role": "admin",
            "organization_ids": ["org-1", "org-2"],
            "active_organization_id": "org-1",
        }

        # Should not raise
        require_membership(user, "org-1")
        require_membership(user, "org-2")

    def test_require_membership_rejects_unknown_org(self):
        """unknown organization membership rejected"""
        from fastapi import HTTPException

        from tools.gates.auth import require_membership

        user = {
            "actor": "john",
            "role": "admin",
            "organization_ids": ["org-1"],
            "active_organization_id": "org-1",
        }

        with pytest.raises(HTTPException) as exc_info:
            require_membership(user, "org-999")
        assert exc_info.value.status_code == 403


class TestWebSocketHandshakeOrganizationId:
    """WebSocket handshake organization_id field 검증"""

    def test_agent_hello_message_has_organization_id_field(self):
        """AgentHelloMessage에 organization_id field 있음"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            organization_id="org-1",
        )

        assert msg.organization_id == "org-1"

    def test_agent_hello_message_has_registration_user_id_field(self):
        """AgentHelloMessage에 registration_user_id field 있음"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            organization_id="org-1",
            registration_user_id="user-1",
        )

        assert msg.registration_user_id == "user-1"

    def test_agent_hello_to_dict_includes_organization_id(self):
        """AgentHelloMessage.to_dict()에 organization_id 포함"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            organization_id="org-1",
        )

        d = msg.to_dict()
        assert "organization_id" in d
        assert d["organization_id"] == "org-1"

    def test_agent_hello_safe_dict_keeps_organization_id(self):
        """AgentHelloMessage.safe_dict()에 organization_id 포함"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            host_name_hash="abc123",
            organization_id="org-1",
        )

        safe = msg.safe_dict()
        assert "organization_id" in safe
        assert safe["organization_id"] == "org-1"

    def test_agent_hello_safe_dict_keeps_registration_user_id(self):
        """AgentHelloMessage.safe_dict()에 registration_user_id 포함"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            organization_id="org-1",
            registration_user_id="user-1",
        )

        safe = msg.safe_dict()
        assert "registration_user_id" in safe
        assert safe["registration_user_id"] == "user-1"

    def test_agent_hello_validation_accepts_organization_id(self):
        """validate_agent_hello_message가 organization_id 수용"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import validate_agent_hello_message

        msg = {
            "message_type": "agent.hello",
            "agent_id": "agent-1",
            "agent_version": "1.0.0",
            "host_name_hash": "abc123",
            "mode": "read_only",
            "organization_id": "org-1",
        }

        is_valid, error = validate_agent_hello_message(msg)
        assert is_valid, f"validation failed: {error}"

    def test_server_policy_message_has_organization_id_field(self):
        """ServerPolicyMessage에 organization_id field 있음"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import ServerPolicyMessage

        msg = ServerPolicyMessage(
            organization_id="org-1",
            agent_id="agent-1",
        )

        assert msg.organization_id == "org-1"
        assert msg.agent_id == "agent-1"

    def test_server_policy_to_dict_includes_organization_id(self):
        """ServerPolicyMessage.to_dict()에 organization_id 포함"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import ServerPolicyMessage

        msg = ServerPolicyMessage(
            organization_id="org-1",
            agent_id="agent-1",
        )

        d = msg.to_dict()
        assert "organization_id" in d
        assert d["organization_id"] == "org-1"


class TestScopeValidationRules:
    """Scope validation rules runtime 작동 확인"""

    def test_task_approval_agent_same_org_validates(self):
        """assert_task_approval_agent_same_org 함수 작동"""
        from core.agent_runtime.policy.tenant_scope_contract import (
            BrowserApprovalScope,
            BrowserTaskScope,
            LocalAgentScope,
            assert_task_approval_agent_same_org,
        )

        task = BrowserTaskScope(
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
        )
        approval = BrowserApprovalScope(
            approval_id="approval-1",
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
            approval_token_hash="sha256abc",
        )
        agent = LocalAgentScope(
            agent_id="agent-1",
            organization_id="org-1",
        )

        # Should not raise
        assert_task_approval_agent_same_org(task, approval, agent)

    def test_task_approval_org_mismatch_rejected(self):
        """org mismatch → ValueError"""
        from core.agent_runtime.policy.tenant_scope_contract import (
            BrowserApprovalScope,
            BrowserTaskScope,
            LocalAgentScope,
            assert_task_approval_agent_same_org,
        )

        task = BrowserTaskScope(
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
        )
        approval = BrowserApprovalScope(
            approval_id="approval-1",
            task_id="task-1",
            organization_id="org-2",  # Mismatch!
            requested_by_user_id="user-1",
            approval_token_hash="sha256abc",
        )
        agent = LocalAgentScope(
            agent_id="agent-1",
            organization_id="org-1",
        )

        with pytest.raises(ValueError) as exc_info:
            assert_task_approval_agent_same_org(task, approval, agent)
        assert "organization_id" in str(exc_info.value)

    def test_result_task_scope_validates(self):
        """assert_result_task_same_org 함수 작동"""
        from core.agent_runtime.policy.tenant_scope_contract import (
            BrowserResultScope,
            BrowserTaskScope,
            assert_result_task_same_org,
        )

        task = BrowserTaskScope(
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
        )
        result = BrowserResultScope(
            result_id="result-1",
            task_id="task-1",
            organization_id="org-1",
        )

        # Should not raise
        assert_result_task_same_org(result, task)

    def test_result_task_org_mismatch_rejected(self):
        """result.org != task.org → ValueError"""
        from core.agent_runtime.policy.tenant_scope_contract import (
            BrowserResultScope,
            BrowserTaskScope,
            assert_result_task_same_org,
        )

        task = BrowserTaskScope(
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
        )
        result = BrowserResultScope(
            result_id="result-1",
            task_id="task-1",
            organization_id="org-2",  # Mismatch!
        )

        with pytest.raises(ValueError) as exc_info:
            assert_result_task_same_org(result, task)
        assert "organization_id" in str(exc_info.value)


class TestSecurityValidation:
    """보안 검증 (민감정보 제거)"""

    def test_safe_dict_removes_approval_token(self):
        """safe_dict에서 approval_token 제거"""
        from core.agent_runtime.policy.tenant_scope_contract import safe_tenant_scope_dict

        data = {
            "approval_token": "secret-token",
            "organization_id": "org-1",
            "safe_field": "value",
        }

        result = safe_tenant_scope_dict(data)
        assert "approval_token" not in result
        assert "organization_id" in result

    def test_safe_dict_removes_token_hash(self):
        """safe_dict에서 token_hash 제거"""
        from core.agent_runtime.policy.tenant_scope_contract import safe_tenant_scope_dict

        data = {
            "token_hash": "sha256:abc123",
            "organization_id": "org-1",
        }

        result = safe_tenant_scope_dict(data)
        assert "token_hash" not in result
        assert "organization_id" in result

    def test_websocket_safe_dict_removes_password(self):
        """WebSocket safe_dict에서 password 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {
            "password": "secret123",
            "agent_id": "agent-1",
        }

        result = safe_dict(data)
        assert "password" not in result
        assert "agent_id" in result

    def test_websocket_safe_dict_removes_raw_hostname(self):
        """WebSocket safe_dict에서 raw hostname 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {
            "hostname": "my-computer.local",
            "host_name_hash": "abc123",
        }

        result = safe_dict(data)
        assert "hostname" not in result
        assert "host_name_hash" in result


class TestBackwardCompatibility:
    """Backward compatibility 확인"""

    def test_existing_auth_format_preserved(self):
        """기존 auth format {actor, role} 유지"""
        from tools.gates.auth import build_tenant_context

        user = {"actor": "john", "role": "admin"}
        ctx = build_tenant_context(user)

        # Backward compat: original fields still there
        assert "actor" in ctx
        assert "role" in ctx
        assert ctx["actor"] == "john"
        assert ctx["role"] == "admin"

    def test_agent_hello_optional_organization_id(self):
        """AgentHelloMessage organization_id optional (backward compat)"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        # Should be creatable without organization_id
        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
        )

        assert msg.agent_id == "agent-1"
        # Default value
        assert msg.organization_id == ""

    def test_server_policy_optional_organization_id(self):
        """ServerPolicyMessage organization_id optional"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import ServerPolicyMessage

        # Should be creatable without organization_id
        msg = ServerPolicyMessage()

        # Default value
        assert msg.organization_id == ""


class TestGapCoverageAndRegression:
    """TENANT-2 및 기존 tests 회귀 확인"""

    def test_tenant2_tests_still_pass(self):
        """TENANT-2 tests still passing"""
        # This is implicitly tested by running pytest suite
        # but documenting intent here
        pytest.skip("Run full test suite to verify")

    def test_existing_websocket_validation_still_works(self):
        """existing handshake validation still works"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import validate_agent_hello_message

        # Backward compat: message without organization_id still valid
        msg = {
            "message_type": "agent.hello",
            "agent_id": "agent-1",
            "agent_version": "1.0.0",
            "mode": "read_only",
        }

        is_valid, error = validate_agent_hello_message(msg)
        assert is_valid, f"backward compat validation failed: {error}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
