"""
Action Approval/Audit JSONL Store

DB schema 변경 없음. JSONL 파일 기반 1차 저장.
운영 데이터 write 없음 — 테스트/감사 목적 로컬 파일만 사용.

저장 금지:
- raw params
- password / otp / cert_password / private_key
- cookie / session / storage_state
- 인증서 파일 경로
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ── 저장 금지 필드 ────────────────────────────────────────────────────────────

_FORBIDDEN_STORE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cert_password",
        "certificate_password",
        "cookie",
        "cookies",
        "session",
        "storage_state",
        "private_key",
        "npki",
        "auth_header",
        "Authorization",
        "token",
        "access_token",
        "refresh_token",
        "certificate_file_path",
        "raw_params",
        "params",
    }
)

# ── status 상수 ───────────────────────────────────────────────────────────────

STATUS_PENDING = "PENDING_USER_REVIEW"
STATUS_APPROVED = "APPROVED"
STATUS_CONSUMED = "APPROVED_AND_CONSUMED"
STATUS_EXPIRED = "EXPIRED"
STATUS_REJECTED = "REJECTED"
STATUS_BLOCKED = "BLOCKED"

# ── in-memory store (프로세스 내 빠른 조회용) ─────────────────────────────────

_STORE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

# JSONL 저장 경로 (환경 변수 또는 기본값)
_DEFAULT_AUDIT_DIR = Path(__file__).parent.parent.parent / "data" / "audit"
_AUDIT_FILE_NAME = "action_approval_audit.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _audit_path() -> Path:
    p = _DEFAULT_AUDIT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / _AUDIT_FILE_NAME


def _validate_no_forbidden(record: dict[str, Any]) -> list[str]:
    return [f"금지 필드: {k!r}" for k in record if k in _FORBIDDEN_STORE_FIELDS]


def _append_jsonl(record: dict[str, Any]) -> None:
    try:
        with _audit_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: S110
        pass  # 파일 기록 실패 시 in-memory만 유지


def save_approval_request(
    *,
    approval_request_id: str,
    action_name: str,
    params_hash: str,
    requested_by: str,
    scope_safe: dict[str, Any],
    summary_safe: dict[str, Any],
    status: str = STATUS_PENDING,
    expires_at: str = "",
) -> dict[str, Any]:
    """
    승인 요청을 in-memory + JSONL에 저장한다.

    raw params, 민감 필드는 절대 저장하지 않는다.
    scope_safe / summary_safe는 발신자가 sanitize한 값만 전달해야 한다.
    """
    # scope_safe, summary_safe에 금지 필드 포함 여부 검사
    combined = {**scope_safe, **summary_safe}
    violations = _validate_no_forbidden(combined)
    if violations:
        raise ValueError(f"approval_request 저장 금지 필드: {violations}")

    record: dict[str, Any] = {
        "approval_request_id": approval_request_id,
        "action_name": action_name,
        "params_hash": params_hash,
        "requested_by": requested_by,
        "scope_safe": dict(scope_safe),
        "summary_safe": dict(summary_safe),
        "status": status,
        "created_at": _now_iso(),
        "expires_at": expires_at,
        "consumed_at": None,
        "verdict": None,
        "blocked_reason": None,
    }

    with _LOCK:
        _STORE[approval_request_id] = record
    _append_jsonl({"_type": "approval_request", **record})
    return dict(record)


def update_approval_status(
    approval_request_id: str,
    *,
    status: str,
    verdict: str | None = None,
    blocked_reason: str | None = None,
    consumed_at: str | None = None,
) -> bool:
    """승인 요청 상태를 업데이트하고 감사 로그를 추가한다."""
    with _LOCK:
        record = _STORE.get(approval_request_id)
        if record is None:
            return False
        record["status"] = status
        if verdict is not None:
            record["verdict"] = verdict
        if blocked_reason is not None:
            record["blocked_reason"] = blocked_reason
        if consumed_at is not None:
            record["consumed_at"] = consumed_at
        snapshot = dict(record)

    _append_jsonl({"_type": "approval_status_update", **snapshot})
    return True


def get_approval_request(approval_request_id: str) -> dict[str, Any] | None:
    """승인 요청 조회."""
    with _LOCK:
        record = _STORE.get(approval_request_id)
    return dict(record) if record else None


def list_approval_requests(action_name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """승인 요청 목록 조회 (선택: action_name 필터)."""
    with _LOCK:
        records = list(_STORE.values())
    if action_name:
        records = [r for r in records if r.get("action_name") == action_name]
    return [dict(r) for r in records[:limit]]


def clear_store() -> None:
    """테스트용: in-memory store 초기화."""
    with _LOCK:
        _STORE.clear()
