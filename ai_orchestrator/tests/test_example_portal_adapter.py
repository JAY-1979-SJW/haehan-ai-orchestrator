"""ExamplePortalAdapter — mock page 기반 검증. 실제 접속 없음."""

from __future__ import annotations

from collections.abc import Collection
from unittest.mock import MagicMock

import pytest

from ai_orchestrator.sites.adapters.example_portal_adapter import ExamplePortalAdapter
from ai_orchestrator.sites.site_adapter import LoginCheckResult


@pytest.fixture()
def adapter() -> ExamplePortalAdapter:
    return ExamplePortalAdapter()


def _mock_page(url: str = "https://example.test/", selectors: Collection[str] | None = None) -> MagicMock:
    page = MagicMock()
    page.url = url
    sel_map = selectors or {}
    page.query_selector.side_effect = lambda s: MagicMock() if s in sel_map else None
    return page


# ── open_home: page.goto 만 호출 ──────────────────────────────────
class TestOpenHome:
    def test_goto_called_with_home_url(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        adapter.open_home(page)
        page.goto.assert_called_once_with(ExamplePortalAdapter.HOME_URL)

    def test_no_click_fill_type_press(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        adapter.open_home(page)
        page.click.assert_not_called()
        page.fill.assert_not_called()
        page.type.assert_not_called()
        page.press.assert_not_called()


# ── open_login_page: page.goto 만 호출 ──────────────────────────
class TestOpenLoginPage:
    def test_goto_called_with_login_url(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        adapter.open_login_page(page)
        page.goto.assert_called_once_with(ExamplePortalAdapter.LOGIN_URL)

    def test_no_fill_no_submit(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        adapter.open_login_page(page)
        page.fill.assert_not_called()
        page.click.assert_not_called()


# ── check_logged_in ─────────────────────────────────────────────
class TestCheckLoggedIn:
    def test_redirected_to_login_url(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page(url="https://example.test/login?next=/")
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is False
        assert result.reason == "redirected_to_login"

    def test_logged_in_when_selector_present(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page(
            url="https://example.test/",
            selectors={"#user-menu"},
        )
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is True
        assert result.reason == "logged_in_signals_matched"

    def test_no_user_menu_not_logged_in(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page(url="https://example.test/")
        result = adapter.check_logged_in(page)
        assert result.is_logged_in is False
        assert result.reason == "no_user_menu"

    def test_result_is_logincheckresult(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        result = adapter.check_logged_in(page)
        assert isinstance(result, LoginCheckResult)

    def test_no_write_actions_during_check(self, adapter: ExamplePortalAdapter) -> None:
        page = _mock_page()
        adapter.check_logged_in(page)
        page.click.assert_not_called()
        page.fill.assert_not_called()
        page.type.assert_not_called()
        page.press.assert_not_called()
        page.goto.assert_not_called()
