"""Request/Response schemas for file-map-executor API."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ExecutePlan(BaseModel):
    """Single file move plan."""
    source: str
    target: str
    confirmed: bool = True


class ExecuteRequest(BaseModel):
    """cleanup-execute API request."""
    dry_run: bool = True
    preflight_id: Optional[str] = None
    package_id: Optional[str] = None
    approval_token: str
    user_confirmed_execution: bool = True
    base_target_dir: str
    plans: List[ExecutePlan] = []
    include_sensitive: bool = False


class ExecuteResponse(BaseModel):
    """cleanup-execute API response."""
    ok: bool
    run_id: str
    dry_run: bool = True
    success_count: int = 0
    succeeded: List[str] = []
    failed_count: int = 0
    failed: List[str] = []
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str = "1.0"


class AuditResponse(BaseModel):
    """Audit query response."""
    run_id: Optional[str] = None
    audit_lines: List[Dict[str, Any]] = []
    masked_paths: List[str] = []
    error: Optional[str] = None


class RollbackResponse(BaseModel):
    """Rollback query response."""
    run_id: Optional[str] = None
    manifest: Dict[str, Any] = {}
    rollback_status: str = "pending"
    error: Optional[str] = None


class PreflightItem(BaseModel):
    """Single item in preflight validation result."""
    source: str
    target: str
    status: str  # 'ok', 'conflict', 'source_missing', 'target_exists', 'invalid_path'
    reason: str = ""


class PreflightRequest(BaseModel):
    """cleanup-preflight API request (read-only validation)."""
    base_target_dir: str
    plans: List[ExecutePlan] = []
    include_sensitive: bool = False


class PreflightResponse(BaseModel):
    """cleanup-preflight API response (read-only)."""
    ok: bool
    preflight_id: str
    dry_run: bool = True  # Always true (read-only)
    total: int = 0
    ok_count: int = 0
    conflict_count: int = 0
    skipped_count: int = 0
    items: List[PreflightItem] = []
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""
    ok: bool = False
    error: str
    status_code: int
