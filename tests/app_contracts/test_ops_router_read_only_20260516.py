"""
STEP 8 — ops_router read-only API 경계 테스트
검증 범위:
  1. ops_router 가 GET만 제공 (POST/PUT/DELETE 없음)
  2. ops_router 가 admin_ui_router/기존 라우터와 별도
  3. ops_router 가 외부 API/Telegram 호출 없음
  4. ops_router 가 secret/token/password 노출 없음
  5. ops_router 가 router.py에 등록됨
  6. ops_router 가 각 도우미 함수를 올바른 모듈에서 import
  7. 기존 테스트 파일 36개 보존 확인
  8. opsApiClient가 fallback 경로 포함
  9. ApiStatusBanner 파일 존재
  10. CAD/HWPX/Excel EXTERNAL_APP_HOLD 유지
"""

import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
OPS_ROUTER = REPO / "ai_orchestrator" / "routers" / "ops_router.py"
ROUTER_PY = REPO / "ai_orchestrator" / "routers" / "registry.py"
OPS_CLIENT = REPO / "admin-web" / "src" / "app" / "ops" / "lib" / "opsApiClient.ts"
API_BANNER = REPO / "admin-web" / "src" / "app" / "ops" / "components" / "ApiStatusBanner.tsx"
BOUNDARY_TEST = REPO / "tests" / "app_contracts" / "test_admin_web_ops_dashboard_boundary_20260516.py"


class TestOpsRouterExists:
    def test_ops_router_file_exists(self):
        assert OPS_ROUTER.exists()

    def test_ops_router_registered_in_router_py(self):
        src = ROUTER_PY.read_text(encoding="utf-8")
        assert "from ai_orchestrator.routers.ops_router import ops_router" in src
        assert "router.include_router(ops_router)" in src


class TestOpsRouterReadOnly:
    """ops_router 는 GET 만 제공한다."""

    def _src(self) -> str:
        return OPS_ROUTER.read_text(encoding="utf-8")

    def test_no_post_endpoint(self):
        src = self._src()
        # @ops_router.post 또는 @router.post 가 없어야 한다
        assert "@ops_router.post" not in src
        assert "@ops_router.put" not in src
        assert "@ops_router.delete" not in src
        assert "@ops_router.patch" not in src

    def test_has_get_summary(self):
        assert '@ops_router.get("/summary")' in self._src()

    def test_has_get_approvals(self):
        assert '@ops_router.get("/approvals")' in self._src()

    def test_has_get_web_tasks(self):
        assert '@ops_router.get("/web-tasks")' in self._src()

    def test_has_get_audit_events(self):
        assert '@ops_router.get("/audit-events")' in self._src()

    def test_has_get_agents(self):
        assert '@ops_router.get("/agents")' in self._src()

    def test_has_get_external_work(self):
        assert '@ops_router.get("/external-work")' in self._src()

    def test_has_get_integrations(self):
        assert '@ops_router.get("/integrations")' in self._src()


class TestOpsRouterNoSecretExposure:
    def _src(self) -> str:
        return OPS_ROUTER.read_text(encoding="utf-8")

    def test_no_credential_assignment(self):
        src = self._src()
        bad = re.findall(
            r'(?:password|client_secret|api_key)\s*[:=]\s*["\'][^"\']{8,}["\']',
            src,
            re.I,
        )
        assert bad == [], f"credential 값 발견: {bad}"

    def test_token_hash_not_in_response(self):
        src = self._src()
        assert len(src.splitlines()) > 20, "소스가 비어 있음 — 아래 assert 가 공허하게 통과한다"
        # token_hash 를 응답 dict에 포함하지 않음 — "token_hash" 문자열이 주석/docstring에만 있으면 허용
        # 코드 라인에 "token_hash" 가 dict key로 포함되지 않음
        response_lines = [
            line
            for line in src.splitlines()
            if "token_hash" in line
            and not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("*")
            and not line.strip().startswith("-")
        ]
        assert response_lines == [], f"코드에서 token_hash 노출: {response_lines}"

    def test_no_telegram_send_call(self):
        src = self._src()
        assert "send_message" not in src
        assert "telegram_sender" not in src

    def test_no_external_url_fetch(self):
        src = self._src()
        assert "requests.get" not in src
        assert "httpx" not in src
        # 내부 fetch 는 없고 외부 HTTP 라이브러리 호출 없음
        import_lines = [line for line in src.splitlines() if line.startswith("import ") or line.startswith("from ")]
        external_http = [
            line for line in import_lines if "requests" in line or "httpx" in line or "urllib.request" in line
        ]
        assert import_lines, "import_lines 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
        assert external_http == [], f"외부 HTTP import 발견: {external_http}"

    def test_no_db_write(self):
        src = self._src()
        assert len(src.splitlines()) > 20, "소스가 비어 있음 — 아래 assert 가 공허하게 통과한다"
        for bad in ("INSERT INTO", "UPDATE SET", "DROP TABLE", "TRUNCATE", ".write(", ".delete("):
            code_lines = [
                line
                for line in src.splitlines()
                if bad in line
                and not line.strip().startswith("#")
                and '"""' not in line
                and "'''" not in line
                and "- " not in line.strip()[:3]  # 문서 목록 항목 제외
            ]
            assert code_lines == [], f"DB write 패턴 발견 ({bad}): {code_lines}"


class TestOpsRouterImports:
    def _src(self) -> str:
        return OPS_ROUTER.read_text(encoding="utf-8")

    def test_imports_dev_reg_approval(self):
        assert "from ai_orchestrator.dev_reg.dev_reg_approval import list_pending" in self._src()

    def test_imports_audit_logger(self):
        assert "from ai_orchestrator.audit.audit_logger import read_recent_logs" in self._src()

    def test_imports_web_task_registry(self):
        assert "from ai_orchestrator.web_task.web_task_registry import list_entries" in self._src()

    def test_imports_external_work_registry(self):
        src = self._src()  # 줄이 길면 포매터가 괄호로 나눌 수 있어 모듈 이름과 가져오는 이름을 따로 확인한다
        assert "from ai_orchestrator.tasks.external_work_registry import" in src
        assert "list_external_works" in src

    def test_imports_local_agent_registry(self):
        assert "import local_agent_registry" in self._src() or "as _reg" in self._src()


class TestOpsRouterPythonImport:
    def test_ops_router_importable(self):
        from ai_orchestrator.routers.ops_router import ops_router  # noqa: F401

    def test_ops_router_has_correct_prefix(self):
        from ai_orchestrator.routers.ops_router import ops_router

        assert ops_router.prefix == "/ops"

    def test_ops_router_read_only_endpoints_count(self):
        from ai_orchestrator.routers.ops_router import ops_router

        get_routes = [r for r in ops_router.routes if hasattr(r, "methods") and "GET" in r.methods]
        assert len(get_routes) >= 7, f"GET endpoint 수 부족: {len(get_routes)}"

    def test_ops_router_no_post_routes(self):
        from ai_orchestrator.routers.ops_router import ops_router

        post_routes = [r for r in ops_router.routes if hasattr(r, "methods") and "POST" in r.methods]
        assert ops_router.routes, "ops_router.routes 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
        assert post_routes == [], f"POST endpoint 발견: {post_routes}"


class TestOpsApiClientFallback:
    def _src(self) -> str:
        return OPS_CLIENT.read_text(encoding="utf-8")

    def test_ops_client_file_exists(self):
        assert OPS_CLIENT.exists()

    def test_has_fallback_path(self):
        # 2026-10-05 갱신: 소문자 'fallback' 문구는 사라지고 실패 시 빈 결과로 대체하는
        # emptyResult 와 호환용 …Legacy 함수(결과 data 만 반환)가 폴백 구조를 이룬다.
        src = self._src()
        assert "emptyResult(" in src
        for name in ("fetchApprovalQueueLegacy", "fetchAuditEventsLegacy", "fetchAgentStatusesLegacy"):
            assert f"export async function {name}(" in src, f"누락: {name}"

    def test_has_timeout_handling(self):
        src = self._src()
        assert "timeout" in src.lower() or "AbortSignal" in src or "TIMEOUT" in src

    def test_no_secret_hardcoded(self):
        src = self._src()
        bad = re.findall(
            r'(?:password|client_secret)\s*[:=]\s*["\'][^"\']{8,}["\']',
            src,
            re.I,
        )
        assert bad == [], f"secret 값 발견: {bad}"

    def test_has_fetch_approval_queue(self):
        assert "fetchApprovalQueue" in self._src()

    def test_has_fetch_audit_events(self):
        assert "fetchAuditEvents" in self._src()

    def test_has_fetch_agent_statuses(self):
        assert "fetchAgentStatuses" in self._src()

    def test_has_fetch_dashboard_metrics(self):
        assert "fetchDashboardMetrics" in self._src()

    def test_has_fetch_integrations(self):
        assert "fetchIntegrations" in self._src()


class TestApiStatusBannerExists:
    def test_api_status_banner_file_exists(self):
        assert API_BANNER.exists()

    def test_api_status_banner_has_testid(self):
        src = API_BANNER.read_text(encoding="utf-8")
        assert 'data-testid="api-status-banner"' in src

    def test_api_status_banner_is_client_component(self):
        src = API_BANNER.read_text(encoding="utf-8")
        assert '"use client"' in src

    def test_api_status_banner_no_secret(self):
        src = API_BANNER.read_text(encoding="utf-8")
        bad = re.findall(
            r'(?:password|client_secret)\s*[:=]\s*["\'][^"\']{8,}["\']',
            src,
            re.I,
        )
        assert bad == []


class TestExistingBoundaryTestsUnchanged:
    def test_boundary_test_file_exists(self):
        assert BOUNDARY_TEST.exists()

    def test_boundary_test_has_36_test_functions(self):
        src = BOUNDARY_TEST.read_text(encoding="utf-8")
        count = len(re.findall(r"\bdef test_", src))
        assert count >= 36, f"경계 테스트 수 부족: {count}"

    def test_cad_external_app_hold_in_mock_data(self):
        mock_src = (REPO / "admin-web" / "src" / "app" / "ops" / "lib" / "mockOpsData.ts").read_text(encoding="utf-8")
        # 2026-10-05 갱신: CAD 모듈 삭제(17130f8e)로 CAD 항목은 제거됨 — 현행 EXTERNAL_APP_HOLD 는 HWPX·Excel 2종
        assert "EXTERNAL_APP_HOLD" in mock_src
        for key in ("hwpx-integration", "excel-integration", "hwpx-app", "excel-app"):
            assert f'"{key}"' in mock_src, f"EXTERNAL_APP_HOLD 현행 항목 누락: {key}"
        assert mock_src.count('classification: "EXTERNAL_APP_HOLD"') == 4
        assert "cad" not in mock_src.lower(), "CAD 항목은 17130f8e 로 삭제되어 없어야 한다"

    def test_ops_integrations_static_has_cad_hold(self):
        src = OPS_ROUTER.read_text(encoding="utf-8")
        assert "cad-app" in src
        assert "EXTERNAL_APP_HOLD" in src

    def test_ops_router_integrations_no_execution(self):
        """통합 현황은 정적 데이터만 반환, 실제 연결 테스트 없음."""
        src = OPS_ROUTER.read_text(encoding="utf-8")
        assert "_STATIC_INTEGRATIONS" in src
