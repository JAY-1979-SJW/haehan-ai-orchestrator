"""Browser Workflow Approval Record Store Implementation.

Append-only JSONL approval event store for workflow lifecycle approval tracking.
Handles redaction of sensitive data, validation, and append-only persistence.
Test-only implementation (no production paths, no DB write).
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

# append 직렬화 — 라우터 핸들러가 스레드풀에서 동시 실행돼도 줄 인터리브/개수 계산 경합이 없게 한다.
# 락 안에서 다른 락을 잡지 않으므로 RLock 불필요. 읽기 경로(read_*)에는 걸지 않는다.
_APPEND_LOCK = threading.Lock()

# Valid approval event types
VALID_APPROVAL_EVENT_TYPES = {
    "APPROVAL_REQUESTED",
    "APPROVAL_GRANTED",
    "APPROVAL_REJECTED",
    "APPROVAL_EXPIRED",
    "APPROVAL_REVOKED",
}

# Valid approval status values
VALID_APPROVAL_STATUS = {
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "REVOKED",
}

# Mapping: approval_event_type → approval_status
EVENT_TYPE_TO_STATUS = {
    "APPROVAL_REQUESTED": "PENDING",
    "APPROVAL_GRANTED": "APPROVED",
    "APPROVAL_REJECTED": "REJECTED",
    "APPROVAL_EXPIRED": "EXPIRED",
    "APPROVAL_REVOKED": "REVOKED",
}


@dataclass
class ApprovalRecord:
    """Approval record for workflow approval event."""

    # Required: Event Identifiers
    approval_event_id: str
    approval_id: str
    workflow_run_id: str

    # Required: Workflow Context
    workflow_id: str
    action_name: str
    operation_type: str

    # Required: Approval Event
    approval_event_type: str  # APPROVAL_REQUESTED, APPROVAL_GRANTED, etc.
    approval_status: str  # PENDING, APPROVED, REJECTED, EXPIRED, REVOKED

    # Required: Approval Context
    approval_required: bool
    approval_scope: str = ""  # e.g., "click_action", "type_operation", "submit"

    # Required: Request Context
    requested_by: str = ""
    requested_role: str = ""

    # Required: Decision Context
    decided_by: str | None = None
    decided_role: str | None = None

    # Required: Business Context
    tenant_id: str = ""
    user_id: str = ""
    site_id: str = ""
    target_domain: str = ""
    target_url_hash: str = ""
    target_url_redacted: str = ""

    # Required: Reason & Metadata
    request_reason: str = ""
    decision_reason: str | None = None

    # Required: Expiration
    expires_at: str | None = None

    # Required: Timestamp
    created_at: str = ""

    # Optional: Extra Metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class ApprovalWriteResult:
    """Result of approval record write operation."""

    success: bool
    approval_event_id: str
    approval_id: str
    path: str
    event_count: int = 0
    error_message: str | None = None


def build_approval_request(  # noqa: PLR0913 - 승인 요청 빌더, 필드별 키워드 인자가 공개 API
    approval_id: str | None = None,
    workflow_run_id: str = "",
    workflow_id: str = "",
    action_name: str = "",
    operation_type: str = "",
    approval_scope: str = "",
    requested_by: str = "",
    requested_role: str = "",
    tenant_id: str = "",
    user_id: str = "",
    site_id: str = "",
    target_domain: str = "",
    target_url: str = "",
    request_reason: str = "",
    expires_in_hours: int = 24,
    metadata: dict | None = None,
) -> ApprovalRecord:
    """Build approval request record.

    Args:
        approval_id: Approval identifier (auto-generated if None)
        workflow_run_id: Workflow execution ID
        workflow_id: Workflow identifier
        action_name: Action name
        operation_type: Operation type
        approval_scope: Approval scope
        requested_by: Requester identifier
        requested_role: Requester role
        tenant_id: Tenant context
        user_id: User identifier
        site_id: Site identifier
        target_domain: Target domain
        target_url: Target URL (will be redacted)
        request_reason: Reason for request
        expires_in_hours: Expiration time in hours
        metadata: Additional metadata

    Returns:
        ApprovalRecord with APPROVAL_REQUESTED event type
    """
    if not approval_id:
        approval_id = f"appr_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    approval_event_id = f"evt_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    now_iso = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(hours=expires_in_hours)).isoformat().replace("+00:00", "Z")

    # Redact URL
    target_url_redacted, target_url_hash = _redact_url(target_url)

    return ApprovalRecord(
        approval_event_id=approval_event_id,
        approval_id=approval_id,
        workflow_run_id=workflow_run_id,
        workflow_id=workflow_id,
        action_name=action_name,
        operation_type=operation_type,
        approval_event_type="APPROVAL_REQUESTED",
        approval_status="PENDING",
        approval_required=True,
        approval_scope=approval_scope,
        requested_by=requested_by,
        requested_role=requested_role,
        decided_by=None,
        decided_role=None,
        tenant_id=tenant_id,
        user_id=user_id,
        site_id=site_id,
        target_domain=target_domain,
        target_url_hash=target_url_hash,
        target_url_redacted=target_url_redacted,
        request_reason=request_reason,
        decision_reason=None,
        expires_at=expires_at,
        created_at=now_iso,
        metadata=metadata or {},
    )


def build_approval_decision(
    approval_id: str,
    approval_event_type: str,
    decided_by: str,
    decided_role: str,
    decision_reason: str = "",
    metadata: dict | None = None,
) -> ApprovalRecord:
    """Build approval decision record (GRANTED, REJECTED, EXPIRED, REVOKED).

    Args:
        approval_id: Approval identifier
        approval_event_type: Event type (must be GRANTED/REJECTED/EXPIRED/REVOKED)
        decided_by: Decider identifier
        decided_role: Decider role
        decision_reason: Reason for decision
        metadata: Additional metadata

    Returns:
        ApprovalRecord with decision event type

    Raises:
        ValueError: If event type is invalid
    """
    if approval_event_type not in VALID_APPROVAL_EVENT_TYPES:
        raise ValueError(f"Invalid approval_event_type: {approval_event_type}")

    if approval_event_type not in ["APPROVAL_GRANTED", "APPROVAL_REJECTED", "APPROVAL_EXPIRED", "APPROVAL_REVOKED"]:
        raise ValueError(f"Decision event type must be GRANTED/REJECTED/EXPIRED/REVOKED, got {approval_event_type}")

    approval_event_id = f"evt_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    status = EVENT_TYPE_TO_STATUS[approval_event_type]

    return ApprovalRecord(
        approval_event_id=approval_event_id,
        approval_id=approval_id,
        workflow_run_id="",
        workflow_id="",
        action_name="",
        operation_type="",
        approval_event_type=approval_event_type,
        approval_status=status,
        approval_required=True,
        decided_by=decided_by,
        decided_role=decided_role,
        decision_reason=decision_reason,
        created_at=now,
        metadata=metadata or {},
    )


def _redact_url(url: str) -> tuple[str, str]:
    """Redact sensitive query parameters from URL.

    Args:
        url: Original URL

    Returns:
        Tuple of (redacted_url, url_hash)
    """
    if not url:
        return "", ""

    try:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        # Redact sensitive params
        redacted_params = {}
        for key, values in query_params.items():
            if key.lower() in {
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
            }:
                redacted_params[key] = ["[REDACTED]"]
            else:
                redacted_params[key] = values

        # Reconstruct URL
        redacted_query = urlencode(redacted_params, doseq=True)
        redacted_parsed = parsed._replace(query=redacted_query)
        redacted_url = urlunparse(redacted_parsed)

        # Generate hash
        url_hash = hashlib.sha256(redacted_url.encode()).hexdigest()
        return redacted_url, url_hash

    except Exception:  # noqa: BLE001 - URL 리다크션 실패 시 원본 대신 [REDACTED_URL] 플레이스홀더와 해시만 반환 — fail-safe, 원본 URL 노출 없음
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return "[REDACTED_URL]", url_hash


def _validate_event_type_and_status(record: ApprovalRecord) -> list[str]:
    """approval_event_type / approval_status 필수·허용값 검증 (오류 순서 유지)."""
    errors: list[str] = []
    if not record.approval_event_type:
        errors.append("approval_event_type is required")
    elif record.approval_event_type not in VALID_APPROVAL_EVENT_TYPES:
        errors.append(
            f"approval_event_type must be one of {VALID_APPROVAL_EVENT_TYPES}, got {record.approval_event_type}"
        )

    if not record.approval_status:
        errors.append("approval_status is required")
    elif record.approval_status not in VALID_APPROVAL_STATUS:
        errors.append(f"approval_status must be one of {VALID_APPROVAL_STATUS}, got {record.approval_status}")
    return errors


def validate_approval_record(record: ApprovalRecord) -> list[str]:
    """Validate approval record.

    Args:
        record: Approval record to validate

    Returns:
        List of error messages (empty list = valid)
    """
    errors = []

    # Required fields
    if not record.approval_event_id:
        errors.append("approval_event_id is required")
    if not record.approval_id:
        errors.append("approval_id is required")
    errors.extend(_validate_event_type_and_status(record))

    # Timestamp
    if not record.created_at:
        errors.append("created_at is required")

    # Event type → Status mapping
    expected_status = EVENT_TYPE_TO_STATUS.get(record.approval_event_type)
    if expected_status and record.approval_status != expected_status:
        errors.append(
            f"approval_event_type {record.approval_event_type} must have status {expected_status}, got {record.approval_status}"
        )

    # Decision fields validation
    if record.approval_event_type in ["APPROVAL_GRANTED", "APPROVAL_REJECTED", "APPROVAL_REVOKED"]:
        if not record.decided_by:
            errors.append(f"{record.approval_event_type} requires decided_by")

    return errors


def append_approval_record(
    record: ApprovalRecord,
    jsonl_path: Path | str,
) -> ApprovalWriteResult:
    """Append approval record to JSONL file (append-only, no overwrite).

    Args:
        record: Approval record to append
        jsonl_path: Path to JSONL file

    Returns:
        ApprovalWriteResult with success status

    Raises:
        ValueError: If record validation fails
        IOError: If write fails
    """
    jsonl_path = Path(jsonl_path)

    # Validate
    errors = validate_approval_record(record)
    if errors:
        return ApprovalWriteResult(
            success=False,
            approval_event_id=record.approval_event_id,
            approval_id=record.approval_id,
            path=str(jsonl_path),
            error_message=f"Validation failed: {'; '.join(errors)}",
        )

    with _APPEND_LOCK:
        return _append_unlocked(record, jsonl_path)


class ApprovalTransitionError(Exception):
    """승인 결정 기록이 현재 상태와 맞지 않을 때(미존재/이미 종결). status_code 는 404 또는 409."""

    def __init__(self, status_code: int, detail: str, current_status: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.current_status = current_status


def append_decision_if_pending(
    record: ApprovalRecord,
    jsonl_path: Path | str,
) -> ApprovalWriteResult:
    """현재 상태가 PENDING 일 때만 결정 기록을 append (검사+append 를 같은 락 구간에서 원자적으로).

    Raises:
        ApprovalTransitionError: 기록이 전혀 없으면 404, 이미 PENDING 이 아니면 409
    """
    jsonl_path = Path(jsonl_path)
    errors = validate_approval_record(record)
    if errors:
        return ApprovalWriteResult(
            success=False,
            approval_event_id=record.approval_event_id,
            approval_id=record.approval_id,
            path=str(jsonl_path),
            error_message=f"Validation failed: {'; '.join(errors)}",
        )
    with _APPEND_LOCK:
        try:
            latest = get_latest_approval_status(record.approval_id, jsonl_path)
        except FileNotFoundError:
            latest = None
        if latest is None:
            raise ApprovalTransitionError(404, "Approval not found")
        current = latest.get("approval_status", "")
        if current != "PENDING":
            raise ApprovalTransitionError(409, f"Approval already {current}", current)
        return _append_unlocked(record, jsonl_path)


def _append_unlocked(record: ApprovalRecord, jsonl_path: Path) -> ApprovalWriteResult:
    """락을 이미 잡은 상태에서 한 줄 append + 줄 수 계산 (호출자가 _APPEND_LOCK 보유)."""
    try:
        json_line = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True)
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json_line + "\n")

        event_count = 0
        if jsonl_path.exists():
            with jsonl_path.open(encoding="utf-8") as f:
                event_count = sum(1 for line in f if line.strip())

        return ApprovalWriteResult(
            success=True,
            approval_event_id=record.approval_event_id,
            approval_id=record.approval_id,
            path=str(jsonl_path),
            event_count=event_count,
            error_message=None,
        )

    except OSError as e:
        return ApprovalWriteResult(
            success=False,
            approval_event_id=record.approval_event_id,
            approval_id=record.approval_id,
            path=str(jsonl_path),
            error_message=f"Write failed: {e!s}",
        )


def read_jsonl_records(jsonl_path: Path | str, kind: str) -> list[dict]:
    """JSONL 파일의 모든 기록을 dict 목록으로 읽는다(빈 줄은 건너뜀). kind 는 오류 문구의 기록 종류.

    read_approval_records 와 workflow_audit_writer.read_audit_records 가 오류 문구만 다르게 똑같이
    복사해 쓰던 본문을 여기 한 곳으로 모았다(L7 저장 모듈 — L6 workflow_audit_writer 가 import).

    Raises:
        FileNotFoundError: 파일이 없으면 — f"{kind} file not found: {path}"
        ValueError: JSON 이 아닌 줄이 있으면 — f"Invalid JSON at line {n}: {e}"
    """
    jsonl_path = Path(jsonl_path)

    if not jsonl_path.exists():
        raise FileNotFoundError(f"{kind} file not found: {jsonl_path}")

    records = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_num}: {e}") from e

    return records


def read_approval_records(jsonl_path: Path | str) -> list[dict]:
    """Read all approval records from JSONL file.

    Args:
        jsonl_path: Path to JSONL file

    Returns:
        List of record dicts

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If any line is not valid JSON
    """
    return read_jsonl_records(jsonl_path, "Approval")


def get_approval_history(
    approval_id: str,
    jsonl_path: Path | str,
) -> list[dict]:
    """Get approval event history for a specific approval_id.

    Args:
        approval_id: Approval identifier
        jsonl_path: Path to JSONL file

    Returns:
        List of events for this approval_id (in order of creation)

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    all_records = read_approval_records(jsonl_path)
    return [r for r in all_records if r.get("approval_id") == approval_id]


def get_latest_approval_status(
    approval_id: str,
    jsonl_path: Path | str,
) -> dict | None:
    """Get latest approval status for a specific approval_id.

    Args:
        approval_id: Approval identifier
        jsonl_path: Path to JSONL file

    Returns:
        Latest approval event record, or None if not found

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    history = get_approval_history(approval_id, jsonl_path)
    return history[-1] if history else None


def build_audit_approval_context(
    approval_id: str,
    jsonl_path: Path | str,
) -> dict:
    """Build approval context for audit record.

    Args:
        approval_id: Approval identifier
        jsonl_path: Path to JSONL file

    Returns:
        Dict with approval_id and current approval_status
        (empty dict if approval not found)

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    latest = get_latest_approval_status(approval_id, jsonl_path)
    if not latest:
        return {}

    return {
        "approval_id": latest.get("approval_id"),
        "approval_status": latest.get("approval_status"),
        "approval_event_type": latest.get("approval_event_type"),
        "decided_by": latest.get("decided_by"),
        "created_at": latest.get("created_at"),
    }
