"""Local browser task handler for WebSocket/local task integration.

This module bridges WebSocket task payloads to browser automation.
Handles approval verification, action dispatch, and safe result serialization.

Flow:
  WebSocket task payload
  → BrowserTaskHandler.handle_task()
  → ServerApprovalAction conversion
  → BrowserApprovalVerifier validation
  → ServerActionAdapter execution
  → BrowserTaskResult with safe data
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from core.agent_runtime.browser.approval.browser_approval_verifier import BrowserApprovalVerifier
from core.agent_runtime.browser.browser_action_contract import ServerApprovalAction
from core.agent_runtime.browser.server_action_adapter import ServerActionAdapter

logger = logging.getLogger(__name__)


@dataclass
class BrowserTaskPayload:
    """WebSocket/local task payload for browser actions.

    Attributes:
        task_id: Unique task identifier
        task_type: Always "browser_action"
        action_type: browser.execute_click, browser.execute_type, etc.
        selector: CSS selector for the target element
        value: Optional value (for type actions)
        approval_id: Server-side approval record ID
        approval_token: Approval token
        final_approval_token: Final approval for critical actions
    """

    task_id: str
    task_type: str = "browser_action"
    action_type: str = ""
    selector: str = ""
    value: str | None = None
    approval_id: str | None = None
    approval_token: str | None = None
    final_approval_token: str | None = None

    def to_server_action(self) -> ServerApprovalAction:
        """Convert task payload to ServerApprovalAction.

        Returns:
            ServerApprovalAction instance
        """
        return ServerApprovalAction(
            task_id=self.task_id,
            action_type=self.action_type,
            selector=self.selector,
            value=self.value,
            approval_id=self.approval_id,
            approval_token=self.approval_token,
            final_approval_token=self.final_approval_token,
        )


@dataclass
class BrowserTaskResult:
    """Result of browser task execution.

    Attributes:
        task_id: Reference to original task
        status: received / blocked / executed / failed
        action: Action that was attempted
        selector: Element selector
        executed: Whether the action executed
        element_found: Whether element found in DOM
        risk_level: Risk classification
        final_approval_required: Whether final approval needed
        result: Execution status code
        target_url_domain: Domain of target URL
        text_length: Length of typed text (if applicable)
        text_preview: Always "[REDACTED]"
        error_code: Error code if failed
        error_message: Human-readable error message
    """

    task_id: str
    status: str = "received"  # received, blocked, executed, failed
    action: str = ""
    selector: str = ""
    executed: bool = False
    element_found: bool = False
    risk_level: str = "low"
    final_approval_required: bool = False
    result: str = "success"
    target_url_domain: str = ""
    text_length: int = 0
    text_preview: str = "[REDACTED]"
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to safe dict for JSON serialization."""
        data = asdict(self)
        # Ensure no secrets leak
        data["text_preview"] = "[REDACTED]"
        return data

    def __str__(self) -> str:
        """String representation with secret redaction."""
        d = self.to_dict()
        return f"BrowserTaskResult({', '.join(f'{k}={v}' for k, v in d.items())})"


class BrowserTaskHandler:
    """Handles browser automation tasks with approval verification."""

    def __init__(
        self,
        server_action_adapter: ServerActionAdapter,
        approval_verifier: BrowserApprovalVerifier | None = None,
    ):
        """Initialize task handler.

        Args:
            server_action_adapter: ServerActionAdapter instance (must have page loaded)
            approval_verifier: Optional BrowserApprovalVerifier for token validation
        """
        self.adapter = server_action_adapter
        self.verifier = approval_verifier

    async def handle_task(self, payload: BrowserTaskPayload) -> BrowserTaskResult:
        """Handle a browser automation task.

        Args:
            payload: BrowserTaskPayload with action and approval info

        Returns:
            BrowserTaskResult with safe data (no secrets/tokens/raw_text)
        """
        # Validate payload
        if not payload.task_id:
            return BrowserTaskResult(
                task_id=payload.task_id or "unknown",
                status="blocked",
                error_code="invalid_payload",
                error_message="task_id is required",
            )

        if not payload.action_type:
            return BrowserTaskResult(
                task_id=payload.task_id,
                status="blocked",
                error_code="invalid_payload",
                error_message="action_type is required",
            )

        if not payload.selector:
            return BrowserTaskResult(
                task_id=payload.task_id,
                status="blocked",
                error_code="invalid_payload",
                error_message="selector is required",
            )

        if payload.action_type == "browser.execute_type" and not payload.value:
            return BrowserTaskResult(
                task_id=payload.task_id,
                status="blocked",
                action=payload.action_type,
                selector=payload.selector,
                error_code="invalid_payload",
                error_message="value is required for type actions",
            )

        # Convert to ServerApprovalAction
        server_action = payload.to_server_action()

        # Verify approval if verifier configured
        if self.verifier:
            verification = self.verifier.verify(
                approval_id=server_action.approval_id,
                approval_token=server_action.approval_token,
                action_type=server_action.action_type,
                selector=server_action.selector,
            )
            if not verification.valid:
                return BrowserTaskResult(
                    task_id=payload.task_id,
                    status="blocked",
                    action=payload.action_type,
                    selector=payload.selector,
                    executed=False,
                    element_found=False,
                    result=verification.error_code or "approval_invalid",
                    error_code=verification.error_code,
                    error_message=verification.error_message,
                )

        # Execute action via adapter
        try:
            execution_result = await self.adapter.execute_action(server_action)
        except Exception as e:  # noqa: BLE001 - 브라우저 액션 실행(execute_action) 실패를 캡처해 BrowserTaskResult status=failed로 반환 - 실패를 성공으로 위장하지 않음, read-only 핸드셰이크 경로
            logger.error(f"Action execution failed: {e}")
            return BrowserTaskResult(
                task_id=payload.task_id,
                status="failed",
                action=payload.action_type,
                selector=payload.selector,
                executed=False,
                error_code="execution_error",
                error_message=str(e),
            )

        # Mark approval as used if verification succeeded and execution was successful
        if self.verifier and execution_result.executed and server_action.approval_id:
            self.verifier.store.mark_used(server_action.approval_id)

        # Convert ExecutionResult to BrowserTaskResult
        result = BrowserTaskResult(
            task_id=payload.task_id,
            status="executed" if execution_result.executed else "blocked",
            action=execution_result.action,
            selector=execution_result.selector,
            executed=execution_result.executed,
            element_found=execution_result.element_found,
            risk_level=execution_result.risk_level,
            final_approval_required=execution_result.final_approval_required,
            result=execution_result.result,
            target_url_domain=execution_result.target_url_domain,
            text_length=execution_result.text_length,
            text_preview="[REDACTED]",
        )

        return result
