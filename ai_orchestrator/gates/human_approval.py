"""사람이 발급하는 1회용 승인 저장소 (R2d-2 P0b).

설계: docs/architecture/R2D2_HUMAN_APPROVAL_PLAN.md §3. 이 모듈은 **저장·소진 로직만** 담는다(HTTP·인증 없음).
발급(approve)은 로그인한 사람의 요청만 처리하는 발급 API(P0c)가 부르며, AI 도구 경로가 발급하지 못한다는 보장은
그 API 의 인증(JWT)·Origin 검사·계약 시험이 맡는다. 여기서는 `approved_via` 가 허용 목록에 있어야만 승인으로 인정한다.

흐름: 제안(request_approval, pending) → 사람이 승인(approve) → 실행 직전 consume_approval(op, target, 실제 content).
승인은 서버 저장 기록이고 비밀 토큰이 없다. 실행은 실제 내용을 해시해 (op, target_hash, content_hash)가 같은
approved 기록을 **한 번의 원자적 갱신**으로 소진한다. 불일치·만료·소진·미승인이면 `ApprovalNotFound`(GateBlocked)이며
메시지에는 문구·해시·승인 번호를 싣지 않는다.

저장은 `ai_orchestrator/persistence/human_approval_store.py`(L7)가 맡고, 이 모듈(L2)은 정책만 담는다.
`scripts` 를 import 하지 않는다(게이트 핵심과 같은 규칙 — 순환 방지).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from ..persistence import human_approval_store as store
from . import gate_core
from .gate_types import GateResult, GateVerdict, RiskLevel

SCHEMA_VERSION = store.SCHEMA_VERSION
DEFAULT_TTL_S = 15 * 60  # 즉시 실행형 승인 유효 시간
MAX_SNAPSHOT_CHARS = 200_000

# 발급(approve)을 인정하는 경로. 'jwt'=로그인 사용자 화면, 'jwt+pin'=PIN 확인까지 한 경우.
# 'basic'·'mcp'·'agent'·'telegram' 등 도구·서비스 경로 값은 인정하지 않는다.
APPROVED_VIA_ALLOWED = frozenset({"jwt", "jwt+pin"})

_RECIPIENT_KEYS = frozenset({"to", "cc", "bcc", "recipients", "receivers", "receiver"})

PENDING, APPROVED, USED, EXPIRED, REJECTED, REVOKED = (
    store.PENDING,
    store.APPROVED,
    store.USED,
    store.EXPIRED,
    store.REJECTED,
    store.REVOKED,
)


class ApprovalNotFound(gate_core.GateBlocked):
    """실행하려는 (작업·대상·내용)에 대해 유효한 승인이 없다. 메시지에 문구·해시·번호를 싣지 않는다."""

    def __init__(self, op_name: str, reason: str = "사람이 승인한 기록이 없거나 이미 사용·만료됨") -> None:
        super().__init__(
            GateResult(
                verdict=GateVerdict.BLOCKED,
                risk=RiskLevel.APPROVE,
                op_name=op_name,
                reason=reason,
            )
        )


class ApprovalError(ValueError):
    """잘못된 승인 요청(상태 전이 불가, 허용되지 않은 발급 경로 등)."""


# ── 해시 ────────────────────────────────────────────────────────────


def _norm(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return {str(k): _norm(v, str(k)) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_norm(v, key) for v in value]
        if key.lower() in _RECIPIENT_KEYS:  # 수신자 목록은 소문자·중복 제거·정렬
            return sorted({str(i).lower() for i in items})
        return items
    if key.lower() in _RECIPIENT_KEYS and value is not None:
        return str(value).strip().lower()
    return value


def canonical_json(content: Any) -> str:
    """내용을 키 정렬·공백 정리·수신자 정규화한 JSON 문자열로 만든다(해시 입력)."""
    return json.dumps(_norm(content), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(content: Any) -> str:
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def target_hash(target: str | Sequence[str]) -> str:
    items = [target] if isinstance(target, str) else list(target)
    norm = sorted({str(t).strip().lower() for t in items})
    return hashlib.sha256(json.dumps(norm, ensure_ascii=False).encode("utf-8")).hexdigest()


# ── 공통 ────────────────────────────────────────────────────────────


def db_path():
    return store.db_path()


def _now(now: float | None) -> float:
    return time.time() if now is None else now


def _audit(name: str, **fields: Any) -> None:
    gate_core.audit(name, **fields)


# ── 제안 · 승인 · 거부 · 철회 ───────────────────────────────────────


def request_approval(  # noqa: PLR0913 - 선택 인자는 모두 키워드 전용·기본값이 있는 공개 API(호출부 가독성)
    op: str,
    target: str | Sequence[str],
    content: Any,
    *,
    requested_by: str,
    target_preview: str = "",
    schedule_job_id: str | None = None,
    max_uses: int = 1,
    now: float | None = None,
) -> str:
    """승인 요청(pending)을 등록한다. 누구나(에이전트 포함) 제안할 수 있지만 **승인은 되지 않는다**."""
    snapshot = canonical_json(content)
    if len(snapshot) > MAX_SNAPSHOT_CHARS:
        raise ApprovalError("승인 내용이 너무 큽니다")
    if max_uses < 1:
        raise ApprovalError("max_uses 는 1 이상이어야 합니다")
    rid = "ha_" + uuid.uuid4().hex
    chash = content_hash(content)
    store.insert_request(rid, op, target_hash(target), target_preview[:200], chash, snapshot, requested_by,
                         _now(now), max_uses, schedule_job_id)
    _audit("approval.requested", op=op, id=rid, by=requested_by, content=chash[:8])
    return rid


def approve(
    request_id: str,
    *,
    approved_by: str,
    approved_via: str,
    ttl_seconds: int = DEFAULT_TTL_S,
    now: float | None = None,
) -> dict[str, Any]:
    """pending 요청을 승인한다. 발급 API(P0c)만 부른다. `approved_via` 가 허용 목록에 없으면 거부한다."""
    if approved_via not in APPROVED_VIA_ALLOWED:
        _audit("approval.denied_via", id=request_id, via=approved_via)
        raise ApprovalError("허용되지 않은 승인 경로입니다")
    if not approved_by.strip():
        raise ApprovalError("승인자가 필요합니다")
    ts = _now(now)
    row = store.approve_cas(request_id, approved_by, approved_via, ts, ts + ttl_seconds)
    if row is None:
        raise ApprovalError("승인할 수 없는 상태이거나 요청이 없습니다")
    _audit("approval.approved", op=row["op"], id=request_id, by=approved_by, via=approved_via,
           content=row["content_hash"][:8])
    return _public(row)


def reject(request_id: str, *, rejected_by: str, now: float | None = None) -> None:
    if not store.reject_cas(request_id, rejected_by, _now(now)):
        raise ApprovalError("거부할 수 없는 상태이거나 요청이 없습니다")
    _audit("approval.rejected", id=request_id, by=rejected_by)


def revoke(request_id: str, *, revoked_by: str) -> None:
    """승인(approved) 또는 대기(pending) 기록을 철회한다. 이미 소진된 것은 되돌리지 못한다."""
    if not store.revoke_cas(request_id):
        raise ApprovalError("철회할 수 없는 상태이거나 요청이 없습니다")
    _audit("approval.revoked", id=request_id, by=revoked_by)


def revoke_for_job(schedule_job_id: str, *, revoked_by: str) -> int:
    """예약 내용이 바뀌었을 때 그 예약에 묶인 미소진 승인을 모두 철회한다(예약 수정 경쟁 방지)."""
    n = store.revoke_for_job(schedule_job_id)
    if n:
        _audit("approval.revoked_for_job", job=schedule_job_id, by=revoked_by, count=n)
    return n


# ── 소진 ────────────────────────────────────────────────────────────


def consume_approval(
    op: str,
    target: str | Sequence[str],
    content: Any,
    *,
    schedule_job_id: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """실행 직전 호출. 실제 content 를 해시해 같은 (op, target, content) 의 approved 승인 1건을 **원자적으로** 소진한다.

    성공하면 소진된 기록(공개 필드)을 돌려주고, 없거나 만료·소진이면 ApprovalNotFound(메시지에 비밀 없음).
    `schedule_job_id` 를 주면 그 예약에 묶인 승인만, 주지 않으면 예약에 묶이지 않은 승인만 인정한다.
    """
    chash = content_hash(content)
    row = store.consume_cas(op, target_hash(target), chash, schedule_job_id, _now(now))
    if row is None:
        _audit("approval.consume_denied", op=op, content=chash[:8])
        raise ApprovalNotFound(op)
    _audit("approval.consumed", op=op, id=row["id"], by=row["approved_by"], content=chash[:8])
    return _public(row)


# ── 조회(화면·감사용) ───────────────────────────────────────────────


def _public(row: dict[str, Any]) -> dict[str, Any]:
    """외부에 보여 줄 필드. 해시 원문은 싣지 않는다(앞 8자만)."""
    return {
        "id": row["id"],
        "op": row["op"],
        "target_preview": row["target_preview"],
        "content_hash8": row["content_hash"][:8],
        "requested_by": row["requested_by"],
        "requested_at": row["requested_at"],
        "status": row["status"],
        "approved_by": row["approved_by"],
        "approved_at": row["approved_at"],
        "approved_via": row["approved_via"],
        "expires_at": row["expires_at"],
        "max_uses": row["max_uses"],
        "uses": row["uses"],
        "schedule_job_id": row["schedule_job_id"],
    }


def get_request(request_id: str) -> dict[str, Any] | None:
    """승인 화면용: 요청 1건과 **내용 스냅샷**(사람이 실제로 보고 승인할 내용)."""
    row = store.get(request_id)
    if row is None:
        return None
    return {**_public(row), "content_snapshot": json.loads(row["content_snapshot"])}


def list_pending() -> list[dict[str, Any]]:
    return [_public(r) for r in store.list_by_status(PENDING)]


def expire_due(*, now: float | None = None) -> int:
    """만료 시각이 지난 approved 기록을 expired 로 표시한다(소진 시에도 만료는 검사하므로 표시용)."""
    return store.expire_due(_now(now))
