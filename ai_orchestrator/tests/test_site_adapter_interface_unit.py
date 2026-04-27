"""SiteAdapter 인터페이스 계약 검증 — 외부 접속 없음."""
from __future__ import annotations

import pytest

from ai_orchestrator.sites.site_adapter import (
    LoginCheckResult,
    ReauthWaitResult,
    SiteAdapter,
)


# ── LoginCheckResult ────────────────────────────────────────────
class TestLoginCheckResult:
    def test_basic_creation(self) -> None:
        r = LoginCheckResult(is_logged_in=True)
        assert r.is_logged_in is True
        assert r.reason == ""
        assert r.detected_url == ""
        assert r.matched_signals == []

    def test_to_dict_keys(self) -> None:
        r = LoginCheckResult(
            is_logged_in=False,
            reason="redirected_to_login",
            detected_url="https://example.test/login",
            matched_signals=["url_hint:/login"],
        )
        d = r.to_dict()
        assert set(d.keys()) == {"is_logged_in", "reason", "detected_url", "matched_signals"}
        assert d["is_logged_in"] is False
        assert d["reason"] == "redirected_to_login"

    def test_to_dict_no_sensitive_fields(self) -> None:
        r = LoginCheckResult(is_logged_in=True, reason="ok")
        d = r.to_dict()
        for bad in ("password", "token", "cookie", "session", "otp", "secret"):
            assert bad not in d


# ── SiteAdapter 직접 인스턴스화 불가 ────────────────────────────
class TestSiteAdapterAbstract:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            SiteAdapter()  # type: ignore[abstract]

    def test_minimal_subclass_contract(self) -> None:
        class MinimalAdapter(SiteAdapter):
            site_id = "test_site"

            def open_home(self, page):
                pass

            def check_logged_in(self, page):
                return LoginCheckResult(is_logged_in=True, reason="ok")

            def open_login_page(self, page):
                pass

        adapter = MinimalAdapter()
        assert adapter.site_id == "test_site"

        result = adapter.check_logged_in(object())
        assert isinstance(result, LoginCheckResult)
        assert result.is_logged_in is True

    def test_collect_list_default_returns_empty(self) -> None:
        class MinAdapter(SiteAdapter):
            site_id = "s"

            def open_home(self, page):
                pass

            def check_logged_in(self, page):
                return LoginCheckResult(is_logged_in=True)

            def open_login_page(self, page):
                pass

        adapter = MinAdapter()
        result = adapter.collect_list(object())
        assert result["items"] == []
        assert result["done"] is True

    def test_wait_for_human_reauth_succeeds_immediately(self) -> None:
        """sleeper/clock 주입으로 시간 의존성 제거 후 즉시 성공 확인."""
        class ImmediateAdapter(SiteAdapter):
            site_id = "s"

            def open_home(self, page):
                pass

            def check_logged_in(self, page):
                return LoginCheckResult(is_logged_in=True, reason="ok")

            def open_login_page(self, page):
                pass

        adapter = ImmediateAdapter()
        t = [0.0]

        def clock():
            v = t[0]
            t[0] += 1.0
            return v

        result = adapter.wait_for_human_reauth(
            object(),
            timeout_sec=10,
            poll_interval_sec=1.0,
            sleeper=lambda _: None,
            clock=clock,
        )
        assert isinstance(result, ReauthWaitResult)
        assert result.succeeded is True

    def test_wait_for_human_reauth_times_out(self) -> None:
        """항상 미로그인을 반환하는 어댑터가 타임아웃되는지 확인."""
        class NeverAdapter(SiteAdapter):
            site_id = "s"

            def open_home(self, page):
                pass

            def check_logged_in(self, page):
                return LoginCheckResult(is_logged_in=False, reason="no_user_menu")

            def open_login_page(self, page):
                pass

        adapter = NeverAdapter()
        t = [0.0]

        def clock():
            v = t[0]
            t[0] += 10.0
            return v

        result = adapter.wait_for_human_reauth(
            object(),
            timeout_sec=5,
            poll_interval_sec=1.0,
            sleeper=lambda _: None,
            clock=clock,
        )
        assert result.succeeded is False
        assert result.timed_out is True
