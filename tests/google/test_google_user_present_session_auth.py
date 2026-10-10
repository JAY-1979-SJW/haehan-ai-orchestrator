from __future__ import annotations

import pytest


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []

    def goto(self, url: str, **_kwargs) -> None:
        self.url = url
        self.goto_calls.append(url)


def test_google_login_defaults_to_user_present_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.google import auth

    page = _FakePage()
    assert auth.GOOGLE_LOGIN_URL == "https://www.google.com/"
    assert not hasattr(auth, "_load_credentials")
    assert not hasattr(auth, "save_credentials")
    assert not hasattr(auth, "_safe_human_input")
    monkeypatch.setattr(auth, "detect_login_state", lambda _page: {"logged_in": False})
    monkeypatch.setattr(
        auth,
        "wait_for_login_generic",
        lambda _page, **_kwargs: {
            "logged_in": True,
            "user": "user@example.com",
        },
    )

    result = auth.login_google(page, wait_for_user_s=1)

    assert result["ok"] is True
    assert result["method"] == "user_present_session"
    assert result["reason"] == "user_present_login_completed"
    assert page.goto_calls == [auth.GOOGLE_LOGIN_URL]


def test_google_login_reuses_existing_session_without_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.google import auth

    page = _FakePage("https://mail.google.com/mail/u/0/")
    monkeypatch.setattr(
        auth,
        "detect_login_state",
        lambda _page: {"logged_in": True, "user": "user@example.com"},
    )

    result = auth.login_google(page, wait_for_user_s=1)

    assert result["ok"] is True
    assert result["method"] == "user_present_session"
    assert result["reason"] == "already_logged_in"
    assert page.goto_calls == []


def test_google_login_timeout_is_safe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.google import auth

    page = _FakePage()
    monkeypatch.setattr(auth, "detect_login_state", lambda _page: {"logged_in": False})
    monkeypatch.setattr(auth, "wait_for_login_generic", lambda _page, **_kwargs: {"logged_in": False})

    result = auth.login_google(page, wait_for_user_s=1)

    assert result["ok"] is False
    assert result["method"] == "user_present_session"
    assert result["reason"] == "user_present_login_timeout"


def test_google_login_gate_blocks_direct_accounts_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.google import auth

    page = _FakePage()
    monkeypatch.setattr(auth, "GOOGLE_LOGIN_URL", "https://accounts.google.com/signin")
    monkeypatch.setattr(auth, "detect_login_state", lambda _page: {"logged_in": False})

    with pytest.raises(ValueError, match="FORBIDDEN_LOGIN_URL_DIRECT_ENTRY"):
        auth.login_google(page, wait_for_user_s=1)

    assert page.goto_calls == []


def test_google_login_probe_gate_blocks_direct_accounts_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.site_engine import login_session

    page = _FakePage()
    monkeypatch.setitem(login_session.LOGIN_PROBE_URLS, "google", "https://accounts.google.com/signin")

    with pytest.raises(ValueError, match="FORBIDDEN_LOGIN_URL_DIRECT_ENTRY"):
        login_session._probe(page, "google", [], [])

    assert page.goto_calls == []
