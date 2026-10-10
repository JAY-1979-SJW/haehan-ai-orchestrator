"""Browser Submit Audit Log Persistence Module.

Append-only JSONL audit log for submit policy, preview, and result tracking.
No DB write, no production paths, test-only file operations.
Redacts sensitive data before storage.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

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

# Safe hidden fields that can preserve values (non-sensitive)
SAFE_HIDDEN_FIELD_NAMES = {
    "csrf_token",
    "csrf-token",
    "timestamp",
    "form_version",
    "form-version",
    "nonce",
    "request_id",
    "request-id",
}


@dataclass
class SubmitAuditEvent:
    """Audit event for submit lifecycle."""

    # Required: Schema & IDs
    schema_version: str
    event_id: str
    created_at: str  # ISO8601
    validation_id: str

    # Required: Request Context
    action_id: str
    site_id: str
    form_id: str
    submit_button_id: str
    intent: str

    # Required: Policy & Preview
    preview_hash: str
    policy_verdict: str
    risk_level: str

    # Required: User & Submit Status
    user_confirmed: bool
    submitted: bool
    submit_result: str  # "success" / "blocked" / "error" / "pending"

    # Required: Payload & Summary
    redacted_payload: dict
    result_summary: str

    # Optional: Approval & Error
    approved_by: str | None = None
    approved_at: str | None = None
    submit_timestamp: str | None = None
    error_reason: str | None = None

    # Optional: Metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class SubmitAuditWriteResult:
    """Result of audit event write operation."""

    success: bool
    path: str
    event_count: int
    error_message: str | None = None


def build_submit_audit_event(  # noqa: PLR0913 - 감사 이벤트 빌더, 필드별 인자가 공개 API
    validation_id: str,
    action_id: str,
    site_id: str,
    form_id: str,
    submit_button_id: str,
    intent: str,
    policy_verdict: str,
    risk_level: str,
    preview_hash: str,
    user_confirmed: bool,
    submitted: bool,
    submit_result: str,
    redacted_payload: dict,
    result_summary: str,
    approved_by: str | None = None,
    submit_timestamp: str | None = None,
    error_reason: str | None = None,
    metadata: dict | None = None,
) -> SubmitAuditEvent:
    """Build audit event from components.

    Args:
        validation_id: Link to validation request
        action_id: Action identifier (e.g., browser.submit.policy_check)
        site_id: Internal site ID
        form_id: Form identifier
        submit_button_id: Button element ID
        intent: User intent
        policy_verdict: "ALLOW" or "DENY"
        risk_level: "low", "medium", or "high"
        preview_hash: SHA256 hash of preview (64 chars)
        user_confirmed: User clicked OK
        submitted: Was form actually submitted
        submit_result: "success", "blocked", "error", or "pending"
        redacted_payload: Form data with sensitive values masked
        result_summary: Human-readable result
        approved_by: User ID if confirmed (optional)
        submit_timestamp: When submit happened (optional)
        error_reason: Error message if failed (optional)
        metadata: Additional context (optional)

    Returns:
        SubmitAuditEvent
    """
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    event_id = f"evt_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    return SubmitAuditEvent(
        schema_version="1.0",
        event_id=event_id,
        created_at=now,
        validation_id=validation_id,
        action_id=action_id,
        site_id=site_id,
        form_id=form_id,
        submit_button_id=submit_button_id,
        intent=intent,
        preview_hash=preview_hash,
        policy_verdict=policy_verdict,
        risk_level=risk_level,
        user_confirmed=user_confirmed,
        submitted=submitted,
        submit_result=submit_result,
        redacted_payload=redacted_payload,
        result_summary=result_summary,
        approved_by=approved_by,
        approved_at=now if approved_by else None,
        submit_timestamp=submit_timestamp,
        error_reason=error_reason,
        metadata=metadata or {},
    )


def _is_sensitive_field_name(field_name: str) -> bool:
    """Check if a field name is sensitive."""
    return field_name in SENSITIVE_FIELD_NAMES or any(
        sensitive in field_name for sensitive in ["password", "token", "secret", "key", "cookie"]
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
            result["value"] = {"masked": True}
        return result
    return redact_audit_payload(item)


def redact_audit_payload(payload: dict) -> dict:
    """Remove/mask sensitive data from payload.

    Sensitive field names are masked as {"masked": true}.
    Safe hidden fields preserve their values.
    List items with a "name" attribute matching a sensitive field have their
    "value" masked.

    Args:
        payload: Original form data dict

    Returns:
        Redacted payload dict
    """
    result = {}

    for key, value in payload.items():
        field_name = key.lower()

        # Safe hidden fields are checked first so that fields like csrf_token
        # (which contain "token") are preserved rather than masked.
        if field_name in SAFE_HIDDEN_FIELD_NAMES:
            result[key] = value
        elif _is_sensitive_field_name(field_name):
            result[key] = {"masked": True}
        else:
            # Safe field - check if value looks sensitive
            if isinstance(value, str):
                if len(value) > 100 or any(
                    pattern in value.lower() for pattern in ["-----BEGIN", "-----END", "0x", "0X"]
                ):
                    # Looks like a key/secret - mask it
                    result[key] = {"masked": True}
                else:
                    result[key] = value
            elif isinstance(value, dict):
                # Recursively redact nested dict
                result[key] = redact_audit_payload(value)
            elif isinstance(value, list):
                # Redact list items with name-based masking support
                result[key] = [_redact_list_item(item) for item in value]
            else:
                result[key] = value

    return result


# 값이 비어 있으면 "<name> is required" 오류가 되는 필드 (검사 순서 고정)
_REQUIRED_TRUTHY_FIELDS: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "created_at",
    "validation_id",
    "action_id",
    "site_id",
    "form_id",
    "submit_button_id",
    "intent",
    "preview_hash",
)


def validate_submit_audit_event(event: SubmitAuditEvent) -> list[str]:
    """Validate event has all required fields.

    Args:
        event: Audit event to validate

    Returns:
        List of error messages (empty list = valid)
    """
    errors: list[str] = []

    # Required fields
    for name in _REQUIRED_TRUTHY_FIELDS:
        if not getattr(event, name):
            errors.append(f"{name} is required")
    if event.preview_hash and len(event.preview_hash) != 64:
        errors.append(f"preview_hash must be 64 chars (got {len(event.preview_hash)})")
    if not event.policy_verdict:
        errors.append("policy_verdict is required")
    if event.policy_verdict not in ["ALLOW", "DENY"]:
        errors.append(f"policy_verdict must be ALLOW or DENY (got {event.policy_verdict})")
    if not event.risk_level:
        errors.append("risk_level is required")
    if event.risk_level not in ["low", "medium", "high"]:
        errors.append(f"risk_level must be low/medium/high (got {event.risk_level})")
    errors.extend(_validate_result_fields(event))

    return errors


def _validate_result_fields(event: SubmitAuditEvent) -> list[str]:
    """user_confirmed 이후 결과 관련 필수 필드 검증 (오류 순서 유지)."""
    errors: list[str] = []
    if event.user_confirmed is None:
        errors.append("user_confirmed is required")
    if event.submitted is None:
        errors.append("submitted is required")
    if not event.submit_result:
        errors.append("submit_result is required")
    if event.submit_result not in ["success", "blocked", "error", "pending"]:
        errors.append(f"submit_result must be success/blocked/error/pending (got {event.submit_result})")
    if event.redacted_payload is None:
        errors.append("redacted_payload is required")
    if not event.result_summary:
        errors.append("result_summary is required")
    return errors


def serialize_audit_event(event: SubmitAuditEvent) -> str:
    """Convert event to JSON string (one line).

    Uses: sort_keys=True, ensure_ascii=False

    Args:
        event: Audit event to serialize

    Returns:
        JSON string (one line, no newline)

    Raises:
        ValueError if event contains non-serializable objects
    """
    event_dict = asdict(event)
    return json.dumps(event_dict, sort_keys=True, ensure_ascii=False)


def append_submit_audit_event(
    path: Path,
    event: SubmitAuditEvent,
) -> SubmitAuditWriteResult:
    """Append event to JSONL file (append-only, no overwrite).

    Behavior:
        - If file doesn't exist, create it
        - If file exists, append to end
        - Never overwrite existing content
        - Parent directory must exist

    Args:
        path: Path to JSONL file (Path or str)
        event: Audit event to append

    Returns:
        SubmitAuditWriteResult with success status and event count

    Raises:
        ValueError: If event validation fails
        IOError: If write fails
    """
    path = Path(path)

    # Validate event
    errors = validate_submit_audit_event(event)
    if errors:
        return SubmitAuditWriteResult(
            success=False, path=str(path), event_count=0, error_message=f"Event validation failed: {'; '.join(errors)}"
        )

    try:
        # Serialize event
        json_line = serialize_audit_event(event)

        # Append to file
        with path.open("a", encoding="utf-8") as f:
            f.write(json_line + "\n")

        # Count events in file
        event_count = 0
        if path.exists():
            with path.open(encoding="utf-8") as f:
                event_count = sum(1 for line in f if line.strip())

        return SubmitAuditWriteResult(
            success=True,
            path=str(path),
            event_count=event_count,
            error_message=None,
        )

    except OSError as e:
        return SubmitAuditWriteResult(
            success=False, path=str(path), event_count=0, error_message=f"Write failed: {e!s}"
        )


def read_submit_audit_events(path: Path) -> list[dict]:
    """Read all events from JSONL file (test only).

    Args:
        path: Path to JSONL file

    Returns:
        List of event dicts (parsed from JSON)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If any line is not valid JSON
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Audit log file not found: {path}")

    events = []
    with path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_num}: {e!s}") from e

    return events
