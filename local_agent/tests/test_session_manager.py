"""Unit tests for local_agent.session_manager — KAKAO-SESSION-2."""
from __future__ import annotations

import inspect
import os
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers: fake browser/context/page fixtures
# ---------------------------------------------------------------------------


def _make_fake_page(
    *,
    url: str = "https://example.com/dashboard",
    title_val: str = "Dashboard",
    content_val: str = "<html><body>Welcome</body></html>",
    query_selector_result: Any = None,
) -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title.return_value = title_val
    page.content.return_value = content_val
    page.query_selector.return_value = query_selector_result
    # Never return a value from input_value — test verifies it's never called
    page.input_value = MagicMock(side_effect=AssertionError(
        "input_value must never be called"
    ))
    page.evaluate = MagicMock(side_effect=AssertionError(
        "evaluate must never be called"
    ))
    page.goto = MagicMock(return_value=None)
    page.bring_to_front = MagicMock(return_value=None)
    return page


def _make_fake_context(page: MagicMock) -> MagicMock:
    context = MagicMock()
    context.new_page.return_value = page
    context.storage_state.return_value = None
    context.pages = [page]
    return context


def _make_fake_browser(context: MagicMock) -> MagicMock:
    browser = MagicMock()
    browser.new_context.return_value = context
    return browser


def _make_fake_pw(browser: MagicMock) -> MagicMock:
    pw = MagicMock()
    pw.chromium.launch.return_value = browser
    return pw


class _FakePWContextManager:
    """Fake playwright context manager."""

    def __init__(self, pw: MagicMock) -> None:
        self._pw = pw

    def __enter__(self) -> MagicMock:
        return self._pw

    def __exit__(self, *args: Any) -> None:
        pass

    def __call__(self) -> "_FakePWContextManager":
        return self


def _make_factory(
    *,
    url: str = "https://example.com/dashboard",
    title_val: str = "Dashboard",
    content_val: str = "<html><body>Welcome</body></html>",
    query_selector_result: Any = None,
) -> tuple[_FakePWContextManager, MagicMock, MagicMock, MagicMock]:
    page = _make_fake_page(
        url=url,
        title_val=title_val,
        content_val=content_val,
        query_selector_result=query_selector_result,
    )
    context = _make_fake_context(page)
    browser = _make_fake_browser(context)
    pw = _make_fake_pw(browser)
    factory = _FakePWContextManager(pw)
    return factory, pw, browser, page


class _FakeClock:
    """Fake monotonic clock for deterministic tests."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self._t = start
        self._step = step

    def monotonic(self) -> float:
        return self._t

    def sleep(self, secs: float) -> None:
        self._t += secs

    def advance(self, secs: float) -> None:
        self._t += secs


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from local_agent import session_manager as sm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_state_dir(tmp_path: Path) -> Path:
    state_dir = tmp_path / "secrets" / "browser_state"
    state_dir.mkdir(parents=True)
    return state_dir


@pytest.fixture()
def patch_state_path(tmp_state_dir: Path):
    """Patch secrets_policy.session_state_path to use tmp dir."""
    def _fake_path(site_name: str) -> Path:
        return tmp_state_dir / f"{site_name}.json"

    with patch.object(sm.secrets_policy, "session_state_path", side_effect=_fake_path):
        yield tmp_state_dir


# ---------------------------------------------------------------------------
# 1. test_reused_session_returns_without_browser
# ---------------------------------------------------------------------------

def test_reused_session_returns_without_browser(
    patch_state_path: Path,
) -> None:
    """State file exists → ensure_session returns state='reused', no browser launched."""
    state_file = patch_state_path / "mysite.json"
    state_file.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    factory_called = []

    def spy_factory() -> Any:
        factory_called.append(True)
        return MagicMock()

    result = sm.ensure_session(
        "mysite",
        "https://example.com/login",
        _browser_factory=spy_factory,
        _input_reader=lambda _: "",
    )
    assert result.ok is True
    assert result.state == "reused"
    assert result.storage_state_path == state_file
    assert not factory_called, "Browser factory must NOT be called on reuse"


# ---------------------------------------------------------------------------
# 2. test_captured_session_saves_storage_state
# ---------------------------------------------------------------------------

def test_captured_session_saves_storage_state(
    patch_state_path: Path,
) -> None:
    """No state file → mock browser, user confirms login, storage_state() called."""
    factory, pw, browser, page = _make_factory(
        url="https://example.com/dashboard",
        content_val="<html><body><h1>Welcome</h1></body></html>",
    )
    context = browser.new_context.return_value
    # Simulate storage_state call writing a file
    def fake_storage_state(path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    context.storage_state.side_effect = fake_storage_state

    clock = _FakeClock(start=0.0, step=5.0)
    # Make deadline expire quickly so loop ends
    clock._t = 10000.0  # huge monotonic start so deadline already passed

    answers = iter(["", ""])  # first = login confirmed, second = save confirm

    result = sm.ensure_session(
        "mysite2",
        "https://example.com/login",
        wait_seconds=10,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda prompt: next(answers),
    )
    assert result.ok is True, f"Expected ok=True but got: {result}"
    assert result.state == "captured"
    context.storage_state.assert_called_once()


# ---------------------------------------------------------------------------
# 3. test_expired_session_triggers_recapture
# ---------------------------------------------------------------------------

def test_expired_session_triggers_recapture(
    patch_state_path: Path,
) -> None:
    """ensure_valid_session: first call reuses, validate finds login page, triggers clear+recapture."""
    state_file = patch_state_path / "mysite3.json"
    state_file.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    # Patch validate_session_after_reuse to simulate expired session
    with patch.object(sm, "validate_session_after_reuse") as mock_validate:
        mock_validate.return_value = {
            "ok": False,
            "login_required": True,
            "evidence": ["url_contains:login"],
            "session_expired_detected": True,
        }

        capture_calls: list[str] = []

        original_ensure = sm.ensure_session

        def spy_ensure(site_name: str, login_url: str, **kwargs: Any) -> sm.SessionResult:
            capture_calls.append(site_name)
            if len(capture_calls) == 1:
                # First call: return reused (simulate)
                return sm.SessionResult(
                    ok=True, state="reused", site_name=site_name,
                    storage_state_path=state_file,
                    summary="reused",
                )
            # Second call: return captured
            return sm.SessionResult(
                ok=True, state="captured", site_name=site_name,
                storage_state_path=state_file,
                summary="captured",
            )

        # Build a fake headless browser for the validation step
        factory, pw, browser, page = _make_factory(
            url="https://example.com/login",
            content_val='<html><input type="password"></html>',
        )
        page.goto = MagicMock(return_value=None)

        with patch.object(sm, "ensure_session", side_effect=spy_ensure):
            result = sm.ensure_valid_session(
                "mysite3",
                "https://example.com/login",
                "https://example.com/dashboard",
                _browser_factory=factory,
            )

        # The session was expired so ensure_session should be called twice
        assert len(capture_calls) == 2
        assert "session_expired_detected=True" in result.summary


# ---------------------------------------------------------------------------
# 4. test_url_change_alone_not_sufficient_for_completion
# ---------------------------------------------------------------------------

def test_url_change_alone_not_sufficient_for_completion() -> None:
    """Only url_changed in reasons → _has_strong_reason_for_capture returns False."""
    assert sm._has_strong_reason_for_capture(["url_changed"]) is False
    assert sm._has_strong_reason_for_capture([
        "success_url_match:dashboard"
    ]) is False
    # With another signal alongside url_changed → True
    assert sm._has_strong_reason_for_capture([
        "url_changed", "password_input_disappeared"
    ]) is True
    assert sm._has_strong_reason_for_capture([
        "url_changed", "login_required_hint_cleared"
    ]) is True
    # user_confirmed_login alone → True
    assert sm._has_strong_reason_for_capture(["user_confirmed_login"]) is True


# ---------------------------------------------------------------------------
# 5. test_post_login_selector_found_completes_session
# ---------------------------------------------------------------------------

def test_post_login_selector_found_completes_session() -> None:
    """Selector found → returned in found list."""
    fake_element = MagicMock()
    page = _make_fake_page(query_selector_result=fake_element)
    found = sm._check_post_login_selectors(
        page, [".console-app-list", "[data-testid='logout']"]
    )
    assert ".console-app-list" in found


# ---------------------------------------------------------------------------
# 6. test_post_login_selector_missing_records_evidence_only
# ---------------------------------------------------------------------------

def test_post_login_selector_missing_records_evidence_only(
    patch_state_path: Path,
) -> None:
    """Selector not found → warning recorded, not a hard fail."""
    factory, pw, browser, page = _make_factory(
        url="https://example.com/dashboard",
        content_val="<html><body>Welcome</body></html>",
    )
    # query_selector returns None (selector not found)
    page.query_selector.return_value = None

    context = browser.new_context.return_value

    def fake_storage_state(path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    context.storage_state.side_effect = fake_storage_state

    clock = _FakeClock(start=10000.0)

    answers = iter(["", ""])

    result = sm.ensure_session(
        "mysite4",
        "https://example.com/login",
        wait_seconds=10,
        post_login_signals=[".console-app-list"],
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda prompt: next(answers),
    )
    # Should succeed (not hard fail)
    assert result.ok is True
    assert any("POST_LOGIN_SELECTOR_NOT_FOUND" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 7. test_timeout_default_is_300
# ---------------------------------------------------------------------------

def test_timeout_default_is_300() -> None:
    """Default wait_seconds for ensure_session is 300."""
    sig = inspect.signature(sm.ensure_session)
    default_val = sig.parameters["wait_seconds"].default
    assert default_val == 300, f"Expected 300, got {default_val}"


# ---------------------------------------------------------------------------
# 8. test_timeout_warning_at_60s_remaining
# ---------------------------------------------------------------------------

def test_timeout_warning_at_60s_remaining(
    patch_state_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warning '60초 남았습니다' is logged when 60 seconds remain."""
    factory, pw, browser, page = _make_factory(
        url="https://example.com/dashboard",
        content_val="<html><body>Welcome</body></html>",
    )
    context = browser.new_context.return_value

    def fake_storage_state(path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    context.storage_state.side_effect = fake_storage_state

    # Clock that simulates: start at 0, wait_seconds=120, after sleep will be at ~61s
    # So remaining = 120 - 61 = 59 < 60 → warning fires
    tick = [0.0]

    class StepClock:
        def monotonic(self) -> float:
            return tick[0]

        def sleep(self, secs: float) -> None:
            tick[0] += secs + 60  # big jump so 60s warning triggers

    clock = StepClock()

    answers = iter(["", ""])

    import logging
    with caplog.at_level(logging.WARNING, logger="local_agent.session_manager"):
        result = sm.ensure_session(
            "mysite5",
            "https://example.com/login",
            wait_seconds=120,
            poll_interval_seconds=3,
            _browser_factory=factory,
            _clock=clock,
            _input_reader=lambda prompt: next(answers),
        )

    warned = any("60초 남았습니다" in rec.message for rec in caplog.records)
    assert warned, f"Expected 60s warning. Log records: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# 9. test_gitignore_not_covered_warning
# ---------------------------------------------------------------------------

def test_gitignore_not_covered_warning(tmp_path: Path) -> None:
    """.gitignore without secrets/ → GITIGNORE_NOT_COVERED warning."""
    # Create a fake repo structure
    state_dir = tmp_path / "secrets" / "browser_state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "mysite.json"
    state_file.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    # .gitignore without secrets/
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")

    warnings: list[str] = []
    sm._warn_gitignore(state_file, warnings)
    assert any("GITIGNORE_NOT_COVERED" in w for w in warnings)


# ---------------------------------------------------------------------------
# 10. test_git_tracked_file_raises
# ---------------------------------------------------------------------------

def test_git_tracked_file_raises(tmp_path: Path) -> None:
    """If git ls-files returns 0 → RuntimeError raised."""
    state_file = tmp_path / "mysite.json"
    state_file.write_text("{}", encoding="utf-8")

    # Patch subprocess.run to simulate git-tracked file
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("local_agent.session_manager.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="git-tracked"):
            warnings: list[str] = []
            sm._secure_state_file(state_file, warnings)


# ---------------------------------------------------------------------------
# 11. test_no_password_env_vars_used
# ---------------------------------------------------------------------------

def test_no_password_env_vars_used() -> None:
    """ensure_session source does not reference GOOGLE_PASSWORD or GOOGLE_OTP_SECRET."""
    source = inspect.getsource(sm.ensure_session)
    assert "GOOGLE_PASSWORD" not in source
    assert "GOOGLE_OTP_SECRET" not in source

    # Also check _run_capture and _capture_session
    source2 = inspect.getsource(sm._run_capture)
    assert "GOOGLE_PASSWORD" not in source2
    assert "GOOGLE_OTP_SECRET" not in source2


# ---------------------------------------------------------------------------
# 12. test_password_input_value_never_read
# ---------------------------------------------------------------------------

def test_password_input_value_never_read() -> None:
    """is_login_required_page never calls page.input_value or page.evaluate."""
    page = _make_fake_page(
        url="https://example.com/login",
        content_val='<html><input type="password"><button>Login</button></html>',
    )
    # Override _observe to avoid MagicMock calls propagating
    with patch.object(sm, "_observe") as mock_observe:
        mock_observe.return_value = {
            "title": "Login",
            "current_url": "https://example.com/login",
            "login_required_hint": True,
            "login_reason": ["password_input_detected"],
            "page_structure": {},
        }
        login_required, evidence = sm.is_login_required_page(page)

    # Verify neither input_value nor evaluate was called
    page.input_value.assert_not_called()
    page.evaluate.assert_not_called()
    assert login_required is True


# ---------------------------------------------------------------------------
# 13. test_session_raw_content_not_in_result
# ---------------------------------------------------------------------------

def test_session_raw_content_not_in_result(
    patch_state_path: Path,
) -> None:
    """storage_state bytes/content not present in SessionResult fields."""
    state_file = patch_state_path / "mysite6.json"
    state_file.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    result = sm.ensure_session(
        "mysite6",
        "https://example.com/login",
        _input_reader=lambda _: "",
    )
    assert result.ok is True
    assert result.state == "reused"

    # Verify no field contains raw cookie/session data
    raw_session_marker = '"cookies"'
    assert raw_session_marker not in (result.summary or "")
    assert raw_session_marker not in (result.login_hint or "")
    for w in result.warnings:
        assert raw_session_marker not in w
