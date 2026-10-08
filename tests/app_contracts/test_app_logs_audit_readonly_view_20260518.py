"""Tests: APP_LOGS_AUDIT_READONLY_VIEW_01 (2026-05-18)

로그·감사 화면 read-only 정책 준수 및 보안 경계 검증.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

LOGS_PAGE = assistant_route("logs", "page.tsx")
AUDIT_LIST = ROOT / "admin-web" / "src" / "components" / "assistant" / "AuditLogList.tsx"
API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"
TYPES_FILE = ROOT / "admin-web" / "src" / "types" / "assistant.ts"
MOCK_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "mock.ts"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture(scope="module")
def page():
    return _src(LOGS_PAGE)


@pytest.fixture(scope="module")
def comp():
    return _src(AUDIT_LIST)


@pytest.fixture(scope="module")
def api():
    return _src(API_FILE)


@pytest.fixture(scope="module")
def types():
    return _src(TYPES_FILE)


@pytest.fixture(scope="module")
def mock():
    return _src(MOCK_FILE)


# ── 파일 존재 ─────────────────────────────────────────────────────────────────
class TestFilesExist:
    def test_logs_page_exists(self):
        assert LOGS_PAGE.exists()

    def test_audit_list_exists(self):
        assert AUDIT_LIST.exists()


# ── use client 전환 ──────────────────────────────────────────────────────────
class TestUseClient:
    def test_logs_page_use_client(self, page):
        assert '"use client"' in page

    def test_audit_list_use_client(self, comp):
        assert '"use client"' in comp


# ── read-only 배너 ───────────────────────────────────────────────────────────
class TestReadOnlyBanners:
    def test_read_only_mode_banner(self, page):
        assert "ReadOnlyModeBanner" in page

    def test_forbidden_action_banner(self, page):
        assert "ForbiddenActionBanner" in page

    def test_mutation_blocked_badge(self, page):
        assert "MUTATION_BLOCKED" in page


# ── API 연결 ─────────────────────────────────────────────────────────────────
class TestApiConnection:
    def test_get_ops_audit_events_in_api(self, api):
        assert "getOpsAuditEvents" in api

    def test_get_ops_audit_events_in_page(self, page):
        assert "getOpsAuditEvents" in page

    def test_ops_audit_events_response_type(self, types):
        assert "OpsAuditEventsResponse" in types

    def test_unified_log_entry_type(self, types):
        assert "UnifiedLogEntry" in types

    def test_ops_audit_event_row_type(self, types):
        assert "OpsAuditEventRow" in types


# ── 정규화 ───────────────────────────────────────────────────────────────────
class TestNormalization:
    def test_normalize_function_exists(self, page):
        assert "normalize" in page

    def test_redacted_true_enforced(self, page):
        assert "redacted: true" in page

    def test_ops_api_source_label(self, page):
        assert "ops-api" in page

    def test_app_mock_source_label(self, page):
        assert "app-mock" in page


# ── 요약 카드 ────────────────────────────────────────────────────────────────
class TestSummaryCards:
    def test_summary_cards_component(self, comp):
        assert "SummaryCards" in comp

    def test_total_events_card(self, comp):
        assert "총 이벤트" in comp

    def test_warn_card(self, comp):
        assert "경고" in comp

    def test_error_card(self, comp):
        assert "오류" in comp


# ── 필터바 ───────────────────────────────────────────────────────────────────
class TestFilterBar:
    def test_level_filter(self, comp):
        assert "levelFilter" in comp

    def test_source_filter(self, comp):
        assert "sourceFilter" in comp

    def test_info_filter_option(self, comp):
        assert '"INFO"' in comp

    def test_warn_filter_option(self, comp):
        assert '"WARN"' in comp

    def test_error_filter_option(self, comp):
        assert '"ERROR"' in comp

    def test_blocked_filter_option(self, comp):
        assert '"BLOCKED"' in comp

    def test_ops_api_source_filter(self, comp):
        assert "ops-api" in comp

    def test_app_mock_source_filter(self, comp):
        assert "app-mock" in comp


# ── 상태 처리 ────────────────────────────────────────────────────────────────
class TestStateHandling:
    def test_loading_state(self, page):
        assert "loading" in page

    def test_mock_fallback_state(self, page):
        assert "mock_fallback" in page

    def test_empty_state(self, page):
        assert "empty" in page

    def test_error_state(self, page):
        assert "error" in page


# ── 필드 표시 ────────────────────────────────────────────────────────────────
class TestFieldDisplay:
    def test_timestamp_displayed(self, comp):
        assert "timestamp" in comp

    def test_level_displayed(self, comp):
        assert "level" in comp

    def test_source_displayed(self, comp):
        assert "source" in comp

    def test_event_type_displayed(self, comp):
        assert "eventType" in comp

    def test_actor_displayed(self, comp):
        assert "actor" in comp

    def test_task_id_displayed(self, comp):
        assert "taskId" in comp

    def test_summary_displayed(self, comp):
        assert "summary" in comp


# ── 금지 버튼 없음 ───────────────────────────────────────────────────────────
class TestNoActionButtons:
    def test_no_execute_btn(self, comp):
        assert "execute_btn" not in comp

    def test_no_approve_btn(self, comp):
        assert "approve_btn" not in comp

    def test_no_delete_btn(self, comp):
        assert "delete_btn" not in comp

    def test_no_execute_label_ko(self, comp):
        assert ">실행<" not in comp


# ── POST mutation 없음 ───────────────────────────────────────────────────────
class TestNoPostMutation:
    def test_no_post_method_page(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page

    def test_no_post_method_comp(self, comp):
        assert 'method: "POST"' not in comp

    def test_no_execute_url(self, page, comp):
        assert "execute_url" not in page
        assert "execute_url" not in comp

    def test_no_approve_url(self, page, comp):
        assert "approve_url" not in page
        assert "approve_url" not in comp


# ── 보안 ─────────────────────────────────────────────────────────────────────
class TestSecurity:
    def test_no_approval_token_raw(self, page, comp):
        assert "approval_token_raw" not in page
        assert "approval_token_raw" not in comp

    def test_no_cookie_value(self, page, comp):
        assert "cookie_value" not in page
        assert "cookie_value" not in comp

    def test_redacted_policy_note(self, comp):
        assert "token 원문 표시 금지" in comp or "secret/token/cookie" in comp


# ── API endpoint 계약 ────────────────────────────────────────────────────────
class TestApiContract:
    @staticmethod
    def _authed_client():
        # 2026-10-04 갱신: ops API 는 JWT 인증이 필수가 됨 — 인증 의존성을 시험용 사용자로 대체해 응답 계약만 검증.
        from fastapi.testclient import TestClient

        from ai_orchestrator.auth.user_auth_router import get_jwt_user
        from ai_orchestrator.asgi import app

        app.dependency_overrides[get_jwt_user] = lambda: {"actor": "owner-test", "role": "owner"}
        return app, TestClient(app, raise_server_exceptions=False)

    def test_ops_audit_events_200(self):
        app, client = self._authed_client()
        try:
            r = client.get("/api/v1/ops/audit-events")
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200

    def test_ops_summary_200(self):
        app, client = self._authed_client()
        try:
            r = client.get("/api/v1/ops/summary")
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200

    def test_endpoint_count_still_63(self):
        from tests.app_routes import EXPECTED_RUNTIME_ROUTES, runtime_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        routes = runtime_routes()
        assert len(routes) == EXPECTED_RUNTIME_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)

    def test_no_new_post_endpoint(self):
        from tests.app_routes import EXPECTED_POST_ROUTES, http_routes

        # 2026-10-04 갱신: app.routes 직접 순회는 지연 include_router 로 0개 — 펼친 목록의 현재 POST 수(앞선 개수 시험과 같은 기준 184)
        posts = [r for r in http_routes() if "POST" in r.method.split(",")]
        assert len(posts) == EXPECTED_POST_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)


# ── mock 다양성 ──────────────────────────────────────────────────────────────
class TestMockDiversity:
    def test_mock_has_error_level(self, mock):
        assert "ERROR" in mock

    def test_mock_has_warn_level(self, mock):
        assert "WARN" in mock

    def test_mock_has_info_level(self, mock):
        assert "INFO" in mock

    def test_mock_audit_logs_exist(self, mock):
        assert "auditLogsMock" in mock


# ── 회귀: baseline sync 유지 ─────────────────────────────────────────────────
class TestBaselineRegression:
    def test_dashboard_uses_get_app_health_summary(self):
        dashboard = assistant_route("page.tsx")
        assert "getAppHealthSummary" in _src(dashboard)

    def test_task_queue_uses_task_table(self):
        tasks = assistant_route("tasks", "page.tsx")
        assert "TaskTable" in _src(tasks)

    def test_task_detail_read_only_panel(self):
        detail = ROOT / "admin-web" / "src" / "components" / "assistant" / "TaskDetailPanel.tsx"
        assert "TaskDetailPanel" in _src(detail)

    def test_router_no_logs_router(self):
        assert "logs_router" not in _src(ROUTER_FILE)
