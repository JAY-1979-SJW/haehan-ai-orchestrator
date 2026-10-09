"""Adapter between server approval actions and local BrowserController.

This module translates ServerApprovalAction requests into BrowserController
calls, ensuring approval tokens are properly validated and result_data
is safely serialized.
"""

from __future__ import annotations

import logging

from core.agent_runtime.browser.approval.browser_approval_verifier import BrowserApprovalVerifier
from core.agent_runtime.browser.browser_action_contract import (
    ExecutionResult,
    ServerApprovalAction,
    assess_action_risk,
    validate_execution_result,
)
from core.agent_runtime.browser.browser_controller import BrowserController

logger = logging.getLogger(__name__)


class ServerActionAdapterError(Exception):
    """Server action adapter error."""

    pass


class ServerActionAdapter:
    """Adapter for server approval actions → BrowserController execution."""

    def __init__(
        self,
        browser_controller: BrowserController,
        approval_verifier: BrowserApprovalVerifier | None = None,
    ):
        """Initialize adapter with a BrowserController instance.

        Args:
            browser_controller: Initialized BrowserController with page loaded
            approval_verifier: BrowserApprovalVerifier for token validation
        """
        self.controller = browser_controller
        self.verifier = approval_verifier

    async def execute_action(
        self,
        action: ServerApprovalAction,
    ) -> ExecutionResult:
        """Execute a server approval action using BrowserController.

        Args:
            action: ServerApprovalAction from server

        Returns:
            ExecutionResult with safe data (no secrets/tokens/raw_text)

        Raises:
            ServerActionAdapterError: If action is invalid or execution fails
        """
        # Validate action
        is_valid, error_msg = action.validate()
        if not is_valid:
            raise ServerActionAdapterError(f"Invalid action: {error_msg}")

        # Verify approval token if verifier is configured
        if self.verifier:
            verification = self.verifier.verify(
                approval_id=action.approval_id,
                approval_token=action.approval_token,
                action_type=action.action_type,
                selector=action.selector,
            )
            if not verification.valid:
                # Return blocked result without executing
                return ExecutionResult(
                    task_id=action.task_id,
                    action=action.action_type,
                    selector=action.selector,
                    executed=False,
                    element_found=False,
                    risk_level="high",
                    final_approval_required=False,
                    result=verification.error_code or "approval_invalid",
                    target_url_domain=self.controller._extract_domain(self.controller.page.url)
                    if self.controller.page
                    else "",
                )

        # Route to appropriate handler
        if action.action_type == "browser.execute_click":
            result = await self._execute_click(action)
        elif action.action_type == "browser.execute_type":
            result = await self._execute_type(action)
        else:
            raise ServerActionAdapterError(f"Unsupported action type: {action.action_type}")

        # Mark approval as used if verification succeeded and execution was successful
        if self.verifier and result.executed and action.approval_id:
            self.verifier.store.mark_used(action.approval_id)

        return result

    async def _execute_click(self, action: ServerApprovalAction) -> ExecutionResult:
        """Execute a click action.

        Args:
            action: ServerApprovalAction with action_type='browser.execute_click'

        Returns:
            ExecutionResult
        """
        # Assess risk
        risk_level, final_approval_required = assess_action_risk(
            action.action_type,
            action.selector,
        )

        # Call BrowserController with tokens
        bc_result = await self.controller.execute_click(
            action.selector,
            approval_token=action.approval_token,
            final_approval_token=action.final_approval_token,
        )

        # Convert BrowserController result to ExecutionResult
        result = ExecutionResult(
            task_id=action.task_id,
            action="browser_execute_click",
            selector=action.selector,
            executed=bc_result.executed,
            element_found=bc_result.element_found,
            risk_level=risk_level,
            final_approval_required=final_approval_required,
            result=bc_result.result,
            target_url_domain=bc_result.target_url_domain,
            screenshot_taken=bc_result.screenshot_taken,
            screenshot_ref=bc_result.screenshot_ref,
        )

        # Validate result contains no secrets
        is_safe, error_msg = validate_execution_result(result)
        if not is_safe:
            logger.error(f"Result validation failed: {error_msg}")
            raise ServerActionAdapterError(f"Unsafe result: {error_msg}")

        return result

    async def _execute_type(self, action: ServerApprovalAction) -> ExecutionResult:
        """Execute a type action.

        Args:
            action: ServerApprovalAction with action_type='browser.execute_type'

        Returns:
            ExecutionResult
        """
        if not action.value:
            raise ServerActionAdapterError("Type action requires value")

        # Assess risk
        risk_level, final_approval_required = assess_action_risk(
            action.action_type,
            action.selector,
            action.value,
        )

        # Call BrowserController with token
        bc_result = await self.controller.execute_type(
            action.selector,
            action.value,
            approval_token=action.approval_token,
        )

        # Convert BrowserController result to ExecutionResult
        result = ExecutionResult(
            task_id=action.task_id,
            action="browser_execute_type",
            selector=action.selector,
            executed=bc_result.executed,
            element_found=bc_result.element_found,
            risk_level=risk_level,
            final_approval_required=final_approval_required,
            result=bc_result.result,
            target_url_domain=bc_result.target_url_domain,
            text_length=bc_result.text_length,
            text_preview="[REDACTED]",
            screenshot_taken=bc_result.screenshot_taken,
            screenshot_ref=bc_result.screenshot_ref,
        )

        # Validate result contains no secrets
        is_safe, error_msg = validate_execution_result(result)
        if not is_safe:
            logger.error(f"Result validation failed: {error_msg}")
            raise ServerActionAdapterError(f"Unsafe result: {error_msg}")

        return result
