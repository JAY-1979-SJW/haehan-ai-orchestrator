from __future__ import annotations

from scripts.google import managed_console
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy, normalize_google_work_mode
from scripts.youtube import oauth


def test_google_work_mode_is_required() -> None:
    policy = build_google_work_mode_policy(None)

    assert policy["status"] == "blocked"
    assert policy["blocked_reason"] == "google_work_mode_required"
    assert policy["allowed_modes"] == ["main", "background"]


def test_main_mode_requires_visible_browser() -> None:
    policy = build_google_work_mode_policy("main")

    assert policy["status"] == "ok"
    assert policy["mode"] == "main"
    assert policy["visible_browser_required"] is True
    assert policy["headless_or_background_allowed"] is False
    assert policy["google_home_required"] is True
    assert policy["direct_accounts_login_allowed"] is False


def test_background_mode_requires_explicit_approval() -> None:
    policy = build_google_work_mode_policy("background")

    assert policy["status"] == "blocked"
    assert policy["blocked_reason"] == "background_mode_requires_explicit_user_approval"
    assert policy["login_or_mfa_allowed_in_background"] is False


def test_background_mode_allows_approved_existing_session_only() -> None:
    policy = build_google_work_mode_policy("background", background_approved=True)

    assert policy["status"] == "ok"
    assert policy["mode"] == "background"
    assert policy["background_approved"] is True
    assert policy["headless_or_background_allowed"] is True
    assert policy["visible_browser_required"] is False
    assert policy["login_or_mfa_allowed_in_background"] is False


def test_mode_aliases_are_normalized() -> None:
    assert normalize_google_work_mode("foreground") == "main"
    assert normalize_google_work_mode("bg") == "background"
    assert normalize_google_work_mode("invalid") == ""


def test_console_plan_blocks_without_work_mode() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan()

    assert plan["status"] == "blocked"
    assert plan["google_work_mode_policy"]["blocked_reason"] == "google_work_mode_required"


def test_console_prefill_blocks_without_work_mode() -> None:
    from scripts.google import oauth_console_fill

    plan = oauth_console_fill.build_youtube_oauth_console_fill_plan()

    assert plan["status"] == "blocked"
    assert plan["google_work_mode_policy"]["blocked_reason"] == "google_work_mode_required"


def test_console_plan_accepts_selected_main_mode() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan(google_work_mode="main")

    assert plan["status"] == "ready_for_managed_console_open"
    assert plan["google_work_mode"] == "main"
    assert plan["sequence"][0]["url"] == "https://www.google.com/"


def test_console_plan_blocks_unapproved_background_mode() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan(google_work_mode="background")

    assert plan["status"] == "blocked"
    assert plan["google_work_mode_policy"]["blocked_reason"] == "background_mode_requires_explicit_user_approval"


def test_console_plan_accepts_approved_background_mode() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan(
        google_work_mode="background",
        background_approved=True,
    )

    assert plan["status"] == "ready_for_managed_console_open"
    assert plan["google_work_mode"] == "background"
    assert plan["background_approved"] is True


def test_youtube_server_preapproval_requires_work_mode() -> None:
    result, _path = oauth.build_server_preapproval({})

    assert result["status"] == "blocked"
    assert result["google_work_mode_policy"]["blocked_reason"] == "google_work_mode_required"


def test_youtube_server_preapproval_accepts_main_mode() -> None:
    result, _path = oauth.build_server_preapproval({"google_work_mode": "main"})

    assert result["status"] == "ready_for_user_console_approval"
    assert result["google_work_mode"] == "main"
