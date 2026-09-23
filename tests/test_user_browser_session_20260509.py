"""user_browser_session 단위 테스트.

실제 브라우저 launch 없이 경로/검증 로직만 확인.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.local_agent.browser.browser_session import (
    _DEFAULT_SESSION_ROOT,
    get_session_dir,
    list_profiles,
)


def test_session_dir_created(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ai_orchestrator.local_agent.browser.browser_session._DEFAULT_SESSION_ROOT",
        tmp_path / "browser_sessions",
    )
    d = get_session_dir("test_profile")
    assert d.exists()
    assert d.name == "test_profile"
    assert d.is_dir()


def test_session_dir_default_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ai_orchestrator.local_agent.browser.browser_session._DEFAULT_SESSION_ROOT",
        tmp_path / "browser_sessions",
    )
    d = get_session_dir()  # default
    assert d.name == "default"


def test_invalid_profile_name_path_traversal_blocked():
    with pytest.raises(ValueError):
        get_session_dir("../etc/passwd")


def test_invalid_profile_name_slash_blocked():
    with pytest.raises(ValueError):
        get_session_dir("a/b")


def test_invalid_profile_name_backslash_blocked():
    with pytest.raises(ValueError):
        get_session_dir("a\\b")


def test_empty_profile_name_blocked():
    with pytest.raises(ValueError):
        get_session_dir("")


def test_list_profiles_returns_list(tmp_path, monkeypatch):
    root = tmp_path / "browser_sessions"
    monkeypatch.setattr(
        "ai_orchestrator.local_agent.browser.browser_session._DEFAULT_SESSION_ROOT",
        root,
    )
    assert list_profiles() == []
    get_session_dir("alpha")
    get_session_dir("beta")
    profiles = list_profiles()
    assert "alpha" in profiles
    assert "beta" in profiles


def test_default_session_root_under_data():
    # 프로젝트 루트 기준 data/browser_sessions 인지 검증
    assert _DEFAULT_SESSION_ROOT.name == "browser_sessions"
    assert _DEFAULT_SESSION_ROOT.parent.name == "data"
