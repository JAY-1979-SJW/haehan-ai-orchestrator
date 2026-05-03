"""FastAPI application for file-map-executor service."""

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import logging

from .schemas import (
    ExecuteRequest,
    ExecuteResponse,
    PreflightRequest,
    PreflightResponse,
    HealthResponse,
    AuditResponse,
    RollbackResponse,
)
from .service import FileMapExecutorService
from .security import validate_target_path, validate_dry_run


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="file-map-executor",
    description="Dedicated executor service for file cleanup operations",
    version="1.0.0"
)

executor_service = FileMapExecutorService()


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="file-map-executor",
        version="1.0"
    )


@app.post("/cleanup/preflight", response_model=PreflightResponse)
async def preflight_cleanup(request: PreflightRequest):
    """Preflight validation for cleanup operation (read-only).

    Validates plans without executing any cleanup.
    Enforces /tmp target directory constraint.
    """

    # Validate target path (must be in /tmp)
    is_valid, error_msg = validate_target_path(request.base_target_dir)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    try:
        result = executor_service.preflight(request.model_dump())
        return PreflightResponse(**result)
    except Exception as e:
        logger.error(f"Preflight error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Preflight validation failed: {str(e)}"
        )


@app.post("/cleanup/execute", response_model=ExecuteResponse)
async def execute_cleanup(request: ExecuteRequest):
    """Execute cleanup operation (dry_run=true only).

    Validates input and delegates to executor service.
    Enforces dry_run=true policy.
    """

    # Validate dry_run (must be true)
    is_valid, error_msg = validate_dry_run(request.dry_run)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_msg
        )

    # Validate target path (must be in /tmp)
    is_valid, error_msg = validate_target_path(request.base_target_dir)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    try:
        result = executor_service.execute(request.model_dump())
        return ExecuteResponse(**result)
    except Exception as e:
        logger.error(f"Execution error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution failed: {str(e)}"
        )


@app.get("/cleanup/audit", response_model=AuditResponse)
async def get_audit(run_id: str = None):
    """Get audit record for a cleanup operation (read-only)."""
    try:
        result = executor_service.get_audit(run_id)
        return AuditResponse(**result)
    except Exception as e:
        logger.error(f"Audit query error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Audit query failed: {str(e)}"
        )


@app.get("/cleanup/rollback", response_model=RollbackResponse)
async def get_rollback(run_id: str = None):
    """Get rollback manifest for a cleanup operation (read-only, no execution)."""
    try:
        result = executor_service.get_rollback(run_id)
        return RollbackResponse(**result)
    except Exception as e:
        logger.error(f"Rollback query error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rollback query failed: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8510)
