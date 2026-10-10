"""Browser Workflow Audit Writer Implementation.

Append-only JSONL audit writer for workflow lifecycle events.
Handles redaction of sensitive data, validation, and append-only persistence.
Test-only implementation (no production paths, no DB write).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.browser_tool.approval.approval_record_store import read_jsonl_records

# Sensitive field names that must be redacted
SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "session",
    "sessionid",
    "session_id",
    "cookie",
    "cookies",
    "private_key",
    "private-key",
    "pkey",
    "auth",
    "authorization",
    "bearer",
    "jwt",
    "signature",
    "otp",
    "totp",
    "mfa",
    "2fa",
    "card",
    "cc_number",
    "cvv",
    "cvc",
    "ssn",
    "social_security",
    "license_key",
    "license-key",
    "encryption_key",
    "enc_key",
}

# Sensitive URL query parameters
SENSITIVE_URL_PARAMS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "otp",
    "session",
    "cookie",
    "authorization",
}


@dataclass
class WorkflowAuditRecord:
    """Audit record for workflow lifecycle event."""

    # Required: Identifiers
    audit_id: str
    workflow_run_id: str
    event_type: str

    # Required: Action & Operation
    action_name: str
    operation_type: str
    workflow_id: str

    # Required: Policy Decisions
    gate_decision: str
    block_reason: str | None = None

    # Required: Context
    tenant_id: str = ""
    user_id: str = ""
    site_id: str = ""
    target_domain: str = ""
    target_url_hash: str = ""
    target_url_redacted: str = ""

    # Required: Input Handling
    input_redaction_status: str = "not_redacted"  # "not_redacted" | "partial" | "full"
    sensitive_input_detected: bool = False

    # Required: Approval
    approval_id: str | None = None
    approval_status: str = "not_required"  # "not_required" | "pending" | "approved" | "rejected"

    # Required: Execution State
    dry_run: bool = True
    production_mode: bool = False
    safe_to_dispatch: bool = False
    safe_to_execute: bool = False

    # Required: Result
    result_status: str = "recorded"  # "recorded" | "blocked" | "allowed" | "error"
    error_code: str | None = None

    # Required: Timestamp
    created_at: str = ""  # ISO 8601 UTC

    # Optional: Metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class WorkflowAuditWriteResult:
    """Result of audit record write operation."""

    success: bool
    audit_id: str
    path: str
    event_count: int = 0
    bytes_written: int = 0
    error_message: str | None = None


# Valid event types
VALID_EVENT_TYPES = {
    "REQUEST_RECEIVED",
    "GATE_EVALUATED",
    "APPROVAL_CHECKED",
    "AUDIT_REQUIRED",
    "AUDIT_READY",
    "DISPATCH_BLOCKED",
    "DISPATCH_ALLOWED_DRY_RUN",
    "EXECUTION_SKIPPED",
    "EXECUTION_RESULT_RECORDED",
}


def _is_sensitive_field_name(field_name: str) -> bool:
    """Check if a field name is sensitive."""
    field_lower = field_name.lower()
    return field_lower in SENSITIVE_FIELD_NAMES or any(
        sensitive in field_lower for sensitive in ["password", "token", "secret", "key", "cookie"]
    )


def _redact_list_item(item: object) -> object:
    """Redact a list item, with name-based masking for form field dicts.

    Handles {"name": "password", "value": "..."} style form field dicts
    where the `name` attribute identifies a sensitive field.
    """
    if not isinstance(item, dict):
        return item
    name_val = item.get("name", "")
    if isinstance(name_val, str) and _is_sensitive_field_name(name_val.lower()):
        # name key identifies a sensitive field — mask the value
        result = {k: v for k, v in item.items()}
        if "value" in result:
            result["value"] = "[REDACTED]"
        return result
    return redact_audit_payload(item)


def redact_audit_payload(payload: Any) -> Any:
    """Remove/mask sensitive data from payload.

    Args:
        payload: Original data (dict, list, str, etc.)

    Returns:
        Redacted data with sensitive values masked
    """
    if isinstance(payload, dict):
        result = {}
        for key, value in payload.items():
            if _is_sensitive_field_name(key):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_audit_payload(value)
        return result

    elif isinstance(payload, list):
        return [_redact_list_item(item) for item in payload]

    elif isinstance(payload, str):
        # Check if string looks like a sensitive value
        if len(payload) > 100 or any(pattern in payload.lower() for pattern in ["-----BEGIN", "-----END", "0x"]):
            return "[REDACTED]"
        return payload

    else:
        return payload


def _redact_url(url: str) -> tuple[str, str]:
    """Redact sensitive query parameters from URL.

    Args:
        url: Original URL

    Returns:
        Tuple of (redacted_url, url_hash)
    """
    if not url:
        return "", ""

    # Parse URL and redact sensitive query params
    try:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        # Redact sensitive params
        redacted_params = {}
        for key, values in query_params.items():
            if key.lower() in SENSITIVE_URL_PARAMS:
                redacted_params[key] = ["[REDACTED]"]
            else:
                redacted_params[key] = values

        # Reconstruct URL
        redacted_query = urlencode(redacted_params, doseq=True)
        redacted_parsed = parsed._replace(query=redacted_query)
        redacted_url = urlunparse(redacted_parsed)

        # Generate hash from redacted URL
        url_hash = hashlib.sha256(redacted_url.encode()).hexdigest()

        return redacted_url, url_hash

    except Exception:  # noqa: BLE001 - 감사 기록용 URL 리다크션 실패 시 [REDACTED_URL] 플레이스홀더 반환 — fail-safe, 원본 URL 노출 없음
        # If URL parsing fails, return redacted placeholder
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return "[REDACTED_URL]", url_hash


def build_audit_record(  # noqa: PLR0913 - 감사 레코드 빌더, 필드별 인자가 공개 API
    workflow_run_id: str,
    event_type: str,
    action_name: str,
    operation_type: str,
    workflow_id: str,
    gate_decision: str,
    tenant_id: str = "",
    user_id: str = "",
    site_id: str = "",
    target_domain: str = "",
    target_url: str = "",
    approval_id: str | None = None,
    approval_status: str = "not_required",
    sensitive_input_detected: bool = False,
    input_payload: dict | None = None,
    dry_run: bool = True,
    production_mode: bool = False,
    safe_to_dispatch: bool = False,
    safe_to_execute: bool = False,
    result_status: str = "recorded",
    block_reason: str | None = None,
    error_code: str | None = None,
    metadata: dict | None = None,
) -> WorkflowAuditRecord:
    """Build audit record from components.

    Args:
        workflow_run_id: Workflow execution ID
        event_type: Event type (one of VALID_EVENT_TYPES)
        action_name: Action name (e.g., "browser.execute_click")
        operation_type: Operation type (read, navigate, open_url, click, type, submit)
        workflow_id: Workflow identifier
        gate_decision: Gate decision (ALLOW, BLOCK, DENY_BY_DEFAULT)
        tenant_id: Tenant context ID
        user_id: User identifier
        site_id: Site identifier
        target_domain: Target domain
        target_url: Target URL (will be redacted)
        approval_id: Approval record ID
        approval_status: Approval status
        sensitive_input_detected: Whether sensitive input was detected
        input_payload: Input data (will be redacted)
        dry_run: Whether this is a dry-run
        production_mode: Whether production mode
        safe_to_dispatch: Whether safe to dispatch
        safe_to_execute: Whether safe to execute
        result_status: Result status
        block_reason: Reason for blocking
        error_code: Error code if applicable
        metadata: Additional metadata

    Returns:
        WorkflowAuditRecord
    """
    audit_id = f"audit_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    # Redact URL
    target_url_redacted, target_url_hash = _redact_url(target_url)

    # Determine input redaction status
    if input_payload:
        redact_audit_payload(input_payload)
        input_redaction_status = "full" if sensitive_input_detected else "partial"
    else:
        input_redaction_status = "not_redacted"

    return WorkflowAuditRecord(
        audit_id=audit_id,
        workflow_run_id=workflow_run_id,
        event_type=event_type,
        action_name=action_name,
        operation_type=operation_type,
        workflow_id=workflow_id,
        gate_decision=gate_decision,
        block_reason=block_reason,
        tenant_id=tenant_id,
        user_id=user_id,
        site_id=site_id,
        target_domain=target_domain,
        target_url_hash=target_url_hash,
        target_url_redacted=target_url_redacted,
        input_redaction_status=input_redaction_status,
        sensitive_input_detected=sensitive_input_detected,
        approval_id=approval_id,
        approval_status=approval_status,
        dry_run=dry_run,
        production_mode=production_mode,
        safe_to_dispatch=safe_to_dispatch,
        safe_to_execute=safe_to_execute,
        result_status=result_status,
        error_code=error_code,
        created_at=now,
        metadata=metadata or {},
    )


def _validate_required_string_fields(record: WorkflowAuditRecord) -> list[str]:
    """audit_id ~ workflow_id 필수 문자열 필드 검증 (오류 순서 유지)."""
    errors: list[str] = []

    # Required string fields
    if not record.audit_id:
        errors.append("audit_id is required")
    if not record.workflow_run_id:
        errors.append("workflow_run_id is required")
    if not record.event_type:
        errors.append("event_type is required")
    elif record.event_type not in VALID_EVENT_TYPES:
        errors.append(f"event_type must be one of {VALID_EVENT_TYPES}, got {record.event_type}")

    if not record.action_name:
        errors.append("action_name is required")
    if not record.operation_type:
        errors.append("operation_type is required")
    if not record.workflow_id:
        errors.append("workflow_id is required")

    return errors


def validate_audit_record(record: WorkflowAuditRecord) -> list[str]:
    """Validate audit record has required fields and valid values.

    Args:
        record: Audit record to validate

    Returns:
        List of error messages (empty list = valid)
    """
    errors = _validate_required_string_fields(record)

    # Gate decision
    if not record.gate_decision:
        errors.append("gate_decision is required")
    if record.gate_decision not in ["ALLOW", "BLOCK", "DENY_BY_DEFAULT"]:
        errors.append(f"gate_decision must be ALLOW/BLOCK/DENY_BY_DEFAULT, got {record.gate_decision}")

    # Timestamp
    if not record.created_at:
        errors.append("created_at is required")

    # Policy enforcement: safe_to_execute must be false in this phase
    if record.safe_to_execute:
        errors.append("safe_to_execute must be false in this phase")

    # Policy enforcement: production_mode=true requires safe_to_execute=false
    if record.production_mode and record.safe_to_execute:
        errors.append("production_mode=true requires safe_to_execute=false")

    # Approval status validation
    valid_approval_status = {"not_required", "pending", "approved", "rejected"}
    if record.approval_status not in valid_approval_status:
        errors.append(f"approval_status must be one of {valid_approval_status}, got {record.approval_status}")

    return errors


def append_audit_record(
    record: WorkflowAuditRecord,
    jsonl_path: Path | str,
) -> WorkflowAuditWriteResult:
    """Append audit record to JSONL file (append-only, no overwrite).

    Behavior:
        - If file doesn't exist, create it
        - If file exists, append to end
        - Never overwrite existing content
        - Parent directory must exist

    Args:
        record: Audit record to append
        jsonl_path: Path to JSONL file

    Returns:
        WorkflowAuditWriteResult with success status

    Raises:
        ValueError: If record validation fails
        IOError: If write fails
    """
    jsonl_path = Path(jsonl_path)

    # Validate record
    errors = validate_audit_record(record)
    if errors:
        return WorkflowAuditWriteResult(
            success=False,
            audit_id=record.audit_id,
            path=str(jsonl_path),
            error_message=f"Validation failed: {'; '.join(errors)}",
        )

    try:
        # Serialize record to JSON line
        record_dict = asdict(record)
        json_line = json.dumps(record_dict, ensure_ascii=False, sort_keys=True)

        # Append to file
        with jsonl_path.open("a", encoding="utf-8") as f:
            bytes_written = f.write(json_line + "\n")

        # Count events in file
        event_count = 0
        if jsonl_path.exists():
            with jsonl_path.open(encoding="utf-8") as f:
                event_count = sum(1 for line in f if line.strip())

        return WorkflowAuditWriteResult(
            success=True,
            audit_id=record.audit_id,
            path=str(jsonl_path),
            event_count=event_count,
            bytes_written=bytes_written,
            error_message=None,
        )

    except OSError as e:
        return WorkflowAuditWriteResult(
            success=False, audit_id=record.audit_id, path=str(jsonl_path), error_message=f"Write failed: {e!s}"
        )


def read_audit_records(jsonl_path: Path | str) -> list[dict]:
    """Read all audit records from JSONL file.

    Args:
        jsonl_path: Path to JSONL file

    Returns:
        List of record dicts (parsed from JSON)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If any line is not valid JSON
    """
    return read_jsonl_records(jsonl_path, "Audit")
