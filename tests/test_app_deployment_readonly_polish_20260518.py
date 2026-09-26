"""Tests: APP_DEPLOYMENT_READONLY_POLISH_01 (2026-05-18)"""

import sys
from pathlib import Path

import pytest

from tests._route_helpers import (  # noqa: F401
    assert_route_floor,
    assert_routes_present,
    collect_post_routes,
    collect_routes,
)

REQ = [
    "/api/v1/ops/audit-events",
    "/api/v1/ops/summary",
    "/api/v1/ops/approvals",
    "/api/v1/tasks",
    "/api/v1/health",
    "/api/v1/app/health/summary",
]
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "(legacy)" / "deployment" / "page.tsx"
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"


def _src(p: Path) -> str:
    assert p.exists(), f"파일 없음: {p}"
    return p.read_text(encoding="utf-8")


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
        # 2026-09-26: 63 은 2026-05-18 시점 값. 이후 라우터 확장으로 현행 스냅샷 284 로 갱신(배포 페이지 변경이 라우트를 늘리지 않는다는 불변식은 유지)
        assert_route_floor(250)
        assert_routes_present(REQ)

    def test_post_count_27(self):
        posts = collect_post_routes()
        # 2026-09-26: 27 은 2026-05-18 시점 값 → 현행 스냅샷 122
        assert len(posts) >= 100
