"""Tests: APP_DEPLOYMENT_READONLY_POLISH_01 (2026-05-18)"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

PAGE = assistant_route("deployment", "page.tsx")
ROUTER_FILE = ROOT / "ai_orchestrator" / "routers" / "registry.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


@pytest.fixture(scope="module")
def page():
    return _src(PAGE)


class TestFilesExist:
    def test_page_exists(self):
        assert PAGE.exists()


class TestUseClient:
    def test_use_client(self, page):
        assert '"use client"' in page


class TestBanners:
    def test_readonly_mode_banner(self, page):
        assert "ReadOnlyModeBanner" in page

    def test_forbidden_action_banner(self, page):
        assert "ForbiddenActionBanner" in page

    def test_mutation_blocked_badge(self, page):
        assert "MUTATION_BLOCKED" in page

    def test_server_apply_allowed_false(self, page):
        assert "server_apply_allowed=false" in page


class TestSopPanel:
    def test_baked_in_image_sop(self, page):
        assert "BAKED_IN_IMAGE" in page

    def test_restart_alone_forbidden(self, page):
        assert "RESTART_ALONE_FORBIDDEN" in page

    def test_sop_steps_displayed(self, page):
        assert "sop_steps" in page

    def test_deployment_sop_panel(self, page):
        assert "DeploymentSopPanel" in page


class TestSummaryCards:
    def test_server_head_card(self, page):
        assert "서버 HEAD" in page

    def test_sync_state_card(self, page):
        assert "동기화 상태" in page

    def test_build_required_card(self, page):
        assert "빌드 필요" in page


class TestMockUsage:
    def test_deployment_status_mock(self, page):
        assert "deploymentStatusMock" in page


class TestNoActionButtons:
    def test_no_restart_btn(self, page):
        assert "restart_btn" not in page

    def test_no_compose_btn(self, page):
        assert "compose_btn" not in page


class TestSecurity:
    def test_no_approval_token_raw(self, page):
        assert "approval_token_raw" not in page

    def test_no_post_method(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page


class TestBackendInvariant:
    def test_no_deployment_router(self):
        assert "deployment_router" not in _src(ROUTER_FILE)

    def test_endpoint_count_63(self):
        from tests.app_routes import EXPECTED_RUNTIME_ROUTES, runtime_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        routes = runtime_routes()
        assert len(routes) == EXPECTED_RUNTIME_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)

    def test_post_count_27(self):
        from tests.app_routes import EXPECTED_POST_ROUTES, http_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        posts = [r for r in http_routes() if "POST" in r.method.split(",")]
        assert len(posts) == EXPECTED_POST_ROUTES  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)
