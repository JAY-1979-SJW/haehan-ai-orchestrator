"""Browser Worker FastAPI app skeleton.

Note: This app is not running in this environment. It serves as a skeleton for
future deployment as a separate service. The actual browser operations are
handled by browser_worker.service when imported by the Tool Router.
"""
from fastapi import FastAPI
from browser_worker.schemas import WorkerBrowserRequest, WorkerBrowserResponse
from browser_worker.service import handle_browser_request, get_worker_status

# FastAPI app skeleton (not deployed in current environment)
app = FastAPI(
    title="Browser Worker",
    description="Separate tool for browser automation via Playwright",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "worker": "browser_worker"}


@app.get("/v1/worker/status")
def worker_status() -> dict:
    """Get worker status and capabilities."""
    return get_worker_status()


@app.post("/v1/browser/inspect")
def browser_inspect(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
    """Handle browser.inspect request."""
    response = handle_browser_request(request)
    return response


@app.post("/v1/browser/action")
def browser_action(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
    """Handle generic browser action request."""
    response = handle_browser_request(request)
    return response


# Note: This app is not run with uvicorn in the current environment.
# It serves as a specification for the future separate browser-worker service.
# When deployed, run with: uvicorn browser_worker.app:app --host 0.0.0.0 --port 9900
