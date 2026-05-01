"""Browser Worker service — handles browser requests with policy checks."""
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from browser_worker.policy import WorkerSecurityPolicy, is_action_known
from browser_worker.backends.mock_playwright_backend import MockPlaywrightBackend


def handle_browser_request(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
    """Handle browser operation request from Tool Router.

    Args:
        request: Browser operation request

    Returns:
        Browser operation response
    """
    # 1. Check if action is known
    if not is_action_known(request.action):
        return WorkerBrowserResponse.unknown_action(request.action, request.task_id)

    # 2. Validate request based on dry_run flag
    if request.dry_run:
        allowed, reason = WorkerSecurityPolicy.validate_dry_run(request.action)
    else:
        allowed, reason = WorkerSecurityPolicy.validate_actual_execution(request.action)

    if not allowed:
        # Actual execution disabled or not allowed action
        return WorkerBrowserResponse.actual_execution_disabled(request.action, request.task_id)

    # 3. Route to backend
    return MockPlaywrightBackend.handle_browser_action(request)


def get_worker_status() -> dict:
    """Get Browser Worker status and capabilities.

    Returns:
        Status dictionary with info about supported actions and policies.
    """
    return {
        "worker_type": "browser_worker",
        "status": "ready",
        "backend": "mock_playwright_worker",
        "capabilities": {
            "dry_run": ["browser.inspect"],
            "actual_execution": [],
        },
        "security_policies": WorkerSecurityPolicy.get_security_notes(),
    }
