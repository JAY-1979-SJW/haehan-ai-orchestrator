"""Tests: APP_EXTERNAL_SITES_READONLY_POLISH_01 (2026-05-18)"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

PAGE = assistant_route("external-sites", "page.tsx")
API_FILE = ROOT / "admin-web" / "src" / "lib" / "assistant" / "api.ts"

def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

@pytest.fixture(scope="module")
def page(): return _src(PAGE)

@pytest.fixture(scope="module")
def api(): return _src(API_FILE)

class TestFilesExist:
    def test_page_exists(self): assert PAGE.exists()

class TestUseClient:
    def test_use_client(self, page): assert '"use client"' in page

class TestBanners:
    def test_readonly_mode_banner(self, page): assert "ReadOnlyModeBanner" in page
    def test_forbidden_action_banner(self, page): assert "ForbiddenActionBanner" in page
    def test_mutation_blocked_badge(self, page): assert "MUTATION_BLOCKED" in page

class TestApiConnection:
    def test_get_app_providers_page(self, page): assert "getAppProviders" in page
    def test_get_app_providers_api(self, api): assert "getAppProviders" in api
    def test_mock_fallback_state(self, page): assert "mock_fallback" in page
    def test_api_connection_state_badge(self, page): assert "ApiConnectionStateBadge" in page

class TestSummaryCards:
    def test_total_providers(self, page): assert "전체 공급자" in page
    def test_high_risk_card(self, page): assert "HIGH+" in page or "highRisk" in page
    def test_auth_required_card(self, page): assert "인증 필요" in page

class TestComponents:
    def test_provider_card_used(self, page): assert "ProviderCard" in page
    def test_external_providers_mock(self, page): assert "externalProvidersMock" in page

class TestNoActionButtons:
    def test_no_login_btn(self, page): assert "login_btn" not in page
    def test_no_submit_btn(self, page): assert "submit_btn" not in page

class TestSecurity:
    def test_no_approval_token_raw(self, page): assert "approval_token_raw" not in page
    def test_no_cookie_value(self, page): assert "cookie_value" not in page
    def test_no_post_method(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page
