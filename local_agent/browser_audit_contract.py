"""Browser task audit event contract (BROWSER-AUDIT-1).

Defines the safe event contract for browser approval/execution lifecycle audit.
Forward-compatible with future LOG-2B app_audit_log 22-column schema.
Backward-compatible with existing JSONL audit_logger.

Security invariants:
- approval_token / final_approval_token / token_hash NEVER stored
- typed_text / password / OTP / cookie / session / authorization NEVER stored
- localStorage / sessionStorage / raw_screenshot / base64 NEVER stored
- full DOM / request_headers / raw exception stack trace NEVER stored
- payload_hash computed over SANITIZED payload only

Lifecycle event types (browser.*):
- task.received               (PASS — task accepted)
- task.validation_failed      (WARN — schema invalid)
- approval.requested          (PASS — UI approval prompt sent)
- approval.approved           (PASS — admin approved)
- approval.rejected           (SKIP — admin rejected)
- approval.expired            (WARN — approval window passed)
- approval.used               (PASS — approval consumed)
- task.blocked                (WARN — risky action / approval invalid)
- task.executed               (PASS — action executed)
- task.failed                 (FAIL — execution error)
- result.callback_built       (PASS — safe callback emitted to bridge)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class BrowserAuditEventType(str, Enum):
    TASK_RECEIVED = "browser.task.received"
    TASK_VALIDATION_FAILED = "browser.task.validation_failed"
    APPROVAL_REQUESTED = "browser.approval.requested"
    APPROVAL_APPROVED = "browser.approval.approved"
    APPROVAL_REJECTED = "browser.approval.rejected"
    APPROVAL_EXPIRED = "browser.approval.expired"
    APPROVAL_USED = "browser.approval.used"
    TASK_BLOCKED = "browser.task.blocked"
    TASK_EXECUTED = "browser.task.executed"
    TASK_FAILED = "browser.task.failed"
    RESULT_CALLBACK_BUILT = "browser.result.callback_built"


class BrowserAuditStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - 판정 결과 라벨(비밀번호 아님)
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


# Status mapping per instruction (BROWSER-AUDIT-1, section 5)
_EVENT_TYPE_STATUS: dict[BrowserAuditEventType, BrowserAuditStatus] = {
    BrowserAuditEventType.TASK_RECEIVED: BrowserAuditStatus.PASS,
    BrowserAuditEventType.APPROVAL_REQUESTED: BrowserAuditStatus.PASS,
    BrowserAuditEventType.APPROVAL_APPROVED: BrowserAuditStatus.PASS,
    BrowserAuditEventType.APPROVAL_USED: BrowserAuditStatus.PASS,
    BrowserAuditEventType.TASK_EXECUTED: BrowserAuditStatus.PASS,
    BrowserAuditEventType.RESULT_CALLBACK_BUILT: BrowserAuditStatus.PASS,
    BrowserAuditEventType.TASK_VALIDATION_FAILED: BrowserAuditStatus.WARN,
    BrowserAuditEventType.TASK_BLOCKED: BrowserAuditStatus.WARN,
    BrowserAuditEventType.APPROVAL_EXPIRED: BrowserAuditStatus.WARN,
    BrowserAuditEventType.APPROVAL_REJECTED: BrowserAuditStatus.SKIP,
    BrowserAuditEventType.TASK_FAILED: BrowserAuditStatus.FAIL,
}


def status_for_event(event_type: BrowserAuditEventType) -> BrowserAuditStatus:
    return _EVENT_TYPE_STATUS.get(event_type, BrowserAuditStatus.ERROR)


# ---------------------------------------------------------------------------
# Forbidden fields (defense-in-depth)
# ---------------------------------------------------------------------------

# Fields that MUST never appear in audit metadata, payload_hash input, or message
FORBIDDEN_AUDIT_FIELDS: frozenset[str] = frozenset(
    {
        # Token material
        "approval_token",
        "final_approval_token",
        "token_hash",
        "device_token",
        "raw_token",
        "secret",
        # User input / credentials
        "typed_text",
        "password",
        "otp",
        "credential",
        # HTTP / browser state
        "cookie",
        "cookies",
        "session",
        "session_id",
        "authorization",
        "auth",
        "headers",
        "request_headers",
        "browser_storage",
        "localstorage",
        "sessionstorage",
        # Visual / DOM
        "raw_screenshot",
        "screenshot_data",
        "screenshot_b64",
        "base64",
        "full_dom",
        "raw_dom",
        "html",
        # Internal exception detail
        "stack_trace",
        "stacktrace",
        "traceback",
        "raw_exception",
    }
)


# Allowed metadata fields per BROWSER-AUDIT-1 §2
_ALLOWED_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "task_id",
        "action_type",
        "selector",
        "selector_hash",
        "risk_level",
        "final_approval_required",
        "executed",
        "result",
        "target_url_domain",
        "text_length",
        "text_preview",  # text_preview MUST be "[REDACTED]"
        "screenshot_taken",
        "screenshot_ref",
        "approval_id",
        "approval_status",
        "store_type",
        "bridge_status",
    }
)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class BrowserAuditMetadata:
    """Safe metadata payload — keys constrained to _ALLOWED_METADATA_FIELDS."""

    task_id: str | None = None
    action_type: str | None = None
    selector: str | None = None
    selector_hash: str | None = None
    risk_level: str | None = None
    final_approval_required: bool | None = None
    executed: bool | None = None
    result: str | None = None
    target_url_domain: str | None = None
    text_length: int | None = None
    text_preview: str = "[REDACTED]"
    screenshot_taken: bool | None = None
    screenshot_ref: str | None = None
    approval_id: str | None = None
    approval_status: str | None = None
    store_type: str | None = None
    bridge_status: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        """Return dict with only allowed, non-None fields. text_preview always REDACTED."""
        raw = asdict(self)
        out = {k: v for k, v in raw.items() if k in _ALLOWED_METADATA_FIELDS and v is not None}
        # text_preview hard-fixed
        if "text_preview" in out:
            out["text_preview"] = "[REDACTED]"
        return out


def sanitize_browser_audit_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip forbidden keys (case-insensitive) and unknown keys.

    Returns only the intersection of (input keys) ∩ _ALLOWED_METADATA_FIELDS,
    minus anything that case-insensitively matches FORBIDDEN_AUDIT_FIELDS.
    text_preview is always coerced to '[REDACTED]'.
    """
    if not isinstance(raw, dict):
        return {}
    forbidden_lower = {f.lower() for f in FORBIDDEN_AUDIT_FIELDS}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        kl = k.lower()
        if kl in forbidden_lower:
            continue
        if k not in _ALLOWED_METADATA_FIELDS:
            continue
        if v is None:
            continue
        out[k] = v
    if "text_preview" in out:
        out["text_preview"] = "[REDACTED]"
    return out


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def hash_safe_payload(payload: Any) -> str:
    """SHA256 over canonical JSON of a SANITIZED payload.

    Caller MUST pass already-sanitized data. This function will additionally
    drop top-level forbidden keys as defense-in-depth, but does not deep-walk.
    """
    if isinstance(payload, dict):
        forbidden_lower = {f.lower() for f in FORBIDDEN_AUDIT_FIELDS}
        clean = {k: v for k, v in payload.items() if k.lower() not in forbidden_lower}
    else:
        clean = payload
    blob = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def hash_event(event_dict: dict[str, Any], previous_event_hash: str | None = None) -> str:
    """SHA256 chaining hash for audit row integrity."""
    canonical = json.dumps(event_dict, sort_keys=True, ensure_ascii=False, default=str)
    chained = (previous_event_hash or "") + "|" + canonical
    return hashlib.sha256(chained.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# BrowserAuditEvent — forward-compatible with LOG-2B 22-column schema
# ---------------------------------------------------------------------------

# Required columns that any LOG-2B-compatible writer must consume
REQUIRED_AUDIT_COLUMNS: frozenset[str] = frozenset(
    {
        "event_type",
        "event_at",
        "actor_user_id",
        "actor_role",
        "organization_id",
        "target_type",
        "target_id",
        "request_id",
        "status",
        "error_code",
        "error_message",
        "elapsed_ms",
        "payload_hash",
        "metadata_json",
    }
)


@dataclass
class BrowserAuditEvent:
    """Audit event row (forward-compatible with app_audit_log 22-column schema).

    All sensitive fields are scrubbed before construction by the build_*
    factories. Direct construction with unsafe data is the caller's
    responsibility — prefer the factories.
    """

    event_type: str
    event_at: str = ""
    status: str = BrowserAuditStatus.PASS.value
    actor_user_id: str | None = None
    actor_role: str | None = None
    organization_id: str | None = None
    target_type: str = "browser_task"
    target_id: str | None = None
    request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    payload_hash: str | None = None
    prompt_hash: str | None = None  # always None for browser
    response_hash: str | None = None  # always None for browser
    event_hash: str | None = None
    previous_event_hash: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    # Forward-compat columns (schema headroom for LOG-2B 22-column target)
    log_version: str = "browser-audit-1"
    source: str = "local_agent.browser"
    environment: str = "local"

    def to_audit_row(self) -> dict[str, Any]:
        """Convert to dict suitable for app_audit_log INSERT or JSONL append.

        Defensive: strips any forbidden top-level keys that may have leaked in.
        """
        raw = asdict(self)
        forbidden_lower = {f.lower() for f in FORBIDDEN_AUDIT_FIELDS}
        clean = {k: v for k, v in raw.items() if k.lower() not in forbidden_lower}
        # metadata_json must also be scrubbed
        meta = clean.get("metadata_json") or {}
        clean["metadata_json"] = sanitize_browser_audit_metadata(meta)
        return clean


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_browser_task_audit_event(  # noqa: PLR0913 - 공개 keyword-only 감사 이벤트 빌더, 시그니처 유지
    *,
    event_type: BrowserAuditEventType,
    task_id: str,
    action_type: str = "",
    selector: str = "",
    risk_level: str = "low",
    final_approval_required: bool = False,
    executed: bool = False,
    result: str = "",
    target_url_domain: str = "",
    text_length: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
    elapsed_ms: int | None = None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    organization_id: str | None = None,
    request_id: str | None = None,
    approval_id: str | None = None,
    approval_status: str | None = None,
    store_type: str | None = None,
    bridge_status: str | None = None,
    screenshot_taken: bool = False,
    screenshot_ref: str | None = None,
    previous_event_hash: str | None = None,
) -> BrowserAuditEvent:
    """Factory for browser task lifecycle events."""
    metadata = sanitize_browser_audit_metadata(
        {
            "task_id": task_id,
            "action_type": action_type,
            "selector": selector,
            "risk_level": risk_level,
            "final_approval_required": final_approval_required,
            "executed": executed,
            "result": result,
            "target_url_domain": target_url_domain,
            "text_length": text_length,
            "text_preview": "[REDACTED]",
            "screenshot_taken": screenshot_taken,
            "screenshot_ref": screenshot_ref,
            "approval_id": approval_id,
            "approval_status": approval_status,
            "store_type": store_type,
            "bridge_status": bridge_status,
        }
    )
    payload_hash = hash_safe_payload(metadata)

    event = BrowserAuditEvent(
        event_type=event_type.value,
        event_at=_now_iso(),
        status=status_for_event(event_type).value,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        organization_id=organization_id,
        target_type="browser_task",
        target_id=task_id,
        request_id=request_id,
        error_code=error_code,
        error_message=_safe_error_summary(error_message),
        elapsed_ms=elapsed_ms,
        payload_hash=payload_hash,
        previous_event_hash=previous_event_hash,
        metadata_json=metadata,
    )
    # Compute event_hash over the row sans event_hash itself
    row = event.to_audit_row()
    row.pop("event_hash", None)
    event.event_hash = hash_event(row, previous_event_hash)
    return event


def build_browser_approval_audit_event(  # noqa: PLR0913 - 공개 keyword-only 감사 이벤트 빌더, 시그니처 유지
    *,
    event_type: BrowserAuditEventType,
    approval_id: str,
    task_id: str,
    action_type: str,
    selector: str,
    risk_level: str = "low",
    approval_status: str = "approved",
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    organization_id: str | None = None,
    request_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    previous_event_hash: str | None = None,
) -> BrowserAuditEvent:
    """Factory for approval lifecycle events (requested/approved/rejected/expired/used)."""
    return build_browser_task_audit_event(
        event_type=event_type,
        task_id=task_id,
        action_type=action_type,
        selector=selector,
        risk_level=risk_level,
        approval_id=approval_id,
        approval_status=approval_status,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        organization_id=organization_id,
        request_id=request_id,
        error_code=error_code,
        error_message=error_message,
        previous_event_hash=previous_event_hash,
    )


def build_browser_result_audit_event(  # noqa: PLR0913 - 공개 keyword-only 감사 이벤트 빌더, 시그니처 유지
    *,
    task_result: Any,
    bridge_status: str = "callback_built",
    request_id: str | None = None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    organization_id: str | None = None,
    elapsed_ms: int | None = None,
    previous_event_hash: str | None = None,
) -> BrowserAuditEvent:
    """Factory for terminal result events from a BrowserTaskResult.

    Maps result.status → event_type:
        executed       → TASK_EXECUTED
        blocked        → TASK_BLOCKED
        failed         → TASK_FAILED
        any other      → RESULT_CALLBACK_BUILT
    """
    status = getattr(task_result, "status", "")
    mapping = {
        "executed": BrowserAuditEventType.TASK_EXECUTED,
        "blocked": BrowserAuditEventType.TASK_BLOCKED,
        "failed": BrowserAuditEventType.TASK_FAILED,
    }
    event_type = mapping.get(status, BrowserAuditEventType.RESULT_CALLBACK_BUILT)
    return build_browser_task_audit_event(
        event_type=event_type,
        task_id=getattr(task_result, "task_id", "unknown"),
        action_type=getattr(task_result, "action", ""),
        selector=getattr(task_result, "selector", ""),
        risk_level=getattr(task_result, "risk_level", "low"),
        final_approval_required=getattr(task_result, "final_approval_required", False),
        executed=getattr(task_result, "executed", False),
        result=getattr(task_result, "result", ""),
        target_url_domain=getattr(task_result, "target_url_domain", ""),
        text_length=getattr(task_result, "text_length", 0),
        error_code=getattr(task_result, "error_code", None),
        error_message=getattr(task_result, "error_message", None),
        elapsed_ms=elapsed_ms,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        organization_id=organization_id,
        request_id=request_id,
        bridge_status=bridge_status,
        previous_event_hash=previous_event_hash,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_error_summary(message: str | None) -> str | None:
    """Return a short, secret-stripped error summary or None.

    Caller-supplied error_message may contain sensitive data — we drop any
    line whose lowercase text contains a forbidden field name, and truncate
    to 200 chars. Stack traces (long multiline) are summarized to first line.
    """
    if not message:
        return None
    forbidden_lower = {f.lower() for f in FORBIDDEN_AUDIT_FIELDS}
    first = str(message).splitlines()[0]
    lower = first.lower()
    if any(f in lower for f in forbidden_lower):
        return "[REDACTED]"
    return first[:200]


# ---------------------------------------------------------------------------
# Mock writer (for tests / local validation)
# ---------------------------------------------------------------------------


class MockAuditWriter:
    """Collects BrowserAuditEvent rows and validates safety invariants.

    Used to prove that an audit event is safely emit-able to ANY downstream
    writer (JSONL or future app_audit_log INSERT).
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self._previous_event_hash: str | None = None

    def write(self, event: BrowserAuditEvent) -> dict[str, Any]:
        row = event.to_audit_row()
        # Defensive secret check — abort if any forbidden key slipped through
        self._assert_no_secrets(row)
        # Required-column check (for LOG-2B compat)
        for col in REQUIRED_AUDIT_COLUMNS:
            if col not in row:
                raise ValueError(f"required audit column missing: {col}")
        self.records.append(row)
        self._previous_event_hash = event.event_hash
        return row

    def last(self) -> dict[str, Any] | None:
        return self.records[-1] if self.records else None

    def previous_event_hash(self) -> str | None:
        return self._previous_event_hash

    def assert_no_secrets(self) -> None:
        for r in self.records:
            self._assert_no_secrets(r)

    @classmethod
    def _assert_no_secrets(cls, value: Any) -> None:
        forbidden_lower = {f.lower() for f in FORBIDDEN_AUDIT_FIELDS}
        if isinstance(value, dict):
            for k, v in value.items():
                if k.lower() in forbidden_lower:
                    raise ValueError(f"forbidden field present in audit row: {k}")
                cls._assert_no_secrets(v)
        elif isinstance(value, list):
            for item in value:
                cls._assert_no_secrets(item)


__all__ = [
    "FORBIDDEN_AUDIT_FIELDS",
    "REQUIRED_AUDIT_COLUMNS",
    "BrowserAuditEvent",
    "BrowserAuditEventType",
    "BrowserAuditMetadata",
    "BrowserAuditStatus",
    "MockAuditWriter",
    "build_browser_approval_audit_event",
    "build_browser_result_audit_event",
    "build_browser_task_audit_event",
    "hash_event",
    "hash_safe_payload",
    "sanitize_browser_audit_metadata",
    "status_for_event",
]
