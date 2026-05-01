"""Browser Tool Protocol Schemas.

Internal data structures for browser task routing and result handling.
Separate from public API response schemas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


BrowserBackendName = Literal["mock", "server_playwright", "local_agent", "hwp", "excel", "cad"]
BrowserActionName = Literal["inspect", "plan_click", "plan_type", "plan_submit", "execute_click", "execute_type"]
BrowserRiskLevel = Literal["low", "medium", "high"]


@dataclass
class BrowserTask:
    """Browser automation task request."""

    action: BrowserActionName
    params: dict[str, Any] = field(default_factory=dict)

    # Optional fields for future extension
    backend: BrowserBackendName | None = None
    timeout_seconds: int = 30
    approval_required: bool = False


@dataclass
class BrowserResult:
    """Browser automation task result."""

    success: bool
    action: BrowserActionName
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_code: str = ""
    backend: BrowserBackendName = "mock"


@dataclass
class BrowserTaskPolicy:
    """Policy for a specific browser action."""

    action: BrowserActionName
    risk_level: BrowserRiskLevel
    requires_approval: bool
    requires_dry_run: bool  # if True, only dry_run=True is allowed
    blocked: bool = False
    blocked_reason: str = ""
