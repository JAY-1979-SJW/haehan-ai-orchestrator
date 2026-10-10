"""Google secret issuance approval policy.

The gate decides who may perform the final secret-generating click. It never
allows raw secret output.
"""

from __future__ import annotations

from typing import Any

FINAL_APPROVAL_ONLY = "final_approval_only"
SECRET_ISSUE_USER_CLICK = "secret_issue_user_click"
SECRET_ISSUE_AGENT_CLICK = "secret_issue_agent_click"
SECRET_ACTION_MODES = (FINAL_APPROVAL_ONLY, SECRET_ISSUE_USER_CLICK, SECRET_ISSUE_AGENT_CLICK)


def normalize_secret_action_mode(value: str | None) -> str:
    mode = (value or FINAL_APPROVAL_ONLY).strip().lower().replace("-", "_")
    if mode not in SECRET_ACTION_MODES:
        return FINAL_APPROVAL_ONLY
    return mode


def build_secret_action_policy(
    mode: str | None = None,
    *,
    secret_issue_approved: bool = False,
) -> dict[str, Any]:
    normalized = normalize_secret_action_mode(mode)
    agent_click_allowed = normalized == SECRET_ISSUE_AGENT_CLICK and secret_issue_approved
    blocked_reason = ""
    if normalized == SECRET_ISSUE_AGENT_CLICK and not secret_issue_approved:
        blocked_reason = "secret_issue_agent_click_requires_explicit_approval"
    return {
        "schema_version": 1,
        "mode": normalized,
        "status": "ok" if not blocked_reason else "blocked",
        "blocked_reason": blocked_reason,
        "secret_issue_approved": bool(secret_issue_approved),
        "final_button_user_only": normalized in {FINAL_APPROVAL_ONLY, SECRET_ISSUE_USER_CLICK},
        "agent_final_secret_issue_allowed": agent_click_allowed,
        "user_final_secret_issue_allowed": normalized in {FINAL_APPROVAL_ONLY, SECRET_ISSUE_USER_CLICK},
        "raw_secret_output_allowed": False,
        "credential_replay_allowed": False,
        "secret_storage_reference_only": True,
        "allowed_secret_reference_format": "local-secret://<kind>/<name>",
        "reporting": "result status and secret reference only; raw key/client secret/token values forbidden",
        "next_step": (
            "Ask the user to approve secret_issue_agent_click for this exact task."
            if blocked_reason
            else "Proceed inside this mode without raw secret output."
        ),
    }


__all__ = [
    "FINAL_APPROVAL_ONLY",
    "SECRET_ACTION_MODES",
    "SECRET_ISSUE_AGENT_CLICK",
    "SECRET_ISSUE_USER_CLICK",
    "build_secret_action_policy",
    "normalize_secret_action_mode",
]
