"""Managed Google Console browser entrypoints.

Google Console and OAuth approval preparation must use the managed CDP browser
profile. This module intentionally does not call OS/default browser openers.
"""

from __future__ import annotations

import contextlib
from typing import Any

from scripts.common.gates.secret_action_gate import build_secret_action_policy
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy

GOOGLE_HOME_URL = "https://www.google.com/"
GOOGLE_ACCOUNT_URL = "https://myaccount.google.com/"
GOOGLE_CLOUD_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"

YOUTUBE_SERVER_OAUTH_INPUTS = {
    "project": "haehan-ai",
    "api": "YouTube Data API v3",
    "credential_type": "OAuth client ID",
    "application_type": "Web application",
    "client_name": "haehan-youtube-server-captions",
    "authorized_redirect_uri": "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback",
    "scope": "https://www.googleapis.com/auth/youtube.force-ssl",
}


def build_youtube_oauth_console_open_plan(
    *,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    secret_action_mode: str = "final_approval_only",
    secret_issue_approved: bool = False,
) -> dict[str, Any]:
    """Return the locked, non-secret Google Console open plan."""
    work_mode_policy = build_google_work_mode_policy(
        google_work_mode,
        background_approved=background_approved,
    )
    secret_policy = build_secret_action_policy(
        secret_action_mode,
        secret_issue_approved=secret_issue_approved,
    )
    status = "ready_for_managed_console_open"
    if work_mode_policy["status"] == "blocked" or secret_policy["status"] == "blocked":
        status = "blocked"
    return {
        "status": status,
        "browser_runtime": "managed_local_agent_cdp_profile",
        "google_work_mode_policy": work_mode_policy,
        "google_work_mode": work_mode_policy["mode"],
        "background_approved": bool(background_approved),
        "default_browser_allowed": False,
        "os_browser_openers_forbidden": [
            "PowerShell URL opener",
            "Python default browser opener",
            "OS file/URL opener",
            "shell URL open",
        ],
        "open_method": "scripts.browser.cdp.connection.get_page().goto",
        "sequence": [
            {
                "step": 1,
                "stage": "google_home",
                "url": GOOGLE_HOME_URL,
                "verification": "reachable_in_managed_cdp_profile",
            },
            {
                "step": 2,
                "stage": "account_state",
                "url": GOOGLE_ACCOUNT_URL,
                "verification": "user_present_account_state_only_no_secret_export",
            },
            {
                "step": 3,
                "stage": "cloud_credentials",
                "url": GOOGLE_CLOUD_CREDENTIALS_URL,
                "verification": "console_credentials_page_reachable_in_same_profile",
            },
        ],
        "non_secret_inputs": dict(YOUTUBE_SERVER_OAUTH_INPUTS),
        "secret_action_policy": secret_policy,
        "agent_allowed_steps": [
            "open managed CDP browser tab",
            "navigate through the locked Google connection sequence",
            "prepare the required Google API enablement screen",
            "enter non-secret setup values when the page is inspectable",
            "stop before the final Google Console Create/Save button",
            "after the user clicks the final button, capture the client JSON into approved secret storage without printing it",
            "save redacted evidence and reports",
        ],
        "user_only_steps": [
            "Google account login and MFA/2FA when required",
            "final click on the Google Console Create/Save button",
            "Google OAuth consent approval",
            "final approval for storing the downloaded client JSON or generated token",
        ],
        "final_approval_boundary": "user_final_approval_only",
        "user_approval_mode": secret_policy["mode"],
        "state_change": False,
    }


def open_youtube_oauth_console_managed(
    *,
    dry_run: bool = False,
    timeout_ms: int = 60000,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    secret_action_mode: str = "final_approval_only",
    secret_issue_approved: bool = False,
) -> dict[str, Any]:
    """Open Google Console credentials through the managed CDP browser only."""
    plan = build_youtube_oauth_console_open_plan(
        google_work_mode=google_work_mode,
        background_approved=background_approved,
        secret_action_mode=secret_action_mode,
        secret_issue_approved=secret_issue_approved,
    )
    if plan["status"] == "blocked":
        return {**plan, "dry_run": dry_run, "opened": False, "status": "blocked"}
    if dry_run:
        return {**plan, "dry_run": True, "opened": False}

    from scripts.browser.cdp.connection import get_page

    page = get_page()
    visited: list[dict[str, Any]] = []
    for item in plan["sequence"]:
        page.goto(item["url"], timeout=timeout_ms)
        # 구글 관리 콘솔 탐색(읽기 전용) -- 페이지 로드 대기 best-effort 실패는 무시
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        # 구글 관리 콘솔 탐색(읽기 전용) -- 전면화 best-effort 실패는 무시
        with contextlib.suppress(Exception):
            page.bring_to_front()
        visited.append(
            {
                "stage": item["stage"],
                "target_url": item["url"],
                "current_url": page.url,
                "title": page.title(),
            }
        )

    return {
        **plan,
        "dry_run": False,
        "opened": True,
        "visited": visited,
        "current_url": page.url,
        "current_title": page.title(),
    }
