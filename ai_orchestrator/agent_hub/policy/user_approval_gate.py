"""User Approval Gate — 사용자 승인 (1회용 + 만료 + scope-bound).

기존 delegated_permission_*과 별개:
- 1회 승인 = 1개 작업 (max_executions 고정 1)
- 사전 요약 review 후 승인
- 짧은 만료 시간 (default 5분)
- 승인 후 동일 params hash로만 실행 가능 (스코프 이탈 차단)
- 실행 후 자동 EXHAUSTED
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

# 상태
STATUS_PENDING = "PENDING_USER_REVIEW"
STATUS_APPROVED = "APPROVED"
STATUS_EXHAUSTED = "EXHAUSTED"
STATUS_REVOKED = "REVOKED"
STATUS_EXPIRED = "EXPIRED"
STATUS_REJECTED = "REJECTED"

_LOCK = threading.Lock()
_REQUESTS: dict[str, dict[str, Any]] = {}
_TOKENS: dict[str, str] = {}  # token → request_id

# 민감 필드 차단 (요약/저장에서 제거)
_SENSITIVE_PARAM_KEYS = frozenset((
    "password", "otp", "cert_password", "certificate_password",
    "cookie", "session", "token", "storage_state", "private_key",
    "npki", "auth_header", "Authorization",
))


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """민감 파라미터 제거."""
    out = {}
    for k, v in params.items():
        kl = k.lower()
        if any(s in kl for s in _SENSITIVE_PARAM_KEYS):
            continue
        out[k] = v
    return out


def _params_hash(params: dict[str, Any]) -> str:
    """승인 범위 검증용 — 정렬된 JSON의 SHA256."""
    sanitized = _sanitize_params(params)
    s = json.dumps(sanitized, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """공개 helper — 민감 파라미터 제거 결과를 반환."""
    return _sanitize_params(params)


def compute_params_hash(params: dict[str, Any]) -> str:
    """공개 helper — 승인 범위 hash와 동일한 SHA256."""
    return _params_hash(params)


def create_approval_request(
    action_name: str,
    params: dict[str, Any],
    summary: dict[str, Any],
    user_id: str = "anonymous",
    duration_seconds: int = 300,
) -> dict[str, Any]:
    """승인 요청 생성 — 사용자 review 대기 상태."""
    if duration_seconds <= 0 or duration_seconds > 1800:
        raise ValueError(f"승인 만료 시간 범위 초과: {duration_seconds} (1~1800초)")

    request_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)

    record = {
        "request_id": request_id,
        "action_name": action_name,
        "params_hash": _params_hash(params),
        "params_sanitized": _sanitize_params(params),
        "summary": summary,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "approved_at": None,
        "executed_at": None,
        "status": STATUS_PENDING,
        "approval_token": None,
    }
    with _LOCK:
        _REQUESTS[request_id] = record
    return dict(record)


def approve_request(request_id: str, approver_user_id: str) -> dict[str, Any]:
    """사용자가 사전 요약을 보고 승인."""
    with _LOCK:
        rec = _REQUESTS.get(request_id)
        if not rec:
            return {"ok": False, "reason": f"요청 없음: {request_id}"}
        if rec["status"] != STATUS_PENDING:
            return {"ok": False, "reason": f"이미 처리됨: {rec['status']}"}
        if _is_expired(rec):
            rec["status"] = STATUS_EXPIRED
            return {"ok": False, "reason": "만료"}

        token = uuid.uuid4().hex
        rec["status"] = STATUS_APPROVED
        rec["approved_at"] = datetime.now(timezone.utc).isoformat()
        rec["approval_token"] = token
        rec["approver_user_id"] = approver_user_id
        _TOKENS[token] = request_id
        return {
            "ok": True,
            "request_id": request_id,
            "approval_token": token,
            "expires_at": rec["expires_at"],
        }


def reject_request(request_id: str, reason: str = "") -> bool:
    with _LOCK:
        rec = _REQUESTS.get(request_id)
        if not rec or rec["status"] != STATUS_PENDING:
            return False
        rec["status"] = STATUS_REJECTED
        rec["reject_reason"] = reason
        return True


def revoke_approval(request_id: str) -> bool:
    """승인됐지만 아직 미실행인 요청 철회."""
    with _LOCK:
        rec = _REQUESTS.get(request_id)
        if not rec or rec["status"] != STATUS_APPROVED:
            return False
        rec["status"] = STATUS_REVOKED
        token = rec.get("approval_token")
        if token:
            _TOKENS.pop(token, None)
        return True


def verify_and_consume_token(
    token: str,
    action_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """
    실행 직전 토큰 검증 + 1회 소비.
    - 토큰 일치
    - action_name 일치
    - params hash 일치 (승인 범위 이탈 차단)
    - 만료 전
    - APPROVED 상태
    """
    with _LOCK:
        request_id = _TOKENS.get(token)
        if not request_id:
            return {"ok": False, "reason": "유효하지 않은 토큰"}
        rec = _REQUESTS.get(request_id)
        if not rec:
            return {"ok": False, "reason": "요청 없음"}
        if rec["status"] != STATUS_APPROVED:
            return {"ok": False, "reason": f"상태 오류: {rec['status']}"}
        if _is_expired(rec):
            rec["status"] = STATUS_EXPIRED
            return {"ok": False, "reason": "만료"}
        if rec["action_name"] != action_name:
            return {"ok": False, "reason": "action_name 불일치 (스코프 이탈)"}
        if rec["params_hash"] != _params_hash(params):
            return {"ok": False, "reason": "params_hash 불일치 (승인 범위 이탈)"}

        # 즉시 EXHAUSTED 처리 (1회용)
        rec["status"] = STATUS_EXHAUSTED
        rec["executed_at"] = datetime.now(timezone.utc).isoformat()
        _TOKENS.pop(token, None)
        return {
            "ok": True,
            "request_id": request_id,
            "action_name": action_name,
            "executed_at": rec["executed_at"],
        }


def get_request(request_id: str) -> dict[str, Any] | None:
    with _LOCK:
        rec = _REQUESTS.get(request_id)
        return dict(rec) if rec else None


def list_pending() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(r) for r in _REQUESTS.values() if r["status"] == STATUS_PENDING]


def clear_all() -> None:
    with _LOCK:
        _REQUESTS.clear()
        _TOKENS.clear()


def _is_expired(rec: dict[str, Any]) -> bool:
    try:
        exp = datetime.fromisoformat(rec["expires_at"])
        return datetime.now(timezone.utc) > exp
    except (KeyError, ValueError):
        return True
