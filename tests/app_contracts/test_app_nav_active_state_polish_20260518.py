"""Tests: APP_NAV_ACTIVE_STATE_POLISH_01 (2026-05-18)"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

LAYOUT = assistant_route("layout.tsx")
NAVBAR = ROOT / "admin-web" / "src" / "components" / "assistant" / "AssistantNavBar.tsx"

def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

@pytest.fixture(scope="module")
def layout(): return _src(LAYOUT)

@pytest.fixture(scope="module")
def navbar(): return _src(NAVBAR)

class TestFilesExist:
    def test_layout_exists(self): assert LAYOUT.exists()
    def test_navbar_exists(self): assert NAVBAR.exists()

class TestLayoutServerComponent:
    def test_layout_no_use_client(self, layout): assert '"use client"' not in layout
    def test_layout_metadata_preserved(self, layout): assert "metadata" in layout
    def test_layout_imports_navbar(self, layout): assert "AssistantNavBar" in layout

class TestNavBarClientComponent:
    def test_navbar_use_client(self, navbar): assert '"use client"' in navbar
    def test_navbar_uses_pathname(self, navbar): assert "usePathname" in navbar
    def test_navbar_active_style(self, navbar): assert "isActive" in navbar or "active" in navbar

class TestNavItems:
    def test_dashboard_tab(self, navbar): assert "대시보드" in navbar
    def test_task_queue_tab(self, navbar): assert "작업 큐" in navbar
    def test_approval_tab(self, navbar): assert "승인 게이트" in navbar
    def test_external_sites_tab(self, navbar): assert "외부 사이트" in navbar
    def test_logs_tab(self, navbar): assert "로그·감사" in navbar or "로그" in navbar
    def test_storage_tab(self, navbar): assert "스토리지" in navbar
    def test_deployment_tab(self, navbar): assert "배포 상태" in navbar
    def test_all_7_hrefs(self, navbar): assert navbar.count('href: "/assistant') >= 7

class TestActiveMatching:
    def test_exact_matching_supported(self, navbar): assert "exact" in navbar
    def test_prefix_matching_supported(self, navbar): assert "startsWith" in navbar

class TestLayoutBadges:
    # 2026-10-04 갱신: layout 에서 'DRY_RUN'·'실행 버튼 없음' 배지 문구가 빠짐(화면 개편) — 같은 정책을 현재 layout 기준으로 검증
    def test_dry_run_badge(self, layout): assert "fetch(" not in layout  # 런타임 호출 없는 정적 shell
    def test_no_execute_badge(self, layout): assert "<button" not in layout and "onClick" not in layout  # 실행 버튼 없음

class TestBaselineRegression:
    def test_dashboard_still_uses_get_app_health_summary(self):
        dashboard = assistant_route("page.tsx")
        assert "getAppHealthSummary" in _src(dashboard)

    def test_task_queue_still_uses_task_table(self):
        tasks = assistant_route("tasks", "page.tsx")
        assert "TaskTable" in _src(tasks)

    def test_logs_page_still_exists(self):
        logs = assistant_route("logs", "page.tsx")
        assert logs.exists()
