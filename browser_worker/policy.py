"""Browser Worker execution policy."""
import os

# Allowed actions in dry_run mode only
ALLOWED_ACTIONS_DRY_RUN = frozenset({
    "browser.inspect",
})

# Allowed actions in actual execution mode (gated by BROWSER_EXECUTION_ENABLED)
ALLOWED_ACTIONS_ACTUAL_EXECUTION = frozenset({
    "browser.inspect",
})

# Allowed URLs in actual execution mode
ALLOWED_URLS_ACTUAL_EXECUTION = frozenset({
    "about:blank",
})

# Actions disabled in actual execution mode
DISABLED_ACTIONS_ACTUAL = frozenset({
    "browser.inspect",
    "browser.plan_click",
    "browser.plan_type",
    "browser.plan_submit",
    "browser.execute_click",
    "browser.execute_type",
})


def is_action_allowed_dry_run(action: str) -> bool:
    """Check if action is allowed in dry_run mode."""
    return action in ALLOWED_ACTIONS_DRY_RUN


def is_action_known(action: str) -> bool:
    """Check if action is known (defined)."""
    return action in DISABLED_ACTIONS_ACTUAL or action in ALLOWED_ACTIONS_DRY_RUN


# Security policies
class WorkerSecurityPolicy:
    """Browser Worker security and operational policies."""

    @staticmethod
    def validate_dry_run(action: str) -> tuple[bool, str]:
        """Validate dry_run request.

        Returns:
            (allowed, reason)
        """
        if not is_action_allowed_dry_run(action):
            return False, f"Action '{action}' not allowed in dry_run mode"
        return True, "ok"

    @staticmethod
    def validate_actual_execution(action: str, url: str = "") -> tuple[bool, str]:
        """Validate actual execution request.

        Returns:
            (allowed, reason)
        """
        # Check if execution is enabled via environment variable
        if os.environ.get("BROWSER_EXECUTION_ENABLED", "").lower() != "true":
            return False, "BROWSER_EXECUTION_ENABLED not set"

        # Check if action is allowed
        if action not in ALLOWED_ACTIONS_ACTUAL_EXECUTION:
            return False, f"Action '{action}' not allowed in actual execution"

        # Check if URL is allowed (if provided)
        if url and url not in ALLOWED_URLS_ACTUAL_EXECUTION:
            return False, f"URL '{url}' not allowed in actual execution"

        return True, "ok"

    @staticmethod
    def get_security_notes() -> list[str]:
        """Get security and operational notes."""
        return [
            "Task-specific browser context (no context sharing)",
            "Cookies/sessions stored in memory only (no persistence)",
            "Screenshots and temp files deleted after task completion",
            "Login/authentication tasks routed to local_agent_backend",
            "Chromium browser only (Firefox/WebKit not supported)",
        ]
