"""Browser Worker execution policy."""

# Allowed actions in dry_run mode only
ALLOWED_ACTIONS_DRY_RUN = frozenset({
    "browser.inspect",
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
    def validate_actual_execution(action: str) -> tuple[bool, str]:
        """Validate actual execution request.

        Returns:
            (allowed, reason)
        """
        # All browser actions are disabled for actual execution in MVP
        return False, "Actual browser execution disabled in this environment"

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
