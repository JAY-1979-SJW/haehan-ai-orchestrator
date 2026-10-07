from __future__ import annotations

from pathlib import Path

from scripts.google import managed_console
from scripts.google import oauth_console_fill


def test_youtube_oauth_console_plan_forbids_default_browser() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan(google_work_mode="main")

    assert plan["browser_runtime"] == "managed_local_agent_cdp_profile"
    assert plan["default_browser_allowed"] is False
    assert plan["open_method"] == "scripts.browser.cdp.connection.get_page().goto"
    assert plan["state_change"] is False
    assert plan["final_approval_boundary"] == "user_final_approval_only"
    assert plan["secret_action_policy"]["mode"] == "final_approval_only"
    assert plan["google_work_mode_policy"]["status"] == "ok"
    assert plan["google_work_mode"] == "main"
    assert plan["secret_action_policy"]["raw_secret_output_allowed"] is False
    assert "stop before the final Google Console Create/Save button" in plan["agent_allowed_steps"]
    assert "final click on the Google Console Create/Save button" in plan["user_only_steps"]
    assert "Google Console Create/Save for OAuth client" not in plan["user_only_steps"]


def test_youtube_oauth_console_sequence_starts_from_google_home() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan(google_work_mode="main")
    sequence = plan["sequence"]

    assert [item["stage"] for item in sequence] == [
        "google_home",
        "account_state",
        "cloud_credentials",
    ]
    assert sequence[0]["url"] == "https://www.google.com/"
    assert sequence[1]["url"] == "https://myaccount.google.com/"
    assert sequence[2]["url"] == "https://console.cloud.google.com/apis/credentials"


def test_google_login_probe_uses_home_first() -> None:
    from scripts.common.config import LOGIN_PROBE_URLS

    assert LOGIN_PROBE_URLS["google"] == "https://www.google.com/"


def test_managed_console_module_does_not_use_os_browser_openers() -> None:
    src = Path("scripts/google/managed_console.py").read_text(encoding="utf-8")

    forbidden = [
        "webbrowser.open",
        "os.startfile",
        "Start-Process",
        "explorer.exe",
    ]
    for pattern in forbidden:
        assert pattern not in src


def test_dry_run_does_not_open_browser() -> None:
    result = managed_console.open_youtube_oauth_console_managed(dry_run=True, google_work_mode="main")

    assert result["dry_run"] is True
    assert result["opened"] is False
    assert result["default_browser_allowed"] is False


def test_youtube_oauth_console_fill_plan_stops_before_final_button() -> None:
    plan = oauth_console_fill.build_youtube_oauth_console_fill_plan(google_work_mode="main")

    assert plan["status"] == "ready_for_ai_prefill"
    assert plan["browser_runtime"] == "managed_local_agent_cdp_profile"
    assert plan["default_browser_allowed"] is False
    assert plan["state_change_final_button_clicked"] is False
    assert plan["final_button_user_only"] is True
    assert plan["secret_action_policy"]["agent_final_secret_issue_allowed"] is False
    assert plan["google_work_mode"] == "main"
    assert "stop before final Create/Save button" in plan["agent_steps"]
    assert "final click on the visible Google Console Create/Save button" in plan["user_only_steps"]
    assert plan["non_secret_inputs"]["client_name"] == "haehan-youtube-server-captions"
    assert plan["non_secret_inputs"]["authorized_redirect_uri"].startswith("https://haehan-ai.kr/")


def test_youtube_oauth_console_fill_dry_run_does_not_open_browser() -> None:
    result, path = oauth_console_fill.prefill_youtube_oauth_console(dry_run=True, google_work_mode="main")

    assert path is None
    assert result["dry_run"] is True
    assert result["status"] == "dry_run"
    assert result["state_change_final_button_clicked"] is False
    assert result["final_button_user_only"] is True


def test_secret_issue_agent_click_requires_explicit_approval() -> None:
    result, path = oauth_console_fill.prefill_youtube_oauth_console(
        dry_run=True,
        google_work_mode="main",
        secret_action_mode="secret_issue_agent_click",
    )

    assert path is None
    assert result["status"] == "blocked"
    assert result["secret_action_policy"]["blocked_reason"] == "secret_issue_agent_click_requires_explicit_approval"
    assert result["secret_action_policy"]["raw_secret_output_allowed"] is False


def test_secret_issue_agent_click_can_be_approved_for_final_button() -> None:
    plan = oauth_console_fill.build_youtube_oauth_console_fill_plan(
        google_work_mode="main",
        secret_action_mode="secret_issue_agent_click",
        secret_issue_approved=True,
    )

    assert plan["secret_action_policy"]["status"] == "ok"
    assert plan["secret_action_policy"]["agent_final_secret_issue_allowed"] is True
    assert plan["final_button_user_only"] is False
    assert plan["secret_action_policy"]["raw_secret_output_allowed"] is False
