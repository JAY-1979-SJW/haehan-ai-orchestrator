"""Mock Browser Backend.

Provides mock/dry-run responses for browser tasks without actual Playwright execution.
Used for testing and dry_run=True mode.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import BrowserResult, BrowserTask


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def handle_task(task: BrowserTask) -> BrowserResult:
    """Process browser task with mock responses (no Playwright)."""
    action = task.action
    params = task.params or {}

    if action == "inspect":
        return _handle_inspect(params)
    elif action == "plan_type":
        return _handle_plan_type(params)
    elif action == "open_type_close_controlled":
        return _handle_open_type_close_controlled(params)
    else:
        # Unknown action
        return BrowserResult(
            success=False,
            action=action,
            data={},
            error=f"unknown browser action: {action}",
            error_code="UNKNOWN_BROWSER_ACTION",
            backend="mock",
        )


def _handle_inspect(params: dict[str, Any]) -> BrowserResult:
    """Handle browser.inspect action with mock response."""
    dry_run = params.get("dry_run", False)
    if not isinstance(dry_run, bool):
        dry_run = str(dry_run).lower() in ("true", "1", "yes")

    url = params.get("url")
    if url is not None:
        url = str(url).strip() or None

    if dry_run:
        # Mock successful dry_run response
        return BrowserResult(
            success=True,
            action="inspect",
            data={
                "action": "browser.inspect",
                "dry_run": True,
                "browser_started": False,
                "url": url,
                "title": "DRY_RUN_BROWSER_INSPECT",
                "status": "ok",
                "timestamp": _now_iso(),
            },
            backend="mock",
        )
    else:
        # Block actual execution (not implemented in this stage)
        return BrowserResult(
            success=False,
            action="inspect",
            data={
                "action": "browser.inspect",
                "dry_run": False,
                "browser_started": False,
                "reason": "actual_browser_execution_not_enabled",
                "timestamp": _now_iso(),
            },
            error="actual browser execution not supported in this stage",
            error_code="ACTUAL_BROWSER_EXECUTION_NOT_ENABLED",
            backend="mock",
        )


def _handle_plan_type(params: dict[str, Any]) -> BrowserResult:
    """Handle browser.plan_type action (plan-only, no actual input)."""
    # browser.plan_type은 항상 plan-only (typed=false, 실제 입력 없음)
    field_id = params.get("field_id", "sample_text_field")
    sample_value_id = params.get("sample_value_id", "sample_text_short")

    # Sample value allowlist (고정값만)
    sample_values = {
        "sample_text_short": "sample input",
        "sample_text_medium": "sample input with more content",
        "sample_number": "1234",
        "sample_date": "2026-05-06",
    }

    # Field role mapping (고정 enum)
    field_roles = {
        "sample_text_field": "text_input",
        "sample_search_field": "search_input",
    }

    # Validate field_id
    if field_id not in field_roles:
        return BrowserResult(
            success=False,
            action="plan_type",
            data={},
            error=f"invalid field_id: {field_id}",
            error_code="INVALID_FIELD_ID",
            backend="mock",
        )

    # Validate sample_value_id
    if sample_value_id not in sample_values:
        return BrowserResult(
            success=False,
            action="plan_type",
            data={},
            error=f"invalid sample_value_id: {sample_value_id}",
            error_code="INVALID_SAMPLE_VALUE_ID",
            backend="mock",
        )

    # Mock successful plan_type response (plan-only)
    return BrowserResult(
        success=True,
        action="plan_type",
        data={
            "action": "browser.plan_type",
            "typed": False,
            "field_id": field_id,
            "field_role": field_roles[field_id],
            "sample_value_id": sample_value_id,
            "input_redacted": True,
            "requires_approval": False,
            "timestamp": _now_iso(),
        },
        backend="mock",
    )


def _handle_open_type_close_controlled(params: dict[str, Any]) -> BrowserResult:
    """Handle browser.open_type_close_controlled action (controlled type input with approval)."""
    # Sample value allowlist (고정값만)
    sample_values = {
        "sample_text_short": "sample input",
        "sample_text_medium": "sample input with more content",
        "sample_number": "1234",
        "sample_date": "2026-05-06",
    }

    # Field role mapping (고정 enum)
    field_roles = {
        "sample_text_field": "text_input",
        "sample_search_field": "search_input",
    }

    field_id = params.get("field_id")
    sample_value_id = params.get("sample_value_id")
    url = params.get("url")

    # Validate field_id
    if field_id is None or field_id not in field_roles:
        return BrowserResult(
            success=False,
            action="open_type_close_controlled",
            data={},
            error=f"invalid or missing field_id: {field_id}",
            error_code="INVALID_FIELD_ID",
            backend="mock",
        )

    # Validate sample_value_id
    if sample_value_id is None or sample_value_id not in sample_values:
        return BrowserResult(
            success=False,
            action="open_type_close_controlled",
            data={},
            error=f"invalid or missing sample_value_id: {sample_value_id}",
            error_code="INVALID_SAMPLE_VALUE_ID",
            backend="mock",
        )

    # Validate URL (must be present and sample-like)
    if url is None or not isinstance(url, str):
        return BrowserResult(
            success=False,
            action="open_type_close_controlled",
            data={},
            error="url is required",
            error_code="MISSING_URL",
            backend="mock",
        )

    # Mock successful open_type_close_controlled response
    return BrowserResult(
        success=True,
        action="open_type_close_controlled",
        data={
            "action": "browser.open_type_close_controlled",
            "typed": True,
            "field_id": field_id,
            "field_role": field_roles[field_id],
            "sample_value_id": sample_value_id,
            "executed": True,
            "requires_approval": True,
            "lifecycle": {
                "opened": True,
                "typed": True,
                "closed": True,
            },
            "timestamp": _now_iso(),
        },
        backend="mock",
    )
