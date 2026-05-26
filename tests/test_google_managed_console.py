from __future__ import annotations

from pathlib import Path

from scripts.google import managed_console


def test_youtube_oauth_console_plan_forbids_default_browser() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan()

    assert plan["browser_runtime"] == "managed_local_agent_cdp_profile"
    assert plan["default_browser_allowed"] is False
    assert plan["open_method"] == "scripts.web_connector.get_page().goto"
    assert plan["state_change"] is False
    assert plan["final_approval_boundary"] == "user_final_approval_only"
    assert "Google Console Create/Save for OAuth client" in plan["user_only_steps"]


def test_youtube_oauth_console_sequence_starts_from_google_home() -> None:
    plan = managed_console.build_youtube_oauth_console_open_plan()
    sequence = plan["sequence"]

    assert [item["stage"] for item in sequence] == [
        "google_home",
        "account_state",
        "cloud_credentials",
    ]
    assert sequence[0]["url"] == "https://www.google.com/"
    assert sequence[1]["url"] == "https://myaccount.google.com/"
    assert sequence[2]["url"] == "https://console.cloud.google.com/apis/credentials"


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
    result = managed_console.open_youtube_oauth_console_managed(dry_run=True)

    assert result["dry_run"] is True
    assert result["opened"] is False
    assert result["default_browser_allowed"] is False
