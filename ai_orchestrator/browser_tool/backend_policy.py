"""Browser Tool Policy.

Defines risk classification, approval requirements, and execution policies
for browser actions.
"""
from __future__ import annotations

from .schemas import BrowserActionName, BrowserTaskPolicy

# Browser action risk and approval policies
_ACTION_POLICIES: dict[BrowserActionName, BrowserTaskPolicy] = {
    "inspect": BrowserTaskPolicy(
        action="inspect",
        risk_level="low",
        requires_approval=False,
        requires_dry_run=True,  # Only dry_run mode allowed in current stage
        blocked=False,
    ),
    "plan_click": BrowserTaskPolicy(
        action="plan_click",
        risk_level="low",
        requires_approval=False,
        requires_dry_run=False,
        blocked=True,
        blocked_reason="not_implemented",
    ),
    "plan_type": BrowserTaskPolicy(
        action="plan_type",
        risk_level="low",
        requires_approval=False,
        requires_dry_run=False,
        blocked=False,
    ),
    "plan_submit": BrowserTaskPolicy(
        action="plan_submit",
        risk_level="low",
        requires_approval=False,
        requires_dry_run=False,
        blocked=True,
        blocked_reason="not_implemented",
    ),
    "execute_click": BrowserTaskPolicy(
        action="execute_click",
        risk_level="medium",
        requires_approval=True,
        requires_dry_run=False,
        blocked=True,
        blocked_reason="actual_browser_execution_not_enabled",
    ),
    "execute_type": BrowserTaskPolicy(
        action="execute_type",
        risk_level="medium",
        requires_approval=True,
        requires_dry_run=False,
        blocked=True,
        blocked_reason="actual_browser_execution_not_enabled",
    ),
    "open_type_close_controlled": BrowserTaskPolicy(
        action="open_type_close_controlled",
        risk_level="medium",
        requires_approval=True,
        requires_dry_run=False,
        blocked=False,
    ),
}


def get_action_policy(action: BrowserActionName) -> BrowserTaskPolicy | None:
    """Get policy for a browser action."""
    return _ACTION_POLICIES.get(action)


def is_action_blocked(action: BrowserActionName) -> bool:
    """Check if action is blocked."""
    policy = get_action_policy(action)
    return policy is not None and policy.blocked


def get_block_reason(action: BrowserActionName) -> str:
    """Get block reason for action."""
    policy = get_action_policy(action)
    if policy and policy.blocked:
        return policy.blocked_reason
    return ""


def requires_dry_run_only(action: BrowserActionName) -> bool:
    """Check if action requires dry_run=True mode only."""
    policy = get_action_policy(action)
    return policy is not None and policy.requires_dry_run
