"""TENANT-2: Minimal Organization Scope Schema 검증 테스트

TENANT-1 P1 Gap (G1~G13)을 코드 계약으로 변환하고 검증한다.

테스트 원칙:
- gap documented 스타일로 검증 (현재 코드에 없어도 OK, 설계문서 있으면 OK)
- contract file이 존재하고 기본 원칙을 따르는지 확인
- schema proposal이 gap을 다루는지 확인
"""

from pathlib import Path

import pytest


class TestTenantMinimalSchemaProposal:
    """TENANT-2 schema proposal 파일 존재 확인"""

    def test_tenant_schema_report_exists(self):
        """Schema proposal 문서 존재"""
        report_file = Path("docs/reports/tenant_2_minimal_scope_schema_proposal.md")
        assert report_file.exists(), "tenant_2_minimal_scope_schema_proposal.md must exist"

    def test_schema_report_mentions_all_entities(self):
        """Schema에 필수 entity 포함"""
        report_file = Path("docs/reports/tenant_2_minimal_scope_schema_proposal.md")
        content = report_file.read_text(encoding="utf-8")

        entities = [
            "User",
            "Organization",
            "Membership",
            "LocalAgent",
            "BrowserTask",
            "BrowserApproval",
            "BrowserResult",
            "AppAuditLog",
        ]

        for entity in entities:
            assert entity in content, f"Schema report must mention {entity}"

    def test_schema_report_mentions_organization_id_requirement(self):
        """Schema에 organization_id 필수 항목 설명"""
        report_file = Path("docs/reports/tenant_2_minimal_scope_schema_proposal.md")
        content = report_file.read_text(encoding="utf-8")

        assert (
            "organization_id NOT NULL" in content
            or "organization_id REQUIRED" in content
            or "organization_id 필수" in content
        ), "Schema must describe organization_id as required"


class TestTenantContractFile:
    """TENANT-2 contract Python file 검증"""

    def test_tenant_contract_file_exists(self):
        """tenant_scope_contract.py 파일 존재"""
        contract_file = Path("core/agent_runtime/policy/tenant_scope_contract.py")
        assert contract_file.exists(), "tenant_scope_contract.py must exist"

    def test_contract_file_compiles(self):
        """contract file Python 컴파일 검사"""
        import py_compile

        contract_file = Path("core/agent_runtime/policy/tenant_scope_contract.py")
        try:
            py_compile.compile(str(contract_file), doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"Contract file compile error: {e}")

    def test_auth_tenant_context_defined(self):
        """AuthTenantContext 클래스 정의"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        # Create instance
        ctx = AuthTenantContext(
            actor_user_id="user-1",
            organization_ids=["org-1"],
            active_organization_id="org-1",
        )

        assert ctx.actor_user_id == "user-1"
        assert "org-1" in ctx.organization_ids
        assert ctx.active_organization_id == "org-1"

    def test_auth_context_requires_user_id(self):
        """AuthTenantContext에 actor_user_id 필수 (G1)"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        with pytest.raises(ValueError) as exc_info:
            AuthTenantContext(
                actor_user_id="",  # Empty
                organization_ids=["org-1"],
                active_organization_id="org-1",
            )
        assert "actor_user_id" in str(exc_info.value)

    def test_auth_context_requires_organization_ids(self):
        """AuthTenantContext에 organization_ids 필수 (G4)"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        with pytest.raises(ValueError) as exc_info:
            AuthTenantContext(
                actor_user_id="user-1",
                organization_ids=[],  # Empty
                active_organization_id="org-1",
            )
        assert "organization_ids" in str(exc_info.value)

    def test_auth_context_requires_active_organization(self):
        """AuthTenantContext에 active_organization_id 필수"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        with pytest.raises(ValueError) as exc_info:
            AuthTenantContext(
                actor_user_id="user-1",
                organization_ids=["org-1"],
                active_organization_id="",  # Empty
            )
        assert "active_organization_id" in str(exc_info.value)

    def test_auth_context_active_org_must_be_in_list(self):
        """active_organization_id는 organization_ids에 포함되어야 함"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        with pytest.raises(ValueError) as exc_info:
            AuthTenantContext(
                actor_user_id="user-1",
                organization_ids=["org-1"],
                active_organization_id="org-999",  # Not in list
            )
        assert "not in organization_ids" in str(exc_info.value)

    def test_auth_context_has_access_to_organization(self):
        """has_access_to_organization 메서드"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        ctx = AuthTenantContext(
            actor_user_id="user-1",
            organization_ids=["org-1", "org-2"],
            active_organization_id="org-1",
        )

        assert ctx.has_access_to_organization("org-1")
        assert ctx.has_access_to_organization("org-2")
        assert not ctx.has_access_to_organization("org-999")

    def test_auth_context_require_access_raises(self):
        """require_access_to_organization raises on unauthorized"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        ctx = AuthTenantContext(
            actor_user_id="user-1",
            organization_ids=["org-1"],
            active_organization_id="org-1",
        )

        with pytest.raises(ValueError):
            ctx.require_access_to_organization("org-999")


class TestLocalAgentScope:
    """LocalAgent 조직 범위 계약 (G10)"""

    def test_local_agent_requires_organization_id(self):
        """LocalAgentScope에 organization_id 필수 (G10)"""
        from core.agent_runtime.policy.tenant_scope_contract import LocalAgentScope

        with pytest.raises(ValueError) as exc_info:
            LocalAgentScope(
                agent_id="agent-1",
                organization_id="",  # Empty
            )
        assert "organization_id" in str(exc_info.value) and "G10" in str(exc_info.value)

    def test_local_agent_rejects_raw_hostname(self):
        """LocalAgentScope는 raw hostname 거부"""
        from core.agent_runtime.policy.tenant_scope_contract import LocalAgentScope

        with pytest.raises(ValueError) as exc_info:
            LocalAgentScope(
                agent_id="agent-1",
                organization_id="org-1",
                host_name_hash="hostname=my-computer.local",  # raw hostname
            )
        assert "hostname not allowed" in str(exc_info.value)

    def test_local_agent_accepts_host_hash(self):
        """LocalAgentScope는 hostname hash 허용"""
        from core.agent_runtime.policy.tenant_scope_contract import LocalAgentScope

        agent = LocalAgentScope(
            agent_id="agent-1",
            organization_id="org-1",
            host_name_hash="abc123def456",  # hash is OK
        )

        assert agent.host_name_hash == "abc123def456"

    def test_local_agent_safe_dict(self):
        """LocalAgentScope.safe_dict()"""
        from core.agent_runtime.policy.tenant_scope_contract import LocalAgentScope

        agent = LocalAgentScope(
            agent_id="agent-1",
            organization_id="org-1",
            host_name_hash="abc123",
            agent_version="1.0.0",
            capabilities=["browser.inspect"],
            status="ready",
        )

        safe = agent.safe_dict()
        assert safe["agent_id"] == "agent-1"
        assert safe["organization_id"] == "org-1"
        assert safe["host_name_hash"] == "abc123"


class TestBrowserTaskScope:
    """BrowserTask 조직 범위 계약 (G5)"""

    def test_browser_task_requires_organization_id(self):
        """BrowserTaskScope에 organization_id 필수 (G5)"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserTaskScope

        with pytest.raises(ValueError) as exc_info:
            BrowserTaskScope(
                task_id="task-1",
                organization_id="",  # Empty
                requested_by_user_id="user-1",
            )
        assert "organization_id" in str(exc_info.value) and "G5" in str(exc_info.value)

    def test_browser_task_requires_requested_by_user_id(self):
        """BrowserTaskScope에 requested_by_user_id 필수"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserTaskScope

        with pytest.raises(ValueError) as exc_info:
            BrowserTaskScope(
                task_id="task-1",
                organization_id="org-1",
                requested_by_user_id="",  # Empty
            )
        assert "requested_by_user_id" in str(exc_info.value)


class TestBrowserApprovalScope:
    """BrowserApproval 조직 범위 계약 (G6)"""

    def test_browser_approval_requires_organization_id(self):
        """BrowserApprovalScope에 organization_id 필수 (G6)"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserApprovalScope

        with pytest.raises(ValueError) as exc_info:
            BrowserApprovalScope(
                approval_id="approval-1",
                task_id="task-1",
                organization_id="",  # Empty
                requested_by_user_id="user-1",
                approval_token_hash="sha256abc123",
            )
        assert "organization_id" in str(exc_info.value) and "G6" in str(exc_info.value)

    def test_browser_approval_requires_token_hash(self):
        """BrowserApprovalScope에 approval_token_hash 필수"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserApprovalScope

        with pytest.raises(ValueError) as exc_info:
            BrowserApprovalScope(
                approval_id="approval-1",
                task_id="task-1",
                organization_id="org-1",
                requested_by_user_id="user-1",
                approval_token_hash="",  # Empty
            )
        assert "approval_token_hash" in str(exc_info.value)

    def test_browser_approval_rejects_plaintext_token(self):
        """BrowserApprovalScope는 plaintext token 거부"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserApprovalScope

        with pytest.raises(ValueError) as exc_info:
            BrowserApprovalScope(
                approval_id="approval-1",
                task_id="task-1",
                organization_id="org-1",
                requested_by_user_id="user-1",
                approval_token_hash="approval_token=secret123",  # plaintext
            )
        assert "plaintext" in str(exc_info.value)


class TestBrowserResultScope:
    """BrowserResult 조직 범위 계약 (G7)"""

    def test_browser_result_requires_organization_id(self):
        """BrowserResultScope에 organization_id 필수 (G7)"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserResultScope

        with pytest.raises(ValueError) as exc_info:
            BrowserResultScope(
                result_id="result-1",
                task_id="task-1",
                organization_id="",  # Empty
            )
        assert "organization_id" in str(exc_info.value) and "G7" in str(exc_info.value)

    def test_browser_result_requires_task_id(self):
        """BrowserResultScope에 task_id 필수"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserResultScope

        with pytest.raises(ValueError) as exc_info:
            BrowserResultScope(
                result_id="result-1",
                task_id="",  # Empty
                organization_id="org-1",
            )
        assert "task_id" in str(exc_info.value)


class TestBrowserAuditEventScope:
    """BrowserAuditEvent 조직 범위 계약 (G8)"""

    def test_browser_audit_event_requires_org_for_browser_task(self):
        """BROWSER_* event는 organization_id 필수 (G8)"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserAuditEventScope

        with pytest.raises(ValueError) as exc_info:
            BrowserAuditEventScope(
                event_id="event-1",
                event_type="BROWSER_TASK_CREATED",
                task_id="task-1",
                organization_id="",  # Empty
            )
        assert "organization_id" in str(exc_info.value) and "G8" in str(exc_info.value)

    def test_system_audit_event_allows_null_org(self):
        """AGENT_* 등 시스템 event는 organization_id nullable"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserAuditEventScope

        # Should not raise
        event = BrowserAuditEventScope(
            event_id="event-1",
            event_type="AGENT_REGISTERED",
            organization_id=None,  # NULL for system events OK
        )
        assert event.organization_id is None


class TestScopeValidationRules:
    """조직 범위 검증 규칙"""

    def test_task_approval_agent_same_org_rule(self):
        """RULE: task.org == approval.org == agent.org"""
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
        """org mismatch: task.org != approval.org → ValueError"""
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
            organization_id="org-2",  # Different org!
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

    def test_task_agent_org_mismatch_rejected(self):
        """org mismatch: task.org != agent.org → ValueError"""
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
            organization_id="org-2",  # Different org!
        )

        with pytest.raises(ValueError) as exc_info:
            assert_task_approval_agent_same_org(task, approval, agent)
        assert "organization_id" in str(exc_info.value)

    def test_result_task_same_org_rule(self):
        """RULE: result.org == task.org"""
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
            organization_id="org-2",  # Different org!
        )

        with pytest.raises(ValueError) as exc_info:
            assert_result_task_same_org(result, task)
        assert "organization_id" in str(exc_info.value)


class TestSafeTenantScopeDict:
    """safe_tenant_scope_dict 함수 검증"""

    def test_safe_dict_removes_approval_token(self):
        """safe_dict가 approval_token 제거"""
        from core.agent_runtime.policy.tenant_scope_contract import safe_tenant_scope_dict

        data = {
            "approval_token": "secret-token",
            "safe_field": "value",
        }

        result = safe_tenant_scope_dict(data)
        assert "approval_token" not in result
        assert result["safe_field"] == "value"

    def test_safe_dict_removes_password(self):
        """safe_dict가 password 제거"""
        from core.agent_runtime.policy.tenant_scope_contract import safe_tenant_scope_dict

        data = {
            "password": "secret123",
            "username": "john",
            "user_id": "user-1",  # user_id는 OK
        }

        result = safe_tenant_scope_dict(data)
        assert "password" not in result
        assert "username" not in result
        assert result["user_id"] == "user-1"


class TestPermissionMatrix:
    """권한 매트릭스 정의 확인"""

    def test_permission_matrix_defined(self):
        """PERMISSION_MATRIX 정의"""
        from core.agent_runtime.policy.tenant_scope_contract import PERMISSION_MATRIX

        roles = ["owner", "admin", "manager", "operator", "viewer", "auditor", "local_agent"]
        for role in roles:
            assert role in PERMISSION_MATRIX, f"PERMISSION_MATRIX must define {role}"

    def test_permission_matrix_owner_full_access(self):
        """owner role은 full access"""
        from core.agent_runtime.policy.tenant_scope_contract import PERMISSION_MATRIX

        owner_perms = PERMISSION_MATRIX["owner"]
        # owner는 대부분 True
        assert owner_perms["org_settings"] is True
        assert owner_perms["user_invite"] is True


class TestGapCoverage:
    """Gap G1~G13 대응 확인"""

    def test_gap_g1_covered_by_auth_context_user_id(self):
        """G1: auth_context.actor_user_id"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        ctx = AuthTenantContext(
            actor_user_id="user-1",
            organization_ids=["org-1"],
            active_organization_id="org-1",
        )
        assert hasattr(ctx, "actor_user_id")

    def test_gap_g4_covered_by_auth_context_org_ids(self):
        """G4: auth_context.organization_ids"""
        from core.agent_runtime.policy.tenant_scope_contract import AuthTenantContext

        ctx = AuthTenantContext(
            actor_user_id="user-1",
            organization_ids=["org-1"],
            active_organization_id="org-1",
        )
        assert hasattr(ctx, "organization_ids")

    def test_gap_g5_covered_by_browser_task_scope(self):
        """G5: BrowserTaskScope.organization_id"""
        from core.agent_runtime.policy.tenant_scope_contract import BrowserTaskScope

        task = BrowserTaskScope(
            task_id="task-1",
            organization_id="org-1",
            requested_by_user_id="user-1",
        )
        assert hasattr(task, "organization_id")

    def test_gap_g10_covered_by_local_agent_scope(self):
        """G10: LocalAgentScope.organization_id"""
        from core.agent_runtime.policy.tenant_scope_contract import LocalAgentScope

        agent = LocalAgentScope(
            agent_id="agent-1",
            organization_id="org-1",
        )
        assert hasattr(agent, "organization_id")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
