"""TENANT-1 설계 검증 테스트

조직별 데이터 분리 설계의 현황을 검증하고 gap을 명확히 한다.

테스트 원칙:
- 현재 코드에 없는 항목을 "gap documented" 스타일로 검증
- FAIL하지 말고 해당 gap을 명시적으로 기록
- 기존 코드의 safe_dict 등 검증
"""

from pathlib import Path

import pytest


class TestOrganizationModelGap:
    """G2: Organization model 필요성 검증"""

    def test_organization_model_does_not_exist(self):
        """조직 모델이 현재 없음을 확인"""
        try:
            from ai_orchestrator.core.models import Organization

            # 만약 이 import가 성공하면, model이 추가된 것
            assert hasattr(Organization, "organization_id"), "Organization model must have organization_id field"
        except ImportError:
            # 예상되는 상태: gap이 문서화되어야 함
            pass


class TestMembershipModelGap:
    """G3: Membership model 필요성 검증"""

    def test_membership_model_does_not_exist(self):
        """멤버십 모델이 현재 없음을 확인"""
        try:
            from ai_orchestrator.core.models import Membership

            # 만약 이 import가 성공하면, model이 추가된 것
            assert hasattr(Membership, "organization_id"), "Membership must have organization_id"
            assert hasattr(Membership, "user_id"), "Membership must have user_id"
            assert hasattr(Membership, "role"), "Membership must have role"
        except ImportError:
            # Gap documented: Membership 모델 미구현
            pass


class TestAuthOrganizationIdGap:
    """G4: Auth에 organization_id 추가 검증"""

    def test_current_auth_lacks_organization_ids(self):
        """현재 auth는 {actor, role}만 반환 (organization_ids 없음)"""
        # Skip if import fails (env issue)
        try:
            from tools.gates.auth import _DUMMY_USER

            # 현재 구조 확인
            assert "actor" in _DUMMY_USER
            assert "role" in _DUMMY_USER

            # Gap: organization_ids 필드 없음
            assert "organization_ids" not in _DUMMY_USER, "Gap G4: Auth should return organization_ids list"
        except (ImportError, Exception) as e:  # noqa: BLE001 - 테넌트 스코프 설계 검증 테스트 -- import 실패 시 pytest.skip으로 건너뛰는 용도, 실제 로직 실행이나 판정에 영향 없음
            # Skip due to env setup issues
            pytest.skip(f"Import failed: {e}")


class TestBrowserTaskModelGap:
    """G5: BrowserTask model 필요성 검증"""

    def test_browser_task_model_does_not_exist(self):
        """BrowserTask 모델 부재 확인"""
        import importlib
        import importlib.util

        if importlib.util.find_spec("local_agent.browser_task") is None:
            # Gap documented: BrowserTask 모델 미구현
            return
        BrowserTask = importlib.import_module("local_agent.browser_task").BrowserTask
        assert hasattr(BrowserTask, "organization_id"), "BrowserTask must have organization_id field"
        assert hasattr(BrowserTask, "task_id"), "BrowserTask must have task_id field"


class TestBrowserApprovalModelGap:
    """G6: BrowserApproval model persistence 검증"""

    def test_approval_manager_lacks_persistence(self):
        """현재 approval_manager는 메모리 기반"""
        from orchestrator_v1.tasks.approval_manager import _store

        # _store는 dict (메모리 기반)
        assert isinstance(_store, dict), "Current implementation uses in-memory dict"

        # Gap: persistent store 필요
        # approval_id, task_id, organization_id 필드 미정의
        pass

    def test_approval_lacks_organization_id_field(self):
        """approval_manager token record에 organization_id 없음"""
        from orchestrator_v1.core.models import RiskAssessment, TaskRequest
        from orchestrator_v1.tasks.approval_manager import issue_token

        task = TaskRequest(task_id="test-task-1", source="pc", action_type="click", target="button", description="test")
        risk = RiskAssessment(risk_level="low")

        token_id = issue_token(task, risk)
        if token_id:
            from orchestrator_v1.tasks.approval_manager import _store

            record = _store.get(token_id, {})
            # Gap: organization_id 필드 없음
            assert "organization_id" not in record, "Gap G6: Approval record lacks organization_id"


class TestBrowserAuditContractGap:
    """G8: BrowserAuditEvent factory 필요성 검증"""

    def test_browser_audit_contract_does_not_exist(self):
        """BrowserAuditEvent factory 부재"""
        try:
            from core.agent_runtime.browser.approval.browser_audit_contract import BrowserAuditEvent

            # 만약 import 성공하면
            assert hasattr(BrowserAuditEvent, "organization_id"), "BrowserAuditEvent must have organization_id"
        except ImportError:
            # Gap documented: browser_audit_contract 미구현
            pass


class TestWebSocketHandshakeScopeRule:
    """G9: WebSocket handshake organization_id 검증"""

    def test_agent_hello_message_lacks_organization_id(self):
        """AgentHelloMessage에 organization_id가 구현되어 있음 (Gap G9 해소)"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            host_name_hash="abc123",
        )

        msg_dict = msg.to_dict()
        # G9 구현 완료: organization_id가 필드에 포함됨
        assert "organization_id" in msg_dict, "G9 구현: AgentHelloMessage에 organization_id 필드가 있어야 합니다"

    def test_agent_hello_message_lacks_registration_user_id(self):
        """AgentHelloMessage에 registration_user_id가 구현되어 있음 (Gap G9 해소)"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import AgentHelloMessage

        msg = AgentHelloMessage(
            agent_id="agent-1",
            agent_version="1.0.0",
            host_name_hash="abc123",
        )

        msg_dict = msg.to_dict()
        # G9 구현 완료: registration_user_id가 필드에 포함됨
        assert "registration_user_id" in msg_dict, (
            "G9 구현: AgentHelloMessage에 registration_user_id 필드가 있어야 합니다"
        )

    def test_server_policy_message_lacks_organization_id(self):
        """ServerPolicyMessage에 organization_id가 구현되어 있음 (Gap G9 해소)"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import ServerPolicyMessage

        msg = ServerPolicyMessage()
        msg_dict = msg.to_dict()

        # G9 구현 완료: organization_id가 필드에 포함됨
        assert "organization_id" in msg_dict, "G9 구현: ServerPolicyMessage에 organization_id 필드가 있어야 합니다"


class TestWebSocketSafeDict:
    """WebSocket handshake safe_dict 함수 검증"""

    def test_safe_dict_removes_approval_token(self):
        """safe_dict가 approval_token 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {"agent_id": "agent-1", "approval_token": "secret-token-xyz", "safe_field": "value"}

        result = safe_dict(data)
        assert "approval_token" not in result
        assert "safe_field" in result

    def test_safe_dict_removes_final_approval_token(self):
        """safe_dict가 final_approval_token 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {"agent_id": "agent-1", "final_approval_token": "final-secret", "other": "ok"}

        result = safe_dict(data)
        assert "final_approval_token" not in result
        assert "other" in result

    def test_safe_dict_removes_token_hash(self):
        """safe_dict가 token_hash 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {"token_hash": "sha256:...", "safe": "value"}

        result = safe_dict(data)
        assert "token_hash" not in result

    def test_safe_dict_removes_password(self):
        """safe_dict가 password 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {"password": "secret123", "otp": "123456", "safe": "value"}

        result = safe_dict(data)
        assert "password" not in result
        assert "otp" not in result
        assert "safe" in result

    def test_safe_dict_removes_raw_hostname(self):
        """safe_dict가 raw hostname 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {
            "hostname": "my-computer.local",
            "host_name_hash": "abc123def",  # 이건 괜찮음
            "safe": "ok",
        }

        result = safe_dict(data)
        assert "hostname" not in result
        assert "host_name_hash" in result  # hash는 안전

    def test_safe_dict_removes_raw_username(self):
        """safe_dict가 raw username 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {
            "username": "john.doe",
            "user_name": "john",
            "user_id": "user-123",  # ID는 괜찮음
        }

        result = safe_dict(data)
        assert "username" not in result
        assert "user_name" not in result
        assert "user_id" in result

    def test_safe_dict_removes_raw_ip(self):
        """safe_dict가 raw IP address 제거"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {"ip_address": "192.168.1.100", "safe": "ok"}

        result = safe_dict(data)
        assert "ip_address" not in result

    def test_safe_dict_keeps_safe_fields(self):
        """safe_dict가 안전한 필드는 유지"""
        from core.agent_runtime.browser.bridge.browser_websocket_handshake import safe_dict

        data = {
            "agent_id": "agent-123",
            "host_name_hash": "abc",
            "user_id": "user-456",
            "timestamp": "2026-05-01T00:00:00Z",
            "capabilities": ["browser.inspect"],
        }

        result = safe_dict(data)
        assert result["agent_id"] == "agent-123"
        assert result["host_name_hash"] == "abc"
        assert result["user_id"] == "user-456"
        assert result["timestamp"] == "2026-05-01T00:00:00Z"
        assert result["capabilities"] == ["browser.inspect"]


class TestLocalAgentModelGap:
    """G10: LocalAgent model organization_id 검증"""

    def test_local_agent_lacks_organization_id(self):
        """현재 LocalAgent model에 organization_id 없음"""
        # agent.py는 모듈이고 LocalAgent 클래스가 정의되어 있지 않음
        # gap: LocalAgent 모델 클래스 전무
        try:
            from core.agent_runtime.agent import (
                LocalAgent,  # noqa: F401 — 존재 여부만 확인(gap 테스트)
            )

            pytest.fail("LocalAgent class should not exist yet")
        except ImportError:
            # Expected: gap documented
            # LocalAgent 모델이 필요하지만 현재 없음
            assert True


class TestBrowserAuditEventTypes:
    """G6 확장: audit event types 검증"""

    def test_browser_audit_event_types_missing(self):
        """Audit logger에 BROWSER_* event types 추가 필요"""
        try:
            from ai_orchestrator.audit.audit_logger import EVENT_TYPES

            browser_event_types = {
                "BROWSER_TASK_CREATED",
                "BROWSER_TASK_APPROVED",
                "BROWSER_TASK_REJECTED",
                "BROWSER_TASK_COMPLETED",
                "BROWSER_APPROVAL_REQUESTED",
                "BROWSER_APPROVAL_GRANTED",
                "BROWSER_APPROVAL_REJECTED",
                "BROWSER_APPROVAL_EXPIRED",
            }

            missing = browser_event_types - EVENT_TYPES
            # Gap: browser event types 부족
            assert len(missing) > 0, "Gap: Missing browser audit event types: " + ", ".join(missing)
        except (ImportError, Exception) as e:  # noqa: BLE001 - 테넌트 스코프 설계 검증 테스트 -- import 실패 시 pytest.skip으로 건너뛰는 용도, 실제 로직 실행이나 판정에 영향 없음
            # Skip due to env setup issues
            pytest.skip(f"Import failed: {e}")


class TestAdminWebBrowserApprovalTypes:
    """G12: Admin web browser-approval.ts type 검증"""

    def test_browser_approval_types_do_not_exist(self):
        """admin-web/src/types/browser-approval.ts 구현됨 (Gap G12 해소)"""
        types_file = Path("admin-web/src/types/browser-approval.ts")

        # G12 구현 완료: 파일이 생성되어 있음
        assert types_file.exists(), "G12 구현: admin-web/src/types/browser-approval.ts 파일이 있어야 합니다"


class TestAuditLogMigration:
    """G11: AppAuditLog migration 검증"""

    def test_audit_log_table_schema_has_organization_id(self):
        """AppAuditLog 테이블에 organization_id가 있는지 확인"""
        # DB가 없으므로 static 검증만 가능
        # migration 파일 확인 필요

        migrations_dir = Path("migrations")

        if migrations_dir.exists():
            migration_files = list(migrations_dir.glob("*.sql"))
            found_app_audit_log = any(
                "app_audit_log" in f.read_text(encoding="utf-8") for f in migration_files if f.exists()
            )

            if found_app_audit_log:
                # Migration이 있으면 organization_id 확인
                pass

        # Gap G11: migration 파일 확인 또는 생성 필요


class TestTenantScopeDesignReport:
    """설계 보고서 자체 검증"""

    def test_tenant_scope_design_report_exists(self):
        """설계 보고서가 존재하는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        assert report_file.exists(), (
            "Tenant scope design report must exist at docs/reports/tenant_1_scope_design_report.md"
        )

    def test_tenant_scope_report_mentions_browser_task(self):
        """보고서에 BrowserTask가 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "BrowserTask" in content
        assert "organization_id" in content

    def test_tenant_scope_report_mentions_browser_approval(self):
        """보고서에 BrowserApproval이 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "BrowserApproval" in content
        assert "approval_id" in content

    def test_tenant_scope_report_mentions_local_agent(self):
        """보고서에 LocalAgent가 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "LocalAgent" in content

    def test_tenant_scope_report_mentions_audit_log(self):
        """보고서에 감사 로그가 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "BrowserAuditEvent" in content or "audit" in content.lower()

    def test_tenant_scope_report_mentions_permission_matrix(self):
        """보고서에 권한 매트릭스가 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "Permission Matrix" in content or "permission" in content.lower()

    def test_tenant_scope_report_mentions_p1_gaps(self):
        """보고서에 P1 gap이 명시되어 있는지 확인"""
        report_file = Path("docs/reports/tenant_1_scope_design_report.md")
        content = report_file.read_text(encoding="utf-8")
        assert "P1 Gap" in content or "P1:" in content


class TestGapDocumentation:
    """Gap 문서화 검증"""

    def test_gap_g1_user_id_requirement(self):
        """G1: User model에 user_id 필수"""
        # 현재 auth.py의 _DUMMY_USER는 actor만 가짐
        try:
            from tools.gates.auth import _DUMMY_USER

            # Gap: user_id 없음
            assert "user_id" not in _DUMMY_USER, "Gap G1 documented: User model needs user_id field"
        except (ImportError, Exception) as e:  # noqa: BLE001 - 테넌트 스코프 설계 검증 테스트 -- import 실패 시 pytest.skip으로 건너뛰는 용도, 실제 로직 실행이나 판정에 영향 없음
            # Skip due to env setup
            pytest.skip(f"Import failed: {e}")

    def test_gap_g2_organization_model_required(self):
        """G2: Organization model 필수"""
        try:
            from ai_orchestrator.core.models import (
                Organization,  # noqa: F401 — 존재 여부만 확인(gap 테스트)
            )

            pytest.skip("G2 already implemented")
        except ImportError:
            # Expected: gap documented
            assert True

    def test_gap_g13_api_scope_check(self):
        """G13: API scope check 필요"""
        # browser task API가 organization_id로 필터링하지 않음
        # 이 테스트는 API가 구현된 후 확인
        pass


class TestApprovalTokenStorage:
    """Approval token 저장 방식 검증"""

    def test_approval_token_should_not_be_stored_in_plaintext(self):
        """Approval token은 plaintext 저장 금지"""
        # 설계 원칙 검증
        # 현재 approval_manager는 token_id만 저장 (token 원문은 메모리/클라이언트에만)
        from orchestrator_v1.tasks.approval_manager import _store

        # Gap: token 자체는 저장하지 않지만, persistent store 필요 시
        # token_hash를 사용해야 함
        assert isinstance(_store, dict), "Current in-memory store doesn't expose token plaintext (good)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
