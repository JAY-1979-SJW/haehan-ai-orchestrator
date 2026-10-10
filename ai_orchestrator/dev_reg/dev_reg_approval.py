"""개발자 등록 신청 승인 대기 모델.

approval.py 의 ApprovalToken 을 내부 승인 게이트로 재사용.
이 모듈은 그 위에 개발자 등록 전용 메타데이터(provider, action_type,
screenshot, summary 등)를 관리한다.

보안 원칙:
  - approval_token_hash: SHA256(token_id) 만 기록. token 원문 저장 금지.
  - token_id(UUID) 는 식별자로 내부 저장 (비밀값이 아니므로 허용).
  - summary 에 패스워드/쿠키/세션 토큰 포함 금지.
  - screenshot_path: 파일 시스템 경로만 기록. 바이너리 원문 저장 금지.

저장: storage/dev_reg_approvals.jsonl (append-only JSONL, last-wins 복구)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.core.config import LOG_DIR

from tools.gates.approval import approve_token, reject_token

logger = logging.getLogger(__name__)

DevRegStatus = Literal["pending", "approved", "rejected", "expired", "executed", "failed"]

_STORE_PATH = LOG_DIR / "dev_reg_approvals.jsonl"
_store: dict[str, dict] = {}  # task_id → record dict
_token_index: dict[str, str] = {}  # token_id → task_id (역방향 인덱스)
_lock = threading.Lock()
_loaded = False

# ── 승인 이벤트 버스 ─────────────────────────────────────────────
# runner 가 ev.wait() 로 블록킹, webhook 이 signal_approval_event() 로 깨움.
# pre-signal 지원: signal 이 register 보다 먼저 도달해도 runner 가 즉시 반환.
_event_registry: dict[str, threading.Event] = {}  # task_id → threading.Event
_event_lock = threading.Lock()


@dataclass
class DevRegApproval:
    task_id: str
    token_id: str  # ApprovalToken 참조 식별자 (UUID, 비밀 아님)
    approval_token_hash: str  # SHA256(token_id) — 요구사항 준수
    provider: str  # hiworks / naver / google
    action_type: str  # developer_apply / app_register / oauth_submit
    risk_level: str  # medium / high
    status: DevRegStatus
    summary: str  # 입력 필드 요약 (민감 원문 절대 금지)
    target_url: str
    screenshot_path: str  # 파일 경로 (바이너리 원문 아님)
    requested_by: str
    approved_by: str = ""
    expires_at: str = ""
    created_at: str = ""
    decided_at: str = ""  # 승인/거절 결정 시각
    executed_at: str = ""  # 실제 폼 제출 시각
    reject_reason: str = ""
    result: str = ""
    error: str = ""
    telegram_message_id: str = ""


_FIELDS = tuple(DevRegApproval.__dataclass_fields__.keys())

# API 응답에서 반드시 제거할 민감 필드
_SAFE_EXCLUDE: frozenset = frozenset({"approval_token_hash", "screenshot_path"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_token(token_id: str) -> str:
    return hashlib.sha256(token_id.encode()).hexdigest()


def _append_event(event_type: str, rec: dict) -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _STORE_PATH.open("a", encoding="utf-8") as f:
            ev = {"event_timestamp": _now_iso(), "event_type": event_type, **rec}
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("dev_reg_approvals 기록 실패: %s", e)


def _load() -> None:
    global _store, _token_index, _loaded
    _store = {}
    _token_index = {}
    if _STORE_PATH.exists():
        try:
            with _STORE_PATH.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tid = ev.get("task_id")
                    if not tid:
                        continue
                    rec = {k: ev.get(k, "") for k in _FIELDS}
                    _store[tid] = rec
                    tok = rec.get("token_id", "")
                    if tok:
                        _token_index[tok] = tid
        except OSError as e:
            logger.error("dev_reg_approvals 로드 실패: %s", e)
    _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        _load()


def clear() -> None:
    """테스트 전용 — 인메모리 스토어 초기화."""
    global _loaded
    with _lock:
        _store.clear()
        _token_index.clear()
        _loaded = True
    with _event_lock:
        _event_registry.clear()


def register_approval_waiter(task_id: str) -> threading.Event:
    """runner 가 텔레그램 발송 후 호출 — 승인 이벤트 수신 대기.

    signal_approval_event 가 먼저 도달한 경우(pre-signal) 이미 set 된 Event 를 반환한다.
    """
    with _event_lock:
        ev = _event_registry.get(task_id)
        if ev is None:
            ev = threading.Event()
            _event_registry[task_id] = ev
    return ev


def signal_approval_event(task_id: str) -> None:
    """webhook 승인/거절 완료 시 호출 — 대기 중인 runner 를 즉시 깨운다.

    waiter 가 아직 등록되지 않았으면(pre-signal) set 상태의 Event 를 미리 등록해
    이후 register_approval_waiter 호출 시 즉시 반환되도록 한다.
    """
    with _event_lock:
        ev = _event_registry.get(task_id)
        if ev is None:
            ev = threading.Event()
            _event_registry[task_id] = ev
        ev.set()


def unregister_approval_waiter(task_id: str) -> None:
    """runner 완료 후 이벤트 정리."""
    with _event_lock:
        _event_registry.pop(task_id, None)


def create_pending(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    task_id: str,
    token_id: str,
    provider: str,
    action_type: str,
    risk_level: str,
    summary: str,
    target_url: str,
    screenshot_path: str,
    requested_by: str,
    expires_at: str,
) -> DevRegApproval:
    """pending 상태의 개발자 등록 승인 레코드 생성."""
    with _lock:
        _ensure_loaded()
        now = _now_iso()
        rec = DevRegApproval(
            task_id=task_id,
            token_id=token_id,
            approval_token_hash=_hash_token(token_id),
            provider=provider,
            action_type=action_type,
            risk_level=risk_level,
            status="pending",
            summary=summary,
            target_url=target_url,
            screenshot_path=screenshot_path,
            requested_by=requested_by,
            expires_at=expires_at,
            created_at=now,
        )
        d = asdict(rec)
        _store[task_id] = d
        _token_index[token_id] = task_id
        _append_event("DEV_REG_PENDING", d)
    return rec


def _safe_dict(rec: dict) -> dict:
    """API 응답용 안전한 dict — 민감 필드(approval_token_hash, screenshot_path) 제거."""
    return {k: v for k, v in rec.items() if k not in _SAFE_EXCLUDE}


def list_pending() -> list:
    """pending 상태 레코드 목록 반환 (민감 필드 제외)."""
    with _lock:
        _ensure_loaded()
        return [_safe_dict(rec) for rec in _store.values() if rec.get("status") == "pending"]


def list_history(
    *,
    status: str | None = None,
    provider: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """승인 히스토리 조회 — created_at 내림차순, 페이지네이션, 필터 지원 (민감 필드 제외)."""
    with _lock:
        _ensure_loaded()
        records = list(_store.values())  # 락 안에서 복사

    if status:
        records = [r for r in records if r.get("status") == status]
    if provider:
        records = [r for r in records if r.get("provider") == provider]

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    records = records[offset : offset + limit]

    return [_safe_dict(r) for r in records]


def get_detail(task_id: str) -> dict | None:
    """단일 task 상세 조회 (민감 필드 제외). 없으면 None."""
    with _lock:
        _ensure_loaded()
        rec = _store.get(task_id)
    return _safe_dict(rec) if rec else None


def get(task_id: str) -> DevRegApproval | None:
    with _lock:
        _ensure_loaded()
        rec = _store.get(task_id)
    return DevRegApproval(**rec) if rec else None


def get_by_token_id(token_id: str) -> DevRegApproval | None:
    with _lock:
        _ensure_loaded()
        tid = _token_index.get(token_id)
        rec = _store.get(tid) if tid else None
    return DevRegApproval(**rec) if rec else None


def _update(task_id: str, event_type: str, **fields) -> DevRegApproval | None:
    """내부 상태 업데이트 + JSONL 이벤트 기록."""
    with _lock:
        _ensure_loaded()
        rec = _store.get(task_id)
        if not rec:
            return None
        for k, v in fields.items():
            if k in _FIELDS and v is not None:
                rec[k] = v
        _append_event(event_type, rec)
        return DevRegApproval(**rec)


def mark_telegram_sent(task_id: str, message_id: str = "") -> DevRegApproval | None:
    return _update(task_id, "DEV_REG_TELEGRAM_SENT", telegram_message_id=message_id)


def mark_executed(task_id: str, result: str) -> DevRegApproval | None:
    return _update(task_id, "DEV_REG_EXECUTED", status="executed", result=result, executed_at=_now_iso())


def mark_failed(task_id: str, error: str) -> DevRegApproval | None:
    return _update(task_id, "DEV_REG_FAILED", status="failed", error=error)


def mark_rejected_internal(task_id: str) -> DevRegApproval | None:
    """runner 에서 거절 확정 시 상태 동기화 (handle_telegram_decision 과 중복 방지)."""
    return _update(task_id, "DEV_REG_REJECTED", status="rejected")


def mark_expired_internal(task_id: str) -> DevRegApproval | None:
    """runner 에서 만료 확정 시 상태 동기화."""
    return _update(task_id, "DEV_REG_EXPIRED", status="expired", decided_at=_now_iso())


def handle_telegram_decision(
    token_id: str,
    action: str,
    actor: str,
    role: str,
    reason: str = "",
) -> dict:
    """텔레그램 [승인] / [거절] 버튼 처리.

    token_id → DevRegApproval 조회 → ApprovalToken 처리 → 상태 업데이트.
    Returns: {"success": bool, "status": str, "actor": str, "role": str, "message": str}
    """
    approval = get_by_token_id(token_id)
    if not approval:
        logger.warning("dev_reg callback: approval 없음 | token_id=%.8s", token_id)
        return {
            "success": False,
            "status": "not_found",
            "actor": actor,
            "role": role,
            "message": "해당 토큰의 승인 레코드를 찾을 수 없습니다",
        }

    task_id = approval.task_id

    if action == "approve":
        token, status = approve_token(token_id, task_id, actor, role)
        _APPROVE_AUDIT = {
            "approved": "DEV_REG_APPROVED",
            "not_found": "APPROVAL_INVALID_TOKEN",
            "task_mismatch": "APPROVAL_INVALID_TOKEN",
            "already_used": "APPROVAL_ALREADY_USED",
            "expired": "DEV_REG_EXPIRED",
            "forbidden": "APPROVAL_DENIED",
            "rate_limited": "APPROVAL_RATE_LIMITED",
        }
        log_event(
            _APPROVE_AUDIT.get(status, "APPROVAL_DENIED"),
            task_id,
            token_id=token_id,
            actor=actor,
            role=role,
            decision=status,
            risk_level=token.risk_level,
            action_type=approval.action_type,
            note=f"source=telegram provider={approval.provider}",
        )
        if status == "approved":
            _update(task_id, "DEV_REG_APPROVED", status="approved", approved_by=actor, decided_at=_now_iso())
            signal_approval_event(task_id)  # runner 즉시 재개
            message = f"승인 완료: {actor}"
        elif status == "expired":
            _update(task_id, "DEV_REG_EXPIRED", status="expired", decided_at=_now_iso())
            signal_approval_event(task_id)  # runner 즉시 재개 (만료 처리)
            message = "만료된 토큰입니다"
        else:
            message = f"처리 실패: {status}"
        return {"success": status == "approved", "status": status, "actor": actor, "role": role, "message": message}

    else:  # reject
        token, status = reject_token(token_id, task_id, actor, role, reason=reason)
        _REJECT_AUDIT = {
            "rejected": "DEV_REG_REJECTED",
            "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
            "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
            "already_used": "APPROVAL_ALREADY_USED",
            "expired": "DEV_REG_EXPIRED",
            "forbidden": "APPROVAL_REJECT_FORBIDDEN",
            "rate_limited": "APPROVAL_RATE_LIMITED",
        }
        log_event(
            _REJECT_AUDIT.get(status, "APPROVAL_REJECTED"),
            task_id,
            token_id=token_id,
            actor=actor,
            role=role,
            decision=status,
            risk_level=token.risk_level,
            action_type=approval.action_type,
            note=f"source=telegram provider={approval.provider}" + (f" reason={reason}" if reason else ""),
        )
        if status == "rejected":
            _update(
                task_id,
                "DEV_REG_REJECTED",
                status="rejected",
                approved_by=actor,
                decided_at=_now_iso(),
                reject_reason=reason,
            )
            signal_approval_event(task_id)  # runner 즉시 재개 (거절 처리)
            message = f"거절 완료: {actor}" + (f" ({reason})" if reason else "")
        elif status == "expired":
            _update(task_id, "DEV_REG_EXPIRED", status="expired", decided_at=_now_iso())
            signal_approval_event(task_id)  # runner 즉시 재개 (만료 처리)
            message = "만료된 토큰입니다"
        else:
            message = f"처리 실패: {status}"
        return {"success": status == "rejected", "status": status, "actor": actor, "role": role, "message": message}


__all__ = [
    "DevRegApproval",
    "DevRegStatus",
    "clear",
    "create_pending",
    "get",
    "get_by_token_id",
    "get_detail",
    "handle_telegram_decision",
    "list_history",
    "list_pending",
    "mark_executed",
    "mark_expired_internal",
    "mark_failed",
    "mark_rejected_internal",
    "mark_telegram_sent",
    "register_approval_waiter",
    "signal_approval_event",
    "unregister_approval_waiter",
]
