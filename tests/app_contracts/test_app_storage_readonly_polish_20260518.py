"""Tests: APP_STORAGE_READONLY_POLISH_01 (2026-05-18)"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.app_ui_paths import assistant_route  # noqa: E402

PAGE = assistant_route("storage", "page.tsx")

def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""

@pytest.fixture(scope="module")
def page(): return _src(PAGE)

class TestFilesExist:
    def test_page_exists(self): assert PAGE.exists()

class TestUseClient:
    def test_use_client(self, page): assert '"use client"' in page

class TestBanners:
    def test_readonly_mode_banner(self, page): assert "ReadOnlyModeBanner" in page
    def test_mutation_blocked_badge(self, page): assert "MUTATION_BLOCKED" in page

class TestApiConnection:
    def test_get_app_storage_status(self, page): assert "getAppStorageStatus" in page
    def test_mock_fallback(self, page): assert "mock_fallback" in page
    def test_api_connection_state_badge(self, page): assert "ApiConnectionStateBadge" in page

class TestSummaryCards:
    def test_mount_count_card(self, page): assert "마운트 수" in page
    def test_persistent_card(self, page): assert "PERSISTENT" in page
    def test_disposable_card(self, page): assert "DISPOSABLE" in page

class TestComponents:
    def test_storage_status_card(self, page): assert "StorageStatusCard" in page
    def test_storage_status_mock(self, page): assert "storageStatusMock" in page

class TestB3Panel:
    def test_b3_audit_pending(self, page): assert "B-3" in page or "B3" in page
    def test_approval_tokens_note(self, page): assert "approval_tokens" in page
    def test_token_policy(self, page): assert "token 원문" in page

class TestNoActionButtons:
    def test_no_delete_btn(self, page): assert "delete_btn" not in page
    def test_no_format_btn(self, page): assert "format_btn" not in page

class TestSecurity:
    def test_no_approval_token_raw(self, page): assert "approval_token_raw" not in page
    def test_no_cookie_value(self, page): assert "cookie_value" not in page
    def test_no_post_method(self, page):
        assert 'method: "POST"' not in page
        assert "method: 'POST'" not in page
