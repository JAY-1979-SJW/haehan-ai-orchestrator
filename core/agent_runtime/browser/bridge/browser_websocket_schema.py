"""WebSocket payload schema formalization for browser task contract (BROWSER-4G).

This module defines the formal schema for:
1. BrowserWebSocketTaskPayload - Input payload from WebSocket/server
2. BrowserWebSocketTaskResult - Output result for storage/return

Design principles:
1. Explicit whitelist (allowed fields only)
2. Token transmission rules (approval_token allowed in input, forbidden in result)
3. Result data safety (no secrets, no raw tokens, no typed text)
4. Metadata constraints (no cookies, sessions, headers, storage)
5. Status vocabulary standardization
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


# Allowed action types (others blocked)
ALLOWED_ACTION_TYPES = frozenset(
    {
        "browser.inspect",
        "browser.plan_click",
        "browser.plan_type",
        "browser.plan_submit",
        "browser.execute_click",
        "browser.execute_type",
    }
)

# Blocked action types
BLOCKED_ACTION_TYPES = frozenset(
    {
        "browser.execute_submit",
    }
)

# Valid task status values
VALID_TASK_STATUS = frozenset(
    {
        "received",
        "validation_failed",
        "approval_denied",
        "approval_invalid",
        "blocked",
        "executed",
        "failed",
    }
)

# Result data allowed fields (explicit whitelist, must match registry).
# NOTE: task_id is a top-level message field, NOT a result_data inner field.
# safe_dict() includes task_id at top-level alongside result_data contents.
RESULT_DATA_ALLOWED_KEYS = frozenset(
    {
        "status",
        "action",
        "selector",
        "executed",
        "element_found",
        "risk_level",
        "final_approval_required",
        "result",
        "error_code",
        "error_message",
        "target_url_domain",
        "text_length",
        "text_preview",
        "screenshot_ref",
        "screenshot_taken",
    }
)

# Forbidden result data keys (explicit blocklist for safety)
RESULT_DATA_FORBIDDEN_KEYS = frozenset(
    {
        "approval_token",
        "final_approval_token",
        "token_hash",
        "typed_text",
        "password",
        "otp",
        "cookie",
        "session",
        "authorization",
        "localStorage",
        "sessionStorage",
        "base64",
        "raw_screenshot",
        "full_dom",
    }
)

# Forbidden metadata keys
METADATA_FORBIDDEN_KEYS = frozenset(
    {
        "cookie",
        "cookies",
        "session",
        "authorization",
        "auth",
        "headers",
        "localStorage",
        "sessionStorage",
        "password",
        "otp",
        "typed_text",
        "full_dom",
    }
)


@dataclass
class BrowserWebSocketTaskPayloadSchema:
    """Formal WebSocket task payload schema.

    This schema defines the contract for browser task payloads
    transmitted via WebSocket or local task handler.

    Required fields:
    - task_id: Unique task identifier (string)
    - task_type: Always "browser_action" (literal)
    - action_type: One of ALLOWED_ACTION_TYPES (string)
    - selector: CSS selector for target element (string)

    Optional fields:
    - value: Value for type actions (string|null)
    - approval_id: Server-side approval ID (string|null)
    - approval_token: Approval token for verification (string|null)
    - final_approval_token: Final approval for critical actions (string|null)
    - requested_by: User ID or system identifier (string|null)
    - created_at: ISO8601 timestamp (string|null)
    - metadata: Custom safe metadata (dict|null)

    Constraints:
    - approval_token transmitted only for verification
    - approval_token never stored in result_data or logs
    - final_approval_token never stored in result_data or logs
    - token_hash never exposed in result_data or logs
    - action_type must be in ALLOWED_ACTION_TYPES
    - action_type must not be in BLOCKED_ACTION_TYPES
    - For execute_type actions, value is required
    """

    task_id: str
    task_type: Literal["browser_action"] = "browser_action"
    action_type: str = ""
    selector: str = ""
    value: str | None = None
    approval_id: str | None = None
    approval_token: str | None = None
    final_approval_token: str | None = None
    requested_by: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] | None = None

    @staticmethod
    def _validate_metadata(metadata: Any) -> None:
        if metadata and isinstance(metadata, dict):
            forbidden_keys_lower = {k.lower() for k in METADATA_FORBIDDEN_KEYS}
            for key in metadata:
                if key.lower() in forbidden_keys_lower:
                    raise ValueError(f"Forbidden metadata key: {key}")

    @staticmethod
    def _validate_fields(
        task_id: str,
        task_type: str,
        action_type: str,
        selector: str,
        value: Any,
        metadata: Any,
    ) -> None:
        """from_dict 입력 검증 (ValueError, 순서 고정)."""
        # Validate required fields
        if not task_id:
            raise ValueError("task_id is required")
        if task_type != "browser_action":
            raise ValueError(f"task_type must be 'browser_action', got {task_type}")
        if not action_type:
            raise ValueError("action_type is required")
        if not selector:
            raise ValueError("selector is required")

        # Validate action_type (check blocked first for clearer error)
        if action_type in BLOCKED_ACTION_TYPES:
            raise ValueError(f"action_type {action_type} is blocked")
        if action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"action_type {action_type} not in allowed types")

        # Validate action-specific requirements
        if action_type == "browser.execute_type" and not value:
            raise ValueError("value is required for browser.execute_type")

        # Validate metadata
        BrowserWebSocketTaskPayloadSchema._validate_metadata(metadata)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserWebSocketTaskPayloadSchema:
        """Create schema from dictionary.

        Args:
            data: Input dictionary

        Returns:
            BrowserWebSocketTaskPayloadSchema instance

        Raises:
            ValueError: If required fields missing or invalid
        """
        if not isinstance(data, dict):
            raise ValueError("Payload must be a dictionary")

        # Extract fields
        task_id = data.get("task_id", "").strip()
        task_type = data.get("task_type", "browser_action")
        action_type = data.get("action_type", "").strip()
        selector = data.get("selector", "").strip()
        value = data.get("value")
        approval_id = data.get("approval_id")
        approval_token = data.get("approval_token")
        final_approval_token = data.get("final_approval_token")
        requested_by = data.get("requested_by")
        created_at = data.get("created_at")
        metadata = data.get("metadata", {})

        cls._validate_fields(task_id, task_type, action_type, selector, value, metadata)

        return cls(
            task_id=task_id,
            task_type=task_type,
            action_type=action_type,
            selector=selector,
            value=value,
            approval_id=approval_id,
            approval_token=approval_token,
            final_approval_token=final_approval_token,
            requested_by=requested_by,
            created_at=created_at,
            metadata=metadata,
        )

    def validate(self) -> tuple[bool, str | None]:
        """Validate payload.

        Returns:
            (is_valid, error_message)
        """
        if not self.task_id:
            return False, "task_id is required"
        if self.task_type != "browser_action":
            return False, "task_type must be 'browser_action'"
        if not self.action_type:
            return False, "action_type is required"
        if not self.selector:
            return False, "selector is required"
        if self.action_type in BLOCKED_ACTION_TYPES:
            return False, f"action_type {self.action_type} is blocked"
        if self.action_type not in ALLOWED_ACTION_TYPES:
            return False, f"action_type {self.action_type} not allowed"
        if self.action_type == "browser.execute_type" and not self.value:
            return False, "value required for execute_type"

        return True, None

    def safe_dict(self) -> dict[str, Any]:
        """Convert to safe dict (removes tokens for storage).

        Returns:
            Dictionary with tokens removed but other fields preserved
        """
        data = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "action_type": self.action_type,
            "selector": self.selector,
            # NOTE: approval_id preserved for reference, not the token
            "approval_id": self.approval_id,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
        }

        # approval_token and final_approval_token NOT included
        # These are for verification only, never stored
        if self.metadata:
            data["metadata"] = self.metadata

        return {k: v for k, v in data.items() if v is not None}


@dataclass
class BrowserWebSocketTaskResultSchema:
    """Formal WebSocket task result schema.

    This schema defines the contract for browser task results
    returned via WebSocket or task result storage.

    Required fields:
    - task_id: Reference to original task_id (string)
    - status: Task status (received|validation_failed|approval_denied|
              approval_invalid|blocked|executed|failed)

    Optional fields (all safe for storage):
    - action: Action type that was attempted (string)
    - selector: Element selector (string)
    - executed: Whether action executed (boolean)
    - element_found: Whether element found in DOM (boolean)
    - risk_level: Risk level (low|medium|high|critical)
    - final_approval_required: Whether final approval needed (boolean)
    - result: Execution result code (string)
    - error_code: Error code if failed (string|null)
    - error_message: Human-readable error (string|null)
    - target_url_domain: Domain of target URL (string)
    - text_length: Length of typed text (integer)
    - text_preview: Always "[REDACTED]" (string)
    - screenshot_ref: Reference to stored screenshot (string|null)
    - screenshot_taken: Whether screenshot was taken (boolean)

    Constraints:
    - approval_token NEVER included
    - final_approval_token NEVER included
    - token_hash NEVER included
    - typed_text NEVER included (use text_length only)
    - password NEVER included
    - otp NEVER included
    - cookie NEVER included
    - session NEVER included
    - localStorage NEVER included
    - sessionStorage NEVER included
    - base64 content NEVER included
    - raw screenshot NEVER included
    - full DOM NEVER included
    """

    task_id: str
    status: str = "received"
    action: str = ""
    selector: str = ""
    executed: bool = False
    element_found: bool = False
    risk_level: str = "low"
    final_approval_required: bool = False
    result: str = "success"
    error_code: str | None = None
    error_message: str | None = None
    target_url_domain: str = ""
    text_length: int = 0
    text_preview: str = "[REDACTED]"
    screenshot_ref: str | None = None
    screenshot_taken: bool = False

    @classmethod
    def from_task_result(  # noqa: PLR0913 - 공개 classmethod 시그니처 유지(호출부·테스트 다수)
        cls,
        task_id: str,
        status: str,
        action: str = "",
        selector: str = "",
        executed: bool = False,
        element_found: bool = False,
        risk_level: str = "low",
        final_approval_required: bool = False,
        result: str = "success",
        error_code: str | None = None,
        error_message: str | None = None,
        target_url_domain: str = "",
        text_length: int = 0,
        text_preview: str = "[REDACTED]",
        screenshot_ref: str | None = None,
        screenshot_taken: bool = False,
    ) -> BrowserWebSocketTaskResultSchema:
        """Create result schema from task handler result.

        Args:
            task_id: Task identifier
            status: Task status
            action: Action type
            selector: Element selector
            executed: Whether action executed
            element_found: Whether element found
            risk_level: Risk level
            final_approval_required: Whether final approval needed
            result: Execution result
            error_code: Error code if any
            error_message: Error message if any
            target_url_domain: Target domain
            text_length: Length of typed text
            text_preview: Text preview (always redacted)
            screenshot_ref: Screenshot reference
            screenshot_taken: Whether screenshot taken

        Returns:
            BrowserWebSocketTaskResultSchema instance
        """
        # Validate status
        if status not in VALID_TASK_STATUS:
            logger.warning(f"Unknown status {status}, using 'received'")
            status = "received"

        return cls(
            task_id=task_id,
            status=status,
            action=action,
            selector=selector,
            executed=executed,
            element_found=element_found,
            risk_level=risk_level,
            final_approval_required=final_approval_required,
            result=result,
            error_code=error_code,
            error_message=error_message,
            target_url_domain=target_url_domain,
            text_length=text_length,
            text_preview=text_preview,
            screenshot_ref=screenshot_ref,
            screenshot_taken=screenshot_taken,
        )

    def validate_safe_result(self) -> tuple[bool, str | None]:
        """Validate that result contains no secrets.

        Returns:
            (is_safe, error_message)
        """
        if not self.task_id:
            return False, "task_id is required"

        # Check for forbidden keys (belt-and-suspenders)
        data_dict = asdict(self)
        for forbidden_key in RESULT_DATA_FORBIDDEN_KEYS:
            if forbidden_key in data_dict:
                value = data_dict[forbidden_key]
                if value is not None and value != "":
                    return False, f"Forbidden field present: {forbidden_key}"

        # text_preview must be redacted
        if self.text_preview != "[REDACTED]":
            return False, f"text_preview must be '[REDACTED]', got {self.text_preview}"

        return True, None

    def safe_dict(self) -> dict[str, Any]:
        """Convert to safe dict for storage/transmission.

        Returns:
            Dictionary with task_id (top-level) plus only allowed result_data fields.
        """
        data = asdict(self)

        # Ensure forbidden fields are removed
        for forbidden_key in RESULT_DATA_FORBIDDEN_KEYS:
            data.pop(forbidden_key, None)

        # Ensure text_preview is redacted
        data["text_preview"] = "[REDACTED]"

        # Allowed result_data fields + task_id (top-level routing field, not in result_data)
        out: dict[str, Any] = {k: v for k, v in data.items() if k in RESULT_DATA_ALLOWED_KEYS and v is not None}
        if self.task_id:
            out["task_id"] = self.task_id
        return out


def validate_payload_schema(data: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate input payload against schema.

    Args:
        data: Input dictionary

    Returns:
        (is_valid, error_message)
    """
    try:
        schema = BrowserWebSocketTaskPayloadSchema.from_dict(data)
        return schema.validate()
    except ValueError as e:
        return False, str(e)


def validate_result_schema(result: BrowserWebSocketTaskResultSchema) -> tuple[bool, str | None]:
    """Validate result schema for safety.

    Args:
        result: BrowserWebSocketTaskResultSchema instance

    Returns:
        (is_valid, error_message)
    """
    return result.validate_safe_result()


def safe_result_dict(result: BrowserWebSocketTaskResultSchema) -> dict[str, Any]:
    """Convert result to safe dictionary for storage.

    Args:
        result: BrowserWebSocketTaskResultSchema instance

    Returns:
        Safe dictionary with no secrets
    """
    return result.safe_dict()
