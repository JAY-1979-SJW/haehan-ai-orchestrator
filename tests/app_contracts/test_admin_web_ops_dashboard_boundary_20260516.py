"""
STEP 14 — /ops 운영센터 페이지 백엔드 경계 테스트
검증 범위:
  - ops/lib 파일 존재
  - ops/components 파일 존재
  - ops/page.tsx 존재
  - 위험 버튼 disabled 처리 확인
  - secret/token/password 노출 없음
  - 외부 API 직접 호출 없음 (mock fallback 전용)
"""

import re
from pathlib import Path

ADMIN_WEB = Path(__file__).parent.parent.parent / "admin-web" / "src" / "app" / "ops"

LIB_FILES = [
    "lib/types.ts",
    "lib/mockOpsData.ts",
    "lib/statusFormat.ts",
    "lib/opsApiClient.ts",
]

COMPONENT_FILES = [
    "components/OpsDashboard.tsx",
    "components/WorkTradeBoard.tsx",
    "components/ApprovalQueue.tsx",
    "components/WebTaskPanel.tsx",
    "components/ExternalWebTaskSummary.tsx",
    "components/AgentStatusPanel.tsx",
    "components/AuditEventTable.tsx",
    "components/IntegrationStatusPanel.tsx",
    "components/SafetyPolicyBanner.tsx",
]

DATA_TESTIDS = {
    "components/OpsDashboard.tsx": "ops-dashboard-section",
    "components/WorkTradeBoard.tsx": "work-trade-section",
    "components/ApprovalQueue.tsx": "approval-queue-section",
    "components/WebTaskPanel.tsx": "web-task-section",
    "components/ExternalWebTaskSummary.tsx": "external-web-task-section",
    "components/AgentStatusPanel.tsx": "agent-status-section",
    "components/AuditEventTable.tsx": "audit-event-section",
    "components/IntegrationStatusPanel.tsx": "integration-status-section",
    "components/SafetyPolicyBanner.tsx": "safety-policy-section",
}


class TestOpsLibFilesExist:
    def test_types_ts_exists(self):
        assert (ADMIN_WEB / "lib/types.ts").exists()

    def test_mock_ops_data_ts_exists(self):
        assert (ADMIN_WEB / "lib/mockOpsData.ts").exists()

    def test_status_format_ts_exists(self):
        assert (ADMIN_WEB / "lib/statusFormat.ts").exists()

    def test_ops_api_client_ts_exists(self):
        assert (ADMIN_WEB / "lib/opsApiClient.ts").exists()


class TestOpsComponentFilesExist:
    def test_ops_dashboard_exists(self):
        assert (ADMIN_WEB / "components/OpsDashboard.tsx").exists()

    def test_work_trade_board_exists(self):
        assert (ADMIN_WEB / "components/WorkTradeBoard.tsx").exists()

    def test_approval_queue_exists(self):
        assert (ADMIN_WEB / "components/ApprovalQueue.tsx").exists()

    def test_web_task_panel_exists(self):
        assert (ADMIN_WEB / "components/WebTaskPanel.tsx").exists()

    def test_external_web_task_summary_exists(self):
        assert (ADMIN_WEB / "components/ExternalWebTaskSummary.tsx").exists()

    def test_agent_status_panel_exists(self):
        assert (ADMIN_WEB / "components/AgentStatusPanel.tsx").exists()

    def test_audit_event_table_exists(self):
        assert (ADMIN_WEB / "components/AuditEventTable.tsx").exists()

    def test_integration_status_panel_exists(self):
        assert (ADMIN_WEB / "components/IntegrationStatusPanel.tsx").exists()

    def test_safety_policy_banner_exists(self):
        assert (ADMIN_WEB / "components/SafetyPolicyBanner.tsx").exists()

    def test_ops_page_tsx_exists(self):
        assert (ADMIN_WEB / "page.tsx").exists()


class TestOpsComponentTestIds:
    def test_ops_dashboard_has_testid(self):
        src = (ADMIN_WEB / "components/OpsDashboard.tsx").read_text(encoding="utf-8")
        assert 'data-testid="ops-dashboard-section"' in src

    def test_work_trade_has_testid(self):
        src = (ADMIN_WEB / "components/WorkTradeBoard.tsx").read_text(encoding="utf-8")
        assert 'data-testid="work-trade-section"' in src

    def test_approval_queue_has_testid(self):
        src = (ADMIN_WEB / "components/ApprovalQueue.tsx").read_text(encoding="utf-8")
        assert 'data-testid="approval-queue-section"' in src

    def test_web_task_panel_has_testid(self):
        src = (ADMIN_WEB / "components/WebTaskPanel.tsx").read_text(encoding="utf-8")
        assert 'data-testid="web-task-section"' in src

    def test_external_web_task_has_testid(self):
        src = (ADMIN_WEB / "components/ExternalWebTaskSummary.tsx").read_text(encoding="utf-8")
        assert 'data-testid="external-web-task-section"' in src

    def test_agent_status_has_testid(self):
        src = (ADMIN_WEB / "components/AgentStatusPanel.tsx").read_text(encoding="utf-8")
        assert 'data-testid="agent-status-section"' in src

    def test_audit_event_has_testid(self):
        src = (ADMIN_WEB / "components/AuditEventTable.tsx").read_text(encoding="utf-8")
        assert 'data-testid="audit-event-section"' in src

    def test_integration_status_has_testid(self):
        src = (ADMIN_WEB / "components/IntegrationStatusPanel.tsx").read_text(encoding="utf-8")
        assert 'data-testid="integration-status-section"' in src

    def test_safety_policy_has_testid(self):
        src = (ADMIN_WEB / "components/SafetyPolicyBanner.tsx").read_text(encoding="utf-8")
        assert 'data-testid="safety-policy-section"' in src


class TestOpsDisabledButtons:
    """위험 버튼은 모두 disabled 처리되어야 한다."""

    def test_approval_queue_approve_button_disabled(self):
        src = (ADMIN_WEB / "components/ApprovalQueue.tsx").read_text(encoding="utf-8")
        # 승인/거절 버튼 disabled 여부
        assert "disabled" in src
        assert "cursor-not-allowed" in src

    def test_web_task_panel_execute_button_disabled(self):
        src = (ADMIN_WEB / "components/WebTaskPanel.tsx").read_text(encoding="utf-8")
        assert "disabled" in src
        assert "cursor-not-allowed" in src

    def test_integration_panel_action_button_disabled(self):
        src = (ADMIN_WEB / "components/IntegrationStatusPanel.tsx").read_text(encoding="utf-8")
        assert "disabled" in src
        assert "cursor-not-allowed" in src

    def test_approval_queue_no_live_api_call(self):
        src = (ADMIN_WEB / "components/ApprovalQueue.tsx").read_text(encoding="utf-8")
        assert "onClick" not in src


class TestOpsSecretNonExposure:
    """secret/token/password 실제 값 노출 없음."""

    def _all_ops_source(self) -> str:
        blobs = []
        for path in ADMIN_WEB.rglob("*.ts"):
            blobs.append(path.read_text(encoding="utf-8"))
        for path in ADMIN_WEB.rglob("*.tsx"):
            blobs.append(path.read_text(encoding="utf-8"))
        return "\n".join(blobs)

    def test_no_credential_assignment(self):
        blob = self._all_ops_source()
        bad = re.findall(
            r'(?:password|client_secret|api_key)\s*[:=]\s*["\'][^"\']{8,}["\']',
            blob,
            re.I,
        )
        assert bad == [], f"credential 값 발견: {bad}"

    def test_no_bearer_token_hardcoded(self):
        blob = self._all_ops_source()
        # admin-token 은 stub이지만 검사 대상 제외 (opsApiClient 에서만 허용)
        # 실제 비밀 토큰 형태 (40자 이상 hex/base64) 검사
        bad = re.findall(r"Bearer\s+[A-Za-z0-9+/=_-]{40,}", blob)
        assert bad == [], f"실제 Bearer 토큰 발견: {bad}"

    def test_mock_data_no_real_passwords(self):
        mock_src = (ADMIN_WEB / "lib/mockOpsData.ts").read_text(encoding="utf-8")
        # 정책 설명(한글 문자열)에 password 언급은 허용; 실제 할당 패턴만 금지
        bad = re.findall(
            r'(?:password|secret)\s*[:=]\s*["\'][^"\']{4,}["\']',
            mock_src,
            re.I,
        )
        assert bad == [], f"password 값 할당 발견: {bad}"


class TestOpsPageAssembly:
    def test_ops_page_imports_all_components(self):
        src = (ADMIN_WEB / "page.tsx").read_text(encoding="utf-8")
        required = [
            "OpsDashboard",
            "WorkTradeBoard",
            "ApprovalQueue",
            "WebTaskPanel",
            "ExternalWebTaskSummaryPanel",
            "AgentStatusPanel",
            "AuditEventTable",
            "IntegrationStatusPanel",
            "SafetyPolicyBanner",
        ]
        for component in required:
            assert component in src, f"{component} import 누락"

    def test_ops_page_uses_live_data_without_mock_fallback(self):
        src = (ADMIN_WEB / "page.tsx").read_text(encoding="utf-8")
        assert "fetchDashboardMetrics" in src
        assert "fetchApprovalQueue" in src
        assert "MOCK_METRICS" not in src
        assert "MOCK_APPROVAL_QUEUE" not in src

    def test_home_page_has_ops_link(self):
        # 현행: 홈(page.tsx)은 단일 AI 콘솔(855d595a) — /ops 진입 링크는 공통 nav 정본(lib/nav.ts)에 있다.
        nav = (ADMIN_WEB.parent.parent / "lib" / "nav.ts").read_text(encoding="utf-8")
        assert '{ key: "ops",  label: "운영센터", shortLabel: "운영", href: "/ops" }' in nav

    def test_ops_api_client_has_no_mock_fallback(self):
        src = (ADMIN_WEB / "lib/opsApiClient.ts").read_text(encoding="utf-8")
        assert "MOCK_" not in src
        assert "Bearer admin-token" not in src


class TestOpsNoExternalApiCallInComponents:
    """컴포넌트 파일에서 직접 fetch 호출 없음."""

    def test_components_no_direct_fetch(self):
        for rel in COMPONENT_FILES:
            src = (ADMIN_WEB / rel).read_text(encoding="utf-8")
            assert "fetch(" not in src, f"{rel} 에서 직접 fetch 호출 발견"

    def test_api_client_is_only_fetch_point(self):
        src = (ADMIN_WEB / "lib/opsApiClient.ts").read_text(encoding="utf-8")
        assert "fetch(" in src  # client stub은 fetch 사용 허용
