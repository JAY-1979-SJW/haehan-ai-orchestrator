"""Browser Worker service — handles browser requests with policy checks."""
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from browser_worker.policy import WorkerSecurityPolicy, is_action_known
from browser_worker.backends.mock_playwright_backend import MockPlaywrightBackend
from browser_worker.backends.real_playwright_backend import RealPlaywrightBackend


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

    # 2. Route based on dry_run flag
    if request.dry_run:
        # Mock backend for dry_run
        allowed, reason = WorkerSecurityPolicy.validate_dry_run(request.action)
        if not allowed:
            return WorkerBrowserResponse.actual_execution_disabled(request.action, request.task_id)
        return MockPlaywrightBackend.handle_browser_action(request)
    else:
        # Real backend for actual execution (with policy validation)
        allowed, error_code = WorkerSecurityPolicy.validate_actual_execution(request.action, request.url)
        if not allowed:
            # Return precise error code based on policy violation
            error_messages = {
                "ACTION_NOT_ALLOWED_ACTUAL_EXECUTION": f"Action '{request.action}' is not allowed for actual execution",
                "URL_NOT_ALLOWED_ACTUAL_EXECUTION": f"URL '{request.url}' is not allowed for actual execution",
                "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED": "Browser worker actual execution is not enabled in this environment",
            }
            return WorkerBrowserResponse(
                success=False,
                action=request.action,
                task_id=request.task_id,
                browser_started=False,
                backend="mock_playwright_worker",
                status="error",
                error_code=error_code,
                error_message=error_messages.get(error_code, error_code),
            )
        return RealPlaywrightBackend().handle_browser_action(request)


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
