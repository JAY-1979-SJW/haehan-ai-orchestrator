"""Tests: APP_TASK_QUEUE_READONLY_LIST_POLISH_01 (2026-05-18)

Task Queue UI read-only 정책 준수 및 보안 경계 검증.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

TASKS_PAGE = assistant_route("tasks", "page.tsx")
TASK_TABLE = ROOT / "admin-web" / "src" / "components" / "assistant" / "TaskTable.tsx"
MOCK_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "mock.ts"
TYPES_FILE = ROOT / "admin-web" / "src" / "types" / "assistant.ts"
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"
COMPOSE_FILE = ROOT / "docker-compose.yml"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture(scope="module")
def page():
    return _src(TASKS_PAGE)


@pytest.fixture(scope="module")
def table():
    return _src(TASK_TABLE)


@pytest.fixture(scope="module")
def mock():
    return _src(MOCK_FILE)


@pytest.fixture(scope="module")
def types():
    return _src(TYPES_FILE)


# ── 파일 존재 ─────────────────────────────────────────────────────────────────
class TestFilesExist:
    def test_tasks_page_exists(self):
        assert TASKS_PAGE.exists()

    def test_task_table_exists(self):
        assert TASK_TABLE.exists()

    def test_mock_exists(self):
        assert MOCK_FILE.exists()

    def test_types_exists(self):
        assert TYPES_FILE.exists()


# ── 화면 헤딩 및 뱃지 ────────────────────────────────────────────────────────
class TestPageHeading:
    def test_heading_task_queue(self, page):
        assert "작업 큐" in page

    def test_dry_run_only_badge(self, page):
        assert "DRY_RUN_ONLY" in page

    def test_mutation_blocked_badge(self, page):
        assert "MUTATION_BLOCKED" in page


# ── read-only 배너 ───────────────────────────────────────────────────────────
class TestReadOnlyBanners:
    def test_read_only_mode_banner(self, page):
        assert "ReadOnlyModeBanner" in page

    def test_forbidden_action_banner(self, page):
        assert "ForbiddenActionBanner" in page

    def test_dry_run_notice(self, page):
        assert "DryRunNotice" in page


# ── 상태 패널 ────────────────────────────────────────────────────────────────
class TestStateHandling:
    def test_mock_fallback_state(self, page):
        assert "mock_fallback" in page

    def test_empty_state_panel(self, page):
        assert "EmptyStatePanel" in page

    def test_error_state(self, page):
        assert "error" in page

    def test_loading_state(self, page):
        assert "loading" in page


# ── TaskTable 컴포넌트 ────────────────────────────────────────────────────────
class TestTaskTableComponents:
    def test_dry_run_badge_component(self, table):
        assert "DryRunBadge" in table

    def test_token_display_component(self, table):
        assert "TokenDisplay" in table

    def test_task_status_legend(self, table):
        assert "TaskStatusLegend" in table

    def test_risk_filter(self, table):
        assert "riskFilter" in table

    def test_status_filter(self, table):
        assert "statusFilter" in table

    def test_risk_badge(self, table):
        assert "RiskBadge" in table

    def test_status_badge(self, table):
        assert "StatusBadge" in table


# ── 필드 렌더링 ──────────────────────────────────────────────────────────────
class TestFieldRendering:
    def test_provider_field(self, table):
        assert "provider" in table

    def test_action_type_field(self, table):
        assert "action_type" in table

    def test_risk_field(self, table):
        assert "risk" in table

    def test_status_field(self, table):
        assert "status" in table

    def test_summary_field(self, table):
        assert "summary" in table


# ── 실행 버튼 없음 (보안 B-1, B-2) ──────────────────────────────────────────
class TestNoActionButtons:
    def test_no_execute_btn(self, table):
        assert "execute_btn" not in table

    def test_no_approve_btn(self, table):
        assert "approve_btn" not in table

    def test_no_reject_btn(self, table):
        assert "reject_btn" not in table

    def test_no_submit_btn(self, table):
        assert "submit_btn" not in table

    def test_no_execute_label_ko(self, table):
        assert ">실행<" not in table


# ── POST mutation 없음 ───────────────────────────────────────────────────────
class TestNoPostMutation:
    def test_no_post_method_table(self, table):
        assert 'method: "POST"' not in table
        assert "method: 'POST'" not in table

    def test_no_post_method_page(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page

    def test_no_execute_url(self, page, table):
        assert "execute_url" not in page
        assert "execute_url" not in table

    def test_no_approve_url(self, page, table):
        assert "approve_url" not in page
        assert "approve_url" not in table

    def test_no_submit_url(self, page, table):
        assert "submit_url" not in page
        assert "submit_url" not in table


# ── 보안: 원문 표시 금지 ─────────────────────────────────────────────────────
class TestSecurityPolicy:
    def test_no_approval_token_raw_table(self, table):
        assert "approval_token_raw" not in table

    def test_no_approval_token_raw_page(self, page):
        assert "approval_token_raw" not in page

    def test_no_approval_token_raw_mock(self, mock):
        assert "approval_token_raw" not in mock

    def test_no_cookie_value_table(self, table):
        assert "cookie_value" not in table

    def test_no_cookie_value_mock(self, mock):
        assert "cookie_value" not in mock

    def test_token_redacted_policy(self, table):
        assert "redacted" in table

    def test_dry_run_badge_policy(self, table):
        assert "DRY_RUN" in table


# ── mock 다양성 ──────────────────────────────────────────────────────────────
class TestMockDiversity:
    def test_mock_dry_run_status(self, mock):
        assert '"DRY_RUN"' in mock

    def test_mock_blocked_status(self, mock):
        assert '"BLOCKED"' in mock

    def test_mock_approval_display_only(self, mock):
        assert '"APPROVAL_DISPLAY_ONLY"' in mock

    def test_mock_read_only_status(self, mock):
        assert '"READ_ONLY"' in mock

    def test_mock_future_status(self, mock):
        assert '"FUTURE"' in mock

    def test_mock_dry_run_null(self, mock):
        assert "dry_run: null" in mock

    def test_mock_blocked_reasons(self, mock):
        assert "blocked_reasons" in mock

    def test_mock_summary_field(self, mock):
        assert "summary" in mock


# ── 타입 확장 ────────────────────────────────────────────────────────────────
class TestTypeExtensions:
    def test_blocked_reasons_type(self, types):
        assert "blocked_reasons" in types

    def test_approval_token_id_type(self, types):
        assert "approval_token_id" in types

    def test_dry_run_nullable_type(self, types):
        assert "boolean | null" in types

    def test_allowed_field_type(self, types):
        assert "allowed" in types

    def test_requires_approval_type(self, types):
        assert "requires_approval" in types


# ── 백엔드/인프라 불변 ───────────────────────────────────────────────────────
class TestBackendUnchanged:
    def test_router_no_task_queue(self):
        src = _src(ROUTER_FILE)
        assert "task_queue" not in src

    def test_compose_no_task_queue(self):
        src = _src(COMPOSE_FILE)
        assert "task_queue" not in src
