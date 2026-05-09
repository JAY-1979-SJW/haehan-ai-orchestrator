"""
Action Evidence Store

실제 실행 결과(evidence)를 safe field만 저장한다.

저장 금지:
- cookie / session / storage_state
- password / otp / cert_password / private_key
- raw browser storage
- 실제 파일 내용 (경로 ref만 허용)
- localStorage / sessionStorage
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 금지 필드 ─────────────────────────────────────────────────────────────────

FORBIDDEN_EVIDENCE_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "storage_state",
    "password", "otp", "cert_password", "certificate_password",
    "private_key", "npki", "auth_header", "Authorization",
    "token", "access_token", "refresh_token",
    "localStorage", "sessionStorage",
    "raw_browser_storage", "browser_storage",
    "npki_data", "auth_token",
    "certificate_file_path",
})

# 파일 ref만 허용 (실제 내용 금지)
_FORBIDDEN_FILE_CONTENT_KEYS: frozenset[str] = frozenset({
    "file_content", "file_bytes", "file_data",
    "attachment_content", "attachment_bytes",
})

# ── in-memory + JSONL ─────────────────────────────────────────────────────────

_STORE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

_DEFAULT_AUDIT_DIR = Path(__file__).parent.parent.parent / "data" / "audit"
_EVIDENCE_FILE_NAME = "action_evidence.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_path() -> Path:
    p = _DEFAULT_AUDIT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / _EVIDENCE_FILE_NAME


def _append_jsonl(record: dict[str, Any]) -> None:
    try:
        with _evidence_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def validate_evidence_fields(result_fields: dict[str, Any]) -> list[str]:
    """
    evidence 필드 유효성 검사.
    금지 필드 포함 시 위반 목록 반환.
    """
    violations: list[str] = []
    for k in result_fields:
        if k in FORBIDDEN_EVIDENCE_FIELDS:
            violations.append(f"금지 필드: {k!r}")
        if k in _FORBIDDEN_FILE_CONTENT_KEYS:
            violations.append(f"파일 내용 직접 저장 금지: {k!r}")
        kl = k.lower()
        for banned in ("cookie", "session", "password", "otp", "token", "storage"):
            if banned in kl and k not in ("result_status", "action_name", "local_agent_run_id"):
                if k not in violations:
                    violations.append(f"민감 키 패턴 포함: {k!r}")
                break
    return violations


def save_evidence(
    *,
    action_name: str,
    approval_request_id: str,
    params_hash: str,
    result_status: str,
    result_fields_safe: dict[str, Any],
    evidence_files_ref: list[str] | None = None,
    local_agent_run_id: str = "",
    occurred_at: str = "",
) -> dict[str, Any]:
    """
    실행 evidence를 저장한다.

    result_fields_safe는 호출자가 민감 필드를 제거한 값만 전달해야 한다.
    저장 전 validate_evidence_fields로 이중 검증한다.
    """
    violations = validate_evidence_fields(result_fields_safe)
    if violations:
        raise ValueError(f"evidence 금지 필드 포함: {violations}")

    evidence_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "evidence_id": evidence_id,
        "action_name": action_name,
        "approval_request_id": approval_request_id,
        "params_hash": params_hash,
        "result_status": result_status,
        "result_fields_safe": dict(result_fields_safe),
        "evidence_files_ref": list(evidence_files_ref or []),
        "local_agent_run_id": local_agent_run_id,
        "occurred_at": occurred_at or _now_iso(),
        "stored_at": _now_iso(),
    }

    with _LOCK:
        _STORE[evidence_id] = record
    _append_jsonl({"_type": "evidence", **record})
    return dict(record)


def get_evidence(evidence_id: str) -> dict[str, Any] | None:
    """evidence 조회."""
    with _LOCK:
        record = _STORE.get(evidence_id)
    return dict(record) if record else None


def list_evidence(
    approval_request_id: str | None = None,
    action_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """evidence 목록 조회."""
    with _LOCK:
        records = list(_STORE.values())
    if approval_request_id:
        records = [r for r in records if r.get("approval_request_id") == approval_request_id]
    if action_name:
        records = [r for r in records if r.get("action_name") == action_name]
    return [dict(r) for r in records[:limit]]


def clear_store() -> None:
    """테스트용: in-memory store 초기화."""
    with _LOCK:
        _STORE.clear()
