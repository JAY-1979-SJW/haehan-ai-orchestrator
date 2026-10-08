"""Server-owned user data contribution consent and safe export gate."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

STATUS_ACTIVE = "ACTIVE"
STATUS_REVOKED = "REVOKED"
STATUS_EXPIRED = "EXPIRED"

PURPOSE_PRODUCT_IMPROVEMENT = "product_improvement"
PURPOSE_MODEL_TRAINING = "model_training"
PURPOSE_BENCHMARK_CREATION = "benchmark_creation"
PURPOSE_QUALITY_ANALYSIS = "quality_analysis"
PURPOSE_FEATURE_PLANNING = "feature_planning"

ALLOWED_PURPOSES: frozenset[str] = frozenset({
    PURPOSE_PRODUCT_IMPROVEMENT,
    PURPOSE_MODEL_TRAINING,
    PURPOSE_BENCHMARK_CREATION,
    PURPOSE_QUALITY_ANALYSIS,
    PURPOSE_FEATURE_PLANNING,
})

CATEGORY_TASK_CATEGORY = "task_category"
CATEGORY_TOOL_ID_OR_MODULE = "tool_id_or_module"
CATEGORY_SAFE_USER_INTENT_SUMMARY = "safe_user_intent_summary"
CATEGORY_SAFE_RESULT_SUMMARY = "safe_result_summary"
CATEGORY_ERROR_CODE = "error_code"
CATEGORY_STATE_TRANSITION = "state_transition"
CATEGORY_VERIFICATION_REFERENCE = "verification_reference"
CATEGORY_USER_FEEDBACK = "user_feedback"
CATEGORY_MASKED_USER_REFERENCE = "masked_user_reference"
CATEGORY_MASKED_ORGANIZATION_REFERENCE = "masked_organization_reference"

ALLOWED_DATA_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_TASK_CATEGORY,
    CATEGORY_TOOL_ID_OR_MODULE,
    CATEGORY_SAFE_USER_INTENT_SUMMARY,
    CATEGORY_SAFE_RESULT_SUMMARY,
    CATEGORY_ERROR_CODE,
    CATEGORY_STATE_TRANSITION,
    CATEGORY_VERIFICATION_REFERENCE,
    CATEGORY_USER_FEEDBACK,
    CATEGORY_MASKED_USER_REFERENCE,
    CATEGORY_MASKED_ORGANIZATION_REFERENCE,
})

FORBIDDEN_DEVELOPMENT_FIELDS: frozenset[str] = frozenset({
    "raw_user_prompt",
    "raw_prompt",
    "prompt",
    "raw_file",
    "raw_files",
    "file_content",
    "file_bytes",
    "raw_page_content",
    "page_content",
    "page_html",
    "raw_screenshot",
    "screenshot",
    "email_body",
    "raw_email",
    "document_body",
    "raw_document",
    "browser_trace",
    "raw_browser_trace",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "password",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "cookies",
    "session",
    "auth_header",
    "Authorization",
    "sensitive_personal_data",
    "third_party_content",
})

_STORE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_DEFAULT_AUDIT_DIR = data_dir() / "audit"
_CONSENT_LOG_PATH = _DEFAULT_AUDIT_DIR / "user_data_contribution_consents.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_set(values: list[str] | tuple[str, ...] | set[str] | frozenset[str]) -> set[str]:
    return {str(v).strip() for v in values if str(v).strip()}


def _validate_subset(values: set[str], allowed: frozenset[str], label: str) -> list[str]:
    unknown = sorted(values - set(allowed))
    return [f"unknown {label}: {v}" for v in unknown]


def _append_event(event: dict[str, Any]) -> None:
    """Append a redacted consent lifecycle event to durable JSONL storage."""
    try:
        _CONSENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CONSENT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def reload_store_from_disk() -> int:
    """Rebuild in-memory consent state from append-only JSONL events."""
    loaded: dict[str, dict[str, Any]] = {}
    if not _CONSENT_LOG_PATH.exists():
        with _LOCK:
            _STORE.clear()
        return 0

    try:
        lines = _CONSENT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0

    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("_type")
        record = event.get("record")
        if not isinstance(record, dict):
            continue
        consent_id = str(record.get("consent_id") or "")
        if not consent_id:
            continue
        if event_type in {"consent_granted", "consent_revoked"}:
            loaded[consent_id] = dict(record)

    with _LOCK:
        _STORE.clear()
        _STORE.update(loaded)
    return len(loaded)


def _walk_forbidden_keys(value: Any, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_DEVELOPMENT_FIELDS:
                violations.append(f"forbidden development field: {next_path}")
            lower_key = key_text.lower()
            if lower_key.startswith("raw_"):
                violations.append(f"raw development field: {next_path}")
            for marker in ("password", "cookie", "session", "token", "secret"):
                if marker in lower_key and key_text not in ALLOWED_DATA_CATEGORIES:
                    violations.append(f"sensitive development field pattern: {next_path}")
                    break
            violations.extend(_walk_forbidden_keys(child, next_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_walk_forbidden_keys(child, f"{path}[{index}]"))
    return violations


def grant_consent(
    *,
    user_reference: str,
    organization_reference: str = "",
    purposes: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    data_categories: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    retention_days: int = 365,
    source: str = "server",
) -> dict[str, Any]:
    """Record explicit server-owned consent for development data contribution."""
    purpose_set = _normalize_set(purposes)
    category_set = _normalize_set(data_categories)
    violations: list[str] = []
    if not user_reference:
        violations.append("user_reference is required")
    if not purpose_set:
        violations.append("at least one purpose is required")
    if not category_set:
        violations.append("at least one data category is required")
    violations.extend(_validate_subset(purpose_set, ALLOWED_PURPOSES, "purpose"))
    violations.extend(_validate_subset(category_set, ALLOWED_DATA_CATEGORIES, "data category"))
    if retention_days < 1 or retention_days > 3650:
        violations.append("retention_days must be between 1 and 3650")
    if violations:
        raise ValueError("; ".join(violations))

    created_at = _now()
    consent_id = str(uuid.uuid4())
    record = {
        "consent_id": consent_id,
        "status": STATUS_ACTIVE,
        "user_reference": user_reference,
        "organization_reference": organization_reference,
        "purposes": sorted(purpose_set),
        "data_categories": sorted(category_set),
        "retention_days": retention_days,
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(days=retention_days)).isoformat(),
        "revoked_at": None,
        "source": source,
    }
    with _LOCK:
        _STORE[consent_id] = record
    _append_event({"_type": "consent_granted", "record": record})
    return dict(record)


def revoke_consent(consent_id: str) -> dict[str, Any] | None:
    """Revoke a consent record without deleting the audit-relevant fact."""
    with _LOCK:
        record = _STORE.get(consent_id)
        if not record:
            return None
        record["status"] = STATUS_REVOKED
        record["revoked_at"] = _now_iso()
        snapshot = dict(record)
    _append_event({"_type": "consent_revoked", "record": snapshot})
    return snapshot


def get_consent(consent_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _STORE.get(consent_id)
    return dict(record) if record else None


def list_consents(user_reference: str = "", status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        records = list(_STORE.values())
    if user_reference:
        records = [r for r in records if r.get("user_reference") == user_reference]
    if status:
        records = [r for r in records if r.get("status") == status]
    return [dict(r) for r in records[: max(1, min(limit, 500))]]


def find_active_consent(
    *,
    user_reference: str,
    purpose: str,
    required_categories: set[str],
) -> dict[str, Any] | None:
    """Return an active consent covering the requested purpose and categories."""
    now = _now()
    with _LOCK:
        records = list(_STORE.values())
    for record in records:
        if record.get("user_reference") != user_reference:
            continue
        if record.get("status") != STATUS_ACTIVE:
            continue
        expires_at = _parse_iso(str(record.get("expires_at") or ""))
        if expires_at and expires_at < now:
            continue
        if purpose not in set(record.get("purposes") or []):
            continue
        if not required_categories.issubset(set(record.get("data_categories") or [])):
            continue
        return dict(record)
    return None


def export_development_material(
    *,
    user_reference: str,
    purpose: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a consent-gated, minimized development dataset."""
    if purpose not in ALLOWED_PURPOSES:
        return {
            "accepted": False,
            "blocked_reason": [f"unknown purpose: {purpose}"],
            "materials": [],
            "consent_id": None,
        }
    violations = _walk_forbidden_keys(records)
    if violations:
        return {
            "accepted": False,
            "blocked_reason": violations,
            "materials": [],
            "consent_id": None,
        }

    materials: list[dict[str, Any]] = []
    required_categories: set[str] = set()
    for record in records:
        safe_record = {
            key: value
            for key, value in record.items()
            if key in ALLOWED_DATA_CATEGORIES
        }
        required_categories.update(safe_record.keys())
        materials.append(safe_record)

    consent = find_active_consent(
        user_reference=user_reference,
        purpose=purpose,
        required_categories=required_categories,
    )
    if consent is None:
        return {
            "accepted": False,
            "blocked_reason": ["missing active consent for requested purpose and categories"],
            "materials": [],
            "consent_id": None,
        }

    return {
        "accepted": True,
        "blocked_reason": None,
        "materials": materials,
        "consent_id": consent["consent_id"],
        "purpose": purpose,
        "record_count": len(materials),
    }


def clear_store() -> None:
    with _LOCK:
        _STORE.clear()
