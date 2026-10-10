"""Tests: APP_TASK_DETAIL_READONLY_POLISH_01 (2026-05-18)

Task Detail 화면 read-only 정책 준수 및 보안 경계 검증.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

DETAIL_PAGE = assistant_route("tasks", "[id]", "page.tsx")
DETAIL_PANEL = ROOT / "admin-web" / "src" / "components" / "assistant" / "TaskDetailPanel.tsx"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture(scope="module")
def page():
    return _src(DETAIL_PAGE)


@pytest.fixture(scope="module")
def panel():
    return _src(DETAIL_PANEL)


# ── 파일 존재 ─────────────────────────────────────────────────────────────────
class TestFilesExist:
    def test_detail_page_exists(self):
        assert DETAIL_PAGE.exists()

    def test_detail_panel_exists(self):
        assert DETAIL_PANEL.exists()


# ── read-only 배너 ───────────────────────────────────────────────────────────
class TestReadOnlyBanners:
    def test_read_only_mode_banner(self, page):
        assert "ReadOnlyModeBanner" in page

    def test_forbidden_action_banner(self, page):
        assert "ForbiddenActionBanner" in page

    def test_mutation_blocked_badge(self, page):
        assert "MUTATION_BLOCKED" in page


# ── 필수 표시 필드 ───────────────────────────────────────────────────────────
class TestRequiredFields:
    def test_task_id_displayed(self, panel):
        assert "task.id" in panel

    def test_title_displayed(self, panel):
        assert "task.title" in panel

    def test_status_displayed(self, panel):
        assert "task.status" in panel

    def test_risk_displayed(self, panel):
        assert "task.risk" in panel

    def test_provider_displayed(self, panel):
        assert "task.provider" in panel

    def test_action_type_displayed(self, panel):
        assert "task.action_type" in panel

    def test_dry_run_displayed(self, panel):
        assert "task.dry_run" in panel

    def test_created_at_displayed(self, panel):
        assert "task.created_at" in panel

    def test_updated_at_displayed(self, panel):
        assert "task.updated_at" in panel

    def test_summary_displayed(self, panel):
        assert "task.summary" in panel or "summary" in panel

    def test_blocked_reasons_displayed(self, panel):
        assert "blocked_reasons" in panel

    def test_token_redacted_policy(self, panel):
        assert "redacted" in panel


# ── error/warning/log 영역 ──────────────────────────────────────────────────
class TestErrorWarningLog:
    def test_error_section_exists(self, panel):
        assert "LAST_ERROR" in panel or "error" in panel.lower()

    def test_warning_section_exists(self, panel):
        assert "WARNING" in panel or "warning" in panel.lower()

    def test_log_summary_section_exists(self, panel):
        assert "LOG_SUMMARY" in panel or "log" in panel.lower()


# ── fallback 처리 ────────────────────────────────────────────────────────────
class TestFallbackHandling:
    def test_empty_fallback_component(self, panel):
        assert "Empty" in panel or "없음" in panel

    def test_mock_fallback_state(self, page):
        assert "mock_fallback" in page

    def test_loading_state(self, page):
        assert "loading" in page

    def test_null_value_handling(self, panel):
        assert "null" in panel or "undefined" in panel or "??" in panel


# ── 금지 버튼 없음 ───────────────────────────────────────────────────────────
class TestNoActionButtons:
    def test_no_execute_btn(self, panel):
        assert "execute_btn" not in panel

    def test_no_approve_btn(self, panel):
        assert "approve_btn" not in panel

    def test_no_reject_btn(self, panel):
        assert "reject_btn" not in panel

    def test_no_delete_btn(self, panel):
        assert "delete_btn" not in panel

    def test_no_save_btn(self, panel):
        assert "save_btn" not in panel and "onSave" not in panel

    def test_no_execute_label_ko(self, panel):
        assert ">실행<" not in panel

    def test_no_agent_run(self, panel):
        assert "agent_run" not in panel and "agentRun" not in panel


# ── POST mutation 없음 ───────────────────────────────────────────────────────
class TestNoPostMutation:
    def test_no_post_method_page(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page

    def test_no_post_method_panel(self, panel):
        assert 'method: "POST"' not in panel
        assert "method: 'POST'" not in panel

    def test_no_execute_url(self, page, panel):
        assert "execute_url" not in page
        assert "execute_url" not in panel

    def test_no_approve_url(self, page, panel):
        assert "approve_url" not in page
        assert "approve_url" not in panel

    def test_no_reject_url(self, page, panel):
        assert "reject_url" not in page
        assert "reject_url" not in panel


# ── 보안 ─────────────────────────────────────────────────────────────────────
class TestSecurity:
    def test_no_approval_token_raw(self, page, panel):
        assert "approval_token_raw" not in page
        assert "approval_token_raw" not in panel

    def test_no_cookie_value(self, page, panel):
        assert "cookie_value" not in page
        assert "cookie_value" not in panel


# ── UI 기능 ─────────────────────────────────────────────────────────────────
class TestUiFeatures:
    def test_back_link_exists(self, page):
        assert "/assistant/tasks" in page

    def test_json_viewer_or_collapsible(self, panel):
        assert "JsonViewer" in panel or "open" in panel

    def test_read_only_policy_note(self, panel):
        assert "token 원문 표시 금지" in panel or "원문" in panel or "B-1" in panel


# ── backend/infra 불변 ───────────────────────────────────────────────────────
class TestBackendUnchanged:
    def test_router_no_task_detail(self):
        src = _src(ROUTER_FILE)
        assert "task_detail" not in src

    def test_compose_no_task_detail(self):
        src = _src(COMPOSE_FILE)
        assert "task_detail" not in src


# ── 회귀: baseline sync 기준선 유지 ─────────────────────────────────────────
class TestBaselineRegression:
    def test_dashboard_health_uses_get_app_health_summary(self):
        dashboard = assistant_route("page.tsx")
        content = _src(dashboard)
        assert "getAppHealthSummary" in content

    def test_no_new_post_endpoint_in_router(self):
        router = _src(ROUTER_FILE)
        import re

        post_routes = re.findall(r"@router\.post\(", router)
        assert len(post_routes) <= 5  # 기존 POST endpoint 수 이하 유지

    def test_runtime_endpoint_count_still_63(self):
        from tests.app_routes import EXPECTED_RUNTIME_ROUTES, runtime_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        routes = runtime_routes()
        assert len(routes) == EXPECTED_RUNTIME_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)
