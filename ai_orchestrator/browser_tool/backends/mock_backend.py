"""Mock Browser Backend.

Provides mock/dry-run responses for browser tasks without actual Playwright execution.
Used for testing and dry_run=True mode.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..schemas import BrowserResult, BrowserTask


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def handle_task(task: BrowserTask) -> BrowserResult:
    """Process browser task with mock responses (no Playwright)."""
    action = task.action
    params = task.params or {}

    if action == "inspect":
        return _handle_inspect(params)
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
