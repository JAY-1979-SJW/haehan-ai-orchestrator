"""Server approval action contract for browser automation.

This module defines the contract between server task/approval system and
local BrowserController execution. It handles:

1. Approval-gated action proposals from server
2. Safe result_data serialization (no secrets, tokens, or raw text)
3. Risk level classification (low/medium/high/critical)
4. Final approval requirement for dangerous actions

Core Flow:
  1. Server creates browser action proposal (pending state)
  2. User/admin approval generates approval_id and approval_token
  3. Local agent receives ServerApprovalAction with tokens
  4. BrowserController validates and executes with approval_token
  5. Safe ExecutionResult returned (no secrets/tokens/raw_text)
  6. Server stores result_data in task record
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Risk level thresholds
_CRITICAL_RISK_KEYWORDS = frozenset(
    {
        "submit",
        "delete",
        "remove",
        "결제",
        "삭제",
        "등록",
        "가입",
        "제출",
        "payment",
        "checkout",
        "댓글",
        "저장",
        "송금",
        "register",
        "comment",
    }
)

_SUPPORTED_ACTIONS = frozenset(
    {
        "browser.execute_click",
        "browser.execute_type",
        "browser.plan_click",
        "browser.plan_type",
        "browser.inspect",
    }
)


@dataclass
class ServerApprovalAction:
    """Server-side approval action request to local agent.

    Attributes:
        task_id: Unique task identifier from server
        action_type: Action type (browser.execute_click, browser.execute_type, etc.)
        selector: CSS selector for the element
        value: Optional value (for type actions)
        approval_id: Server-side approval record ID (None if not approved)
        approval_token: Short-lived approval token (None if not approved)
        final_approval_token: Final approval for critical actions (None if not approved)
    """

    task_id: str
    action_type: str
    selector: str
    value: str | None = None
    approval_id: str | None = None
    approval_token: str | None = None
    final_approval_token: str | None = None

    def validate(self) -> tuple[bool, str | None]:
        """Validate action structure.

        Returns:
            (is_valid, error_message)
        """
        if not self.task_id or not isinstance(self.task_id, str):
            return False, "task_id must be non-empty string"

        if not self.action_type or self.action_type not in _SUPPORTED_ACTIONS:
            return False, f"action_type not supported: {self.action_type}"

        if not self.selector or not isinstance(self.selector, str):
            return False, "selector must be non-empty string"

        # approval_token is required for execution
        if self.action_type.startswith("browser.execute_") and not self.approval_token:
            return False, "approval_token required for execute actions"

        return True, None


@dataclass
class ExecutionResult:
    """Safe result data for server (no secrets, tokens, or raw text).

    Attributes:
        task_id: Reference to server task
        action: Action that was executed
        selector: Element selector
        executed: Whether the action actually executed
        element_found: Whether the element was found in DOM
        risk_level: Risk classification (low/medium/high)
        final_approval_required: Whether this action needs final approval
        result: Execution status (success, element_not_found, approval_denied, risky_element, sensitive_field, error)
        target_url_domain: Domain of the target URL (for audit trail)
        text_length: Length of typed text (if applicable, 0 if not)
        text_preview: Always "[REDACTED]" for safety
        screenshot_taken: Whether screenshot was captured
        screenshot_ref: Reference to screenshot storage (if any)
    """

    task_id: str
    action: str
    selector: str
    executed: bool
    element_found: bool
    risk_level: str
    final_approval_required: bool
    result: str
    target_url_domain: str = ""
    text_length: int = 0
    text_preview: str = "[REDACTED]"
    screenshot_taken: bool = False
    screenshot_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to safe dict for JSON serialization."""
        data = asdict(self)
        # Ensure no secrets leak
        data["text_preview"] = "[REDACTED]"
        return data

    def __str__(self) -> str:
        """String representation with secret redaction."""
        d = self.to_dict()
        return f"ExecutionResult({', '.join(f'{k}={v}' for k, v in d.items())})"


def assess_action_risk(action_type: str, selector: str, value: str | None = None) -> tuple[str, bool]:
    """Assess risk level of an action.

    Returns:
        (risk_level, final_approval_required)
        - risk_level: one of [low, medium, high, critical]
        - final_approval_required: True if final_approval_token needed
    """
    combined = f"{selector} {value or ''}".lower()

    # Check for critical keywords
    for keyword in _CRITICAL_RISK_KEYWORDS:
        if keyword in combined:
            return "critical", True

    # All execute actions require at least approval_token
    if action_type == "browser.execute_click":
        return "low", False
    elif action_type == "browser.execute_type":
        return "low", False
    else:
        return "low", False


def validate_execution_result(result: ExecutionResult) -> tuple[bool, str | None]:
    """Validate that result_data contains no secrets.

    Returns:
        (is_safe, error_message)
    """
    result_str = str(result)

    forbidden_keywords = [
        "password",
        "token",
        "approval_token",
        "final_approval_token",
        "cookie",
        "session",
        "localStorage",
        "sessionStorage",
        "base64",
        "Authorization",
        "Bearer",
        "secret",
    ]

    for keyword in forbidden_keywords:
        if keyword.lower() in result_str.lower():
            return False, f"Forbidden keyword found in result: {keyword}"

    if result.text_preview != "[REDACTED]":
        return False, "text_preview must be '[REDACTED]', found actual text"

    return True, None
