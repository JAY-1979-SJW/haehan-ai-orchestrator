"""Worker browser request/response schemas."""
from typing import Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class WorkerBrowserRequest:
    """Browser operation request from Tool Router to Worker."""
    action: str  # e.g., "browser.inspect"
    url: str
    task_id: str
    dry_run: bool = False
    payload: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class WorkerBrowserResponse:
    """Browser operation response from Worker."""
    success: bool
    action: str
    task_id: str
    browser_started: bool
    backend: str  # e.g., "mock_playwright_worker"
    title: Optional[str] = None
    url: Optional[str] = None
    status: str = "ok"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def dry_run_success(cls, action: str, task_id: str, url: str) -> "WorkerBrowserResponse":
        """Create successful dry-run response."""
        return cls(
            success=True,
            action=action,
            task_id=task_id,
            browser_started=False,
            backend="mock_playwright_worker",
            title="DRY_RUN_BROWSER_INSPECT",
            url=url,
            status="ok",
        )

    @classmethod
    def actual_execution_disabled(cls, action: str, task_id: str) -> "WorkerBrowserResponse":
        """Create error response for actual execution not enabled."""
        return cls(
            success=False,
            action=action,
            task_id=task_id,
            browser_started=False,
            backend="mock_playwright_worker",
            status="error",
            error_code="ACTUAL_BROWSER_EXECUTION_NOT_ENABLED",
            error_message="Browser worker actual execution is not enabled in this environment",
        )

    @classmethod
    def unknown_action(cls, action: str, task_id: str) -> "WorkerBrowserResponse":
        """Create error response for unknown action."""
        return cls(
            success=False,
            action=action,
            task_id=task_id,
            browser_started=False,
            backend="mock_playwright_worker",
            status="error",
            error_code="UNKNOWN_BROWSER_ACTION",
            error_message=f"Browser action '{action}' is not supported",
        )
