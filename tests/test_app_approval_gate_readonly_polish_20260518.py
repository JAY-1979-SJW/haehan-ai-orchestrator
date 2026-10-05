"""Tests: APP_APPROVAL_GATE_READONLY_POLISH_01 (2026-05-18)"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

PAGE = assistant_route("approval", "page.tsx")
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


@pytest.fixture(scope="module")
def page():
    return _src(PAGE)


class TestFilesExist:
    def test_approval_page_exists(self):
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

    def test_b1_pending_badge(self, page):
        assert "B1_PENDING" in page


class TestSummaryCards:
    def test_total_gates_card(self, page):
        assert "전체 게이트" in page

    def test_blocked_card(self, page):
        assert "BLOCKED" in page

    def test_not_connected_card(self, page):
        assert "미연결" in page


class TestMockUsage:
    def test_approval_gates_mock(self, page):
        assert "approvalGatesMock" in page

    def test_known_backlog_mock(self, page):
        assert "knownBacklogMock" in page


class TestB1Panel:
    def test_b1_pending_panel(self, page):
        assert "B-1" in page or "B1" in page

    def test_intentional_incomplete_note(self, page):
        assert "INTENTIONAL_INCOMPLETE" in page


class TestNoActionButtons:
    def test_no_approve_btn(self, page):
        assert "approve_btn" not in page

    def test_no_delete_btn(self, page):
        assert "delete_btn" not in page

    def test_no_execute_btn(self, page):
        assert "execute_btn" not in page

    def test_no_execute_label_ko(self, page):
        assert ">실행<" not in page


class TestNoPostMutation:
    def test_no_post_method(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page


class TestSecurity:
    def test_no_approval_token_raw(self, page):
        assert "approval_token_raw" not in page

    def test_no_cookie_value(self, page):
        assert "cookie_value" not in page

    def test_token_policy_note(self, page):
        assert "token 원문" in page


class TestBackendInvariant:
    def test_router_no_approval_gate_router(self):
        assert "approval_gate_router" not in _src(ROUTER_FILE)

    def test_endpoint_count_63(self):
        from tests.app_routes import runtime_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        routes = runtime_routes()
        assert len(routes) == 427  # [427=425+2: 사이트 사전 조사 /site-registry/{host}/preflight GET·POST 2개 추가(M10, 삭제 0); 이전 425=424+1: 가입 카페 변동 조회 GET /naver-cafe/my-cafes/changes 1개 추가(2026-10-05), 삭제 0] [424=419+5: /site-registry 5개 추가(2026-10-05 M7-S1)] 2026-10-04: origin/master 402(/dev-reg/approvals GET 3개 복원) + 이 브랜치의 공무 AI 초안·사이트 업무 지도·벤더 조회 17개(삭제 0)

    def test_post_count_27(self):
        from tests.app_routes import http_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        posts = [r for r in http_routes() if "POST" in r.method.split(",")]
        assert len(posts) == 196  # [196=195+1: POST /site-registry/{host}/preflight(2026-10-05 M10)] [195=193+2: /site-registry POST 2개(2026-10-05 M7-S1)] 위 추가분 중 POST 9개(184→193)
