"""
Submit Approval State Persistence Module

Manages approval decision history as append-only JSONL event log.
- Tracks approval requests, approvals, cancellations
- Enables audit trail for compliance
- Provides state query interface
- No network, DB, or environment variable dependencies
"""

import json
from datetime import UTC, datetime
from pathlib import Path


class ApprovalStateError(Exception):
    """Base exception for approval state operations."""

    pass


class ValidationError(ApprovalStateError):
    """Raised when event validation fails."""

    pass


def create_approval_requested_event(
    validation_id: str,
    preview_hash: str,
    site_id: str,
    form_id: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """
    Create an approval requested event.

    Args:
        validation_id: Unique validation identifier
        preview_hash: Hash of the preview payload
        site_id: Target site identifier
        form_id: Target form identifier
        user_id: User who requested approval (optional)
        tenant_id: Tenant identifier (optional)

    Returns:
        Event dictionary

    Raises:
        ValidationError: If required fields are missing
    """
    if not validation_id:
        raise ValidationError("validation_id is required")
    if not preview_hash:
        raise ValidationError("preview_hash is required")

    return {
        "schema_version": "1.0",
        "event_type": "approval_requested",
        "validation_id": validation_id,
        "preview_hash": preview_hash,
        "site_id": site_id,
        "form_id": form_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def create_approval_decision_event(
    validation_id: str,
    preview_hash: str,
    approval_status: str,
    decided_by: str | None = None,
) -> dict:
    """
    Create an approval decision event (approved/cancelled).

    Args:
        validation_id: Unique validation identifier
        preview_hash: Hash matching the requested event
        approval_status: "approved" or "cancelled"
        decided_by: User/system that made the decision (optional)

    Returns:
        Event dictionary

    Raises:
        ValidationError: If validation fails
    """
    if not validation_id:
        raise ValidationError("validation_id is required")
    if not preview_hash:
        raise ValidationError("preview_hash is required")
    if approval_status not in ("approved", "cancelled"):
        raise ValidationError(f"approval_status must be 'approved' or 'cancelled', got '{approval_status}'")

    event_type = "approval_decision_approved" if approval_status == "approved" else "approval_decision_cancelled"

    return {
        "schema_version": "1.0",
        "event_type": event_type,
        "validation_id": validation_id,
        "preview_hash": preview_hash,
        "approval_status": approval_status,
        "decided_by": decided_by,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def append_approval_state_event(log_path: Path, event: dict) -> None:
    """
    Append an event to the approval state log (JSONL format, append-only).

    Args:
        log_path: Path to JSONL log file
        event: Event dictionary to append

    Raises:
        ValidationError: If event validation fails
    """
    if not isinstance(event, dict):
        raise ValidationError("event must be a dictionary")
    if "schema_version" not in event:
        raise ValidationError("event must have schema_version")
    if "event_type" not in event:
        raise ValidationError("event must have event_type")
    if "validation_id" not in event:
        raise ValidationError("event must have validation_id")

    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append to log (never truncate, always append)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_approval_state_events(log_path: Path) -> list[dict]:
    """
    Read all approval state events from JSONL log.

    Args:
        log_path: Path to JSONL log file

    Returns:
        List of event dictionaries in chronological order

    Raises:
        ApprovalStateError: If file cannot be parsed
    """
    if not log_path.exists():
        return []

    events = []
    with log_path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError as e:
                raise ApprovalStateError(f"Invalid JSON at line {line_num}: {e}") from e

    return events


def latest_approval_state(
    events: list[dict],
    preview_hash: str,
) -> dict | None:
    """
    Get the latest approval state for a given preview_hash.

    Args:
        events: List of approval state events
        preview_hash: The preview hash to search for

    Returns:
        Latest event for the preview_hash, or None if not found
    """
    if not preview_hash:
        return None

    # Find all events matching this preview_hash, in order
    matching_events = [e for e in events if e.get("preview_hash") == preview_hash]

    if not matching_events:
        return None

    # Return the last event (most recent)
    return matching_events[-1]


def get_approval_status(event: dict | None) -> str:
    """
    Get the approval status string from an event.

    Args:
        event: Event dictionary or None

    Returns:
        Status: "pending", "approved", "cancelled", or "unknown"
    """
    if event is None:
        return "pending"

    event_type = event.get("event_type", "")
    if event_type == "approval_decision_approved":
        return "approved"
    elif event_type == "approval_decision_cancelled":
        return "cancelled"
    elif event_type == "approval_requested":
        return "pending"
    else:
        return "unknown"
