"""Google browser work mode gate.

Google automation must choose one of two execution modes before opening a
browser task:

* main: visible, user-present browser work.
* background: already-authenticated background work, allowed only after explicit
  user approval for that exact task.
"""

from __future__ import annotations

from typing import Any

MAIN_WORK_MODE = "main"
BACKGROUND_WORK_MODE = "background"
GOOGLE_WORK_MODES = (MAIN_WORK_MODE, BACKGROUND_WORK_MODE)


def normalize_google_work_mode(value: str | None) -> str:
    mode = (value or "").strip().lower().replace("-", "_")
    if mode == "foreground":
        mode = MAIN_WORK_MODE
    if mode in {"bg", "back"}:
        mode = BACKGROUND_WORK_MODE
    return mode if mode in GOOGLE_WORK_MODES else ""


def build_google_work_mode_policy(
    mode: str | None,
    *,
    background_approved: bool = False,
) -> dict[str, Any]:
    normalized = normalize_google_work_mode(mode)
    if not normalized:
        return {
            "schema_version": 1,
            "status": "blocked",
            "mode": "",
            "blocked_reason": "google_work_mode_required",
            "allowed_modes": list(GOOGLE_WORK_MODES),
            "background_approved": bool(background_approved),
            "google_home_required": True,
            "direct_accounts_login_allowed": False,
            "next_step": "Select google_work_mode=main or google_work_mode=background before starting.",
        }

    if normalized == BACKGROUND_WORK_MODE and not background_approved:
        return {
            "schema_version": 1,
            "status": "blocked",
            "mode": BACKGROUND_WORK_MODE,
            "blocked_reason": "background_mode_requires_explicit_user_approval",
            "allowed_modes": list(GOOGLE_WORK_MODES),
            "background_approved": False,
            "google_home_required": True,
            "direct_accounts_login_allowed": False,
            "login_or_mfa_allowed_in_background": False,
            "next_step": "Ask the user to approve background_approved=True for this exact Google task.",
        }

    return {
        "schema_version": 1,
        "status": "ok",
        "mode": normalized,
        "blocked_reason": "",
        "allowed_modes": list(GOOGLE_WORK_MODES),
        "background_approved": bool(background_approved),
        "google_home_required": True,
        "direct_accounts_login_allowed": False,
        "login_or_mfa_allowed_in_background": False,
        "visible_browser_required": normalized == MAIN_WORK_MODE,
        "headless_or_background_allowed": normalized == BACKGROUND_WORK_MODE,
        "final_approval_user_only": True,
        "next_step": "Proceed through Google Home and preserve the final user approval boundary.",
    }


__all__ = [
    "BACKGROUND_WORK_MODE",
    "GOOGLE_WORK_MODES",
    "MAIN_WORK_MODE",
    "build_google_work_mode_policy",
    "normalize_google_work_mode",
]
