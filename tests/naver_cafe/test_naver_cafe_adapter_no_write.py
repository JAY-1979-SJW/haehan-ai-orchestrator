"""NaverCafeAdapter — read-only 판정 검증. 실제 naver.com 접속 없음."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_orchestrator.sites.adapters.naver_cafe_adapter import NaverCafeAdapter
from ai_orchestrator.sites.site_adapter import LoginCheckResult


@pytest.fixture()
def adapter() -> NaverCafeAdapter:
    return NaverCafeAdapter()


def _mock_page(url: str = "https://cafe.naver.com/", selectors: set | None = None) -> MagicMock:
    page = MagicMock()
    page.url = url
    sel_set = selectors or set()
    page.query_selector.side_effect = lambda s: MagicMock() if s in sel_set else None
    return page


# ── open_home / open_login_page: goto 만 ────────────────────────
class TestNaverCafeNavigation:
    def test_open_home_goto_only(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page()
        adapter.open_home(page)
        page.goto.assert_called_once_with(NaverCafeAdapter.HOME_URL)
        page.click.assert_not_called()
        page.fill.assert_not_called()
        page.type.assert_not_called()
        page.press.assert_not_called()

    def test_open_login_page_goto_only(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page()
        adapter.open_login_page(page)
        page.goto.assert_called_once_with(NaverCafeAdapter.LOGIN_URL)
        page.fill.assert_not_called()
        page.click.assert_not_called()


# ── check_logged_in: 판정 로직 (read-only) ───────────────────────
class TestCheckLoggedIn:
    def test_reauth_url_hint_detected(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page(url="https://nid.naver.com/login2?...")
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is False
        assert result.reason == "reauth_required"

    def test_login_url_hint_detected(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page(url="https://nid.naver.com/nidlogin.login?next=...")
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is False
        assert result.reason == "redirected_to_login"

    def test_logged_in_when_gnb_selector_present(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page(
            url="https://cafe.naver.com/",
            selectors={"a#gnb_logout_button"},
        )
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is True
        assert result.reason == "logged_in_signals_matched"

    def test_no_signals_returns_no_user_menu(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page(url="https://cafe.naver.com/")
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is False
        assert result.reason == "no_user_menu"

    def test_check_logged_in_no_write_actions(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page()
        adapter.check_logged_in(page)
        page.click.assert_not_called()
        page.fill.assert_not_called()
        page.type.assert_not_called()
        page.press.assert_not_called()
        page.goto.assert_not_called()

    def test_result_type(self, adapter: NaverCafeAdapter) -> None:
        page = _mock_page()
        result = adapter.check_logged_in(page)
        assert isinstance(result, LoginCheckResult)

    def test_reauth_hints_take_priority_over_login_hints(self, adapter: NaverCafeAdapter) -> None:
        """REAUTH_URL_HINTS 가 LOGIN_URL_HINTS 보다 먼저 판정되는지 확인."""
        # otp URL 은 REAUTH_URL_HINTS 에 속하며 동시에 nid.naver.com 경로임
        page = _mock_page(url="https://nid.naver.com/otp/check")
        result = adapter.check_logged_in(page)
        assert result.reason == "reauth_required"

    def test_no_naver_real_url_access(self, adapter: NaverCafeAdapter) -> None:
        """HOME_URL 가 실제 naver.com 접속 없이 mock page 에서 동작하는지 확인."""
        page = _mock_page(url=NaverCafeAdapter.HOME_URL)
        # 실제 goto 없이 check_logged_in 만 호출해도 결과가 나와야 함
        result = adapter.check_logged_in(page)
        assert isinstance(result, LoginCheckResult)
        page.goto.assert_not_called()
