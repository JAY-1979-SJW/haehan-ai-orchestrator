import json
import logging
import threading
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.core.config import APPROVAL_STORE_PATH as _STORE_PATH
from ai_orchestrator.core.models import RiskAssessment, TaskRequest

logger = logging.getLogger(__name__)

# ── Role 정책 ──────────────────────────────────────────────────────
# 승인/거절을 수행할 수 있는 내부 권한
_APPROVER_ROLES = {"admin", "owner"}

# 레거시 별칭: 외부에서 들어온 role 문자열을 내부 표준 role로 정규화
_ROLE_ALIASES = {"approver": "admin"}


def _normalize_role(role: str) -> str:
    return _ROLE_ALIASES.get(role, role)


# ── Rate limit (인메모리, 재시작 시 초기화) ─────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SEC = 60

# ── 토큰 저장소 ────────────────────────────────────────────────────
_store: dict[str, dict] = {}


@dataclass
class ApprovalToken:
    token_id: str
    task_id: str
    issued_at: str
    expires_at: str
    issued_by: str
    approved_by: str | None
    risk_level: str
    status: Literal["issued", "approved", "expired", "revoked", "rejected"]
    used_at: str | None = None
    result: str = ""
    # Stage 13H-2E: public_id — UI/audit/result_data 표시용 식별자.
    # token_id 는 승인 검증용 secret-like 값이므로 외부 노출 경로에는
    # public_id 만 사용한다. ("appr_" prefix + uuid hex)
    public_id: str = ""


def _new_public_id() -> str:
    return "appr_" + uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# JSONL 이벤트 필드 중 토큰 엔트리로 복원할 키 목록
_TOKEN_FIELDS = (
    "token_id",
    "task_id",
    "issued_at",
    "expires_at",
    "issued_by",
    "approved_by",
    "risk_level",
    "status",
    "used_at",
    "result",
    "public_id",
)

# 만료된 지 이 시간 이상 지난 토큰은 로딩 시 메모리에서 제외
_STALE_AFTER = timedelta(hours=24)


def _apply_store_line(line: str) -> None:
    """JSONL 1줄을 파싱해 _store 에 token_id 별 last-wins 로 반영."""
    line = line.strip()
    if not line:
        return
    try:
        event = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning("승인 토큰 이벤트 파싱 실패: %s | line=%r", e, line)
        return
    token_id = event.get("token_id")
    if not token_id:
        return
    entry = {k: event.get(k) for k in _TOKEN_FIELDS}
    entry.setdefault("used_at", None)
    entry["result"] = entry.get("result") or ""
    entry["public_id"] = entry.get("public_id") or ""
    _store[token_id] = entry


def _load_store() -> None:
    """append-only JSONL 이벤트를 재생하여 _store 를 복구한다.

    각 라인은 이벤트 메타데이터 + 토큰 스냅샷. token_id 별 last-wins 로 머지.
    만료 후 24시간 이상 경과한 토큰은 로딩 시 필터링.
    """
    global _store
    _store = {}
    if not _STORE_PATH.exists():
        return
    try:
        with _STORE_PATH.open(encoding="utf-8") as f:
            for line in f:
                _apply_store_line(line)
    except OSError as e:
        logger.error("승인 토큰 저장소 로드 실패: %s", e)
        _store = {}
        return

    # 만료된 지 오래된 토큰 필터
    threshold = _now() - _STALE_AFTER
    stale = []
    for tid, entry in _store.items():
        try:
            exp = datetime.fromisoformat(entry["expires_at"])
        except (TypeError, ValueError):
            continue
        if exp < threshold:
            stale.append(tid)
    for tid in stale:
        del _store[tid]


def _append_event(event_type: str, entry: dict) -> None:
    """토큰 상태 변경 이벤트 1줄을 JSONL 에 append."""
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_timestamp": _now().isoformat(),
            "event_type": event_type,
            **{k: entry.get(k) for k in _TOKEN_FIELDS},
        }
        with _STORE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("승인 토큰 이벤트 기록 실패: %s", e)


def _check_rate_limit(actor: str) -> tuple[bool, str]:
    now_ts = _now().timestamp()
    with _rate_lock:
        attempts = [t for t in _rate_store[actor] if now_ts - t < RATE_LIMIT_WINDOW_SEC]
        if len(attempts) >= RATE_LIMIT_MAX:
            _rate_store[actor] = attempts
            return False, f"{RATE_LIMIT_MAX}회/{RATE_LIMIT_WINDOW_SEC}초 초과"
        attempts.append(now_ts)
        _rate_store[actor] = attempts
        return True, ""


def issue_token(req: TaskRequest, risk: RiskAssessment, ttl_minutes: int = 30) -> ApprovalToken:
    _load_store()
    now = _now()
    token = ApprovalToken(
        token_id=str(uuid.uuid4()),
        public_id=_new_public_id(),
        task_id=req.task_id,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        issued_by=req.requested_by,
        approved_by=None,
        risk_level=risk.risk_level,
        status="issued",
        used_at=None,
        result="",
    )
    entry = asdict(token)
    _store[token.token_id] = entry
    _append_event("token_created", entry)

    # Audit log: APPROVAL_ISSUED
    try:
        log_event(
            event_type="APPROVAL_ISSUED",
            task_id=token.task_id,
            risk_level=token.risk_level,
            actor=token.issued_by,
            action_type="",
            target="",
            note=f"public_id={token.public_id}",
        )
    except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
        logger.warning("승인 발행 감사 기록 실패: %s", e)

    return token


def approve_token(
    token_id: str,
    task_id: str,
    approved_by: str,
    role: str,
) -> tuple[ApprovalToken, str]:
    """
    Returns (token, status).
    status: approved | not_found | task_mismatch | already_used | expired | forbidden | rate_limited
    """
    _load_store()

    # 1. 토큰 존재 여부
    entry = _store.get(token_id)
    if not entry:
        logger.warning("승인 시도: 토큰 없음 | token_id=%.8s | actor=%s", token_id, approved_by)
        return _stub_token(token_id, task_id, approved_by), "not_found"

    token_obj = ApprovalToken(**entry)

    # 2. task_id 일치
    if token_obj.task_id != task_id:
        logger.warning(
            "승인 시도: task_id 불일치 | token_id=%.8s | expected=%s | got=%s", token_id, token_obj.task_id, task_id
        )
        return token_obj, "task_mismatch"

    # 3. 이미 사용된 토큰
    if token_obj.status != "issued":
        logger.warning("승인 시도: 이미 사용됨 | token_id=%.8s | status=%s", token_id, token_obj.status)
        return token_obj, "already_used"

    # 4. 만료 검사
    expires = datetime.fromisoformat(token_obj.expires_at)
    if _now() > expires:
        entry["status"] = "expired"
        entry["result"] = "expired"
        _append_event("token_expired", entry)

        # Audit log: APPROVAL_EXPIRED
        try:
            log_event(
                event_type="APPROVAL_EXPIRED",
                task_id=token_obj.task_id,
                risk_level=token_obj.risk_level,
                actor="system",
                decision="expired",
                note=f"public_id={token_obj.public_id}",
            )
        except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
            logger.warning("승인 만료 감사 기록 실패: %s", e)

        token_obj.status = "expired"
        token_obj.result = "expired"
        logger.warning("승인 시도: 만료 | token_id=%.8s", token_id)
        return token_obj, "expired"

    # 5. role 권한 검사
    if _normalize_role(role) not in _APPROVER_ROLES:
        logger.warning("승인 시도: 권한 부족 | token_id=%.8s | actor=%s | role=%s", token_id, approved_by, role)
        return token_obj, "forbidden"

    # 6. rate limit
    allowed, reason = _check_rate_limit(approved_by)
    if not allowed:
        logger.warning("승인 시도: rate_limited | actor=%s | %s", approved_by, reason)
        return token_obj, "rate_limited"

    # 7. 승인 완료
    now = _now()
    entry["approved_by"] = approved_by
    entry["status"] = "approved"
    entry["used_at"] = now.isoformat()
    entry["result"] = "approved"
    _append_event("token_approved", entry)

    # Audit log: APPROVAL_GRANTED
    try:
        log_event(
            event_type="APPROVAL_GRANTED",
            task_id=task_id,
            risk_level=token_obj.risk_level,
            actor=approved_by,
            decision="approved",
            note=f"public_id={token_obj.public_id}",
        )
    except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
        logger.warning("승인 허가 감사 기록 실패: %s", e)

    token_obj.approved_by = approved_by
    token_obj.status = "approved"
    token_obj.used_at = now.isoformat()
    token_obj.result = "approved"

    logger.info("승인 완료 | token_id=%.8s | task=%s | actor=%s | role=%s", token_id, task_id, approved_by, role)
    return token_obj, "approved"


def reject_token(
    token_id: str,
    task_id: str,
    rejected_by: str,
    role: str,
    reason: str = "",
) -> tuple["ApprovalToken", str]:
    """
    Returns (token, status).
    status: rejected | not_found | task_mismatch | already_used | expired | forbidden | rate_limited
    """
    _load_store()

    entry = _store.get(token_id)
    if not entry:
        logger.warning("거절 시도: 토큰 없음 | token_id=%.8s | actor=%s", token_id, rejected_by)
        return _stub_token(token_id, task_id, rejected_by), "not_found"

    token_obj = ApprovalToken(**entry)

    if token_obj.task_id != task_id:
        logger.warning("거절 시도: task_id 불일치 | token_id=%.8s", token_id)
        return token_obj, "task_mismatch"

    if token_obj.status != "issued":
        logger.warning("거절 시도: 이미 사용됨 | token_id=%.8s | status=%s", token_id, token_obj.status)
        return token_obj, "already_used"

    expires = datetime.fromisoformat(token_obj.expires_at)
    if _now() > expires:
        entry["status"] = "expired"
        entry["result"] = "expired"
        _append_event("token_expired", entry)

        # Audit log: APPROVAL_EXPIRED
        try:
            log_event(
                event_type="APPROVAL_EXPIRED",
                task_id=token_obj.task_id,
                risk_level=token_obj.risk_level,
                actor="system",
                decision="expired",
                note=f"public_id={token_obj.public_id}",
            )
        except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
            logger.warning("거절 만료 감사 기록 실패: %s", e)

        token_obj.status = "expired"
        token_obj.result = "expired"
        logger.warning("거절 시도: 만료 | token_id=%.8s", token_id)
        return token_obj, "expired"

    if _normalize_role(role) not in _APPROVER_ROLES:
        logger.warning("거절 시도: 권한 부족 | token_id=%.8s | actor=%s | role=%s", token_id, rejected_by, role)
        return token_obj, "forbidden"

    allowed, rate_reason = _check_rate_limit(rejected_by)
    if not allowed:
        logger.warning("거절 시도: rate_limited | actor=%s | %s", rejected_by, rate_reason)
        return token_obj, "rate_limited"

    now = _now()
    entry["approved_by"] = rejected_by
    entry["status"] = "rejected"
    entry["used_at"] = now.isoformat()
    entry["result"] = f"rejected:{reason}" if reason else "rejected"
    _append_event("token_rejected", entry)

    # Audit log: APPROVAL_REJECTED
    try:
        log_event(
            event_type="APPROVAL_REJECTED",
            task_id=task_id,
            risk_level=token_obj.risk_level,
            actor=rejected_by,
            decision="rejected",
            note=f"public_id={token_obj.public_id}, reason={reason}" if reason else f"public_id={token_obj.public_id}",
        )
    except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
        logger.warning("거절 거부 감사 기록 실패: %s", e)

    token_obj.approved_by = rejected_by
    token_obj.status = "rejected"
    token_obj.used_at = now.isoformat()
    token_obj.result = entry["result"]

    logger.info(
        "거절 완료 | token_id=%.8s | task=%s | actor=%s | role=%s | reason=%s",
        token_id,
        task_id,
        rejected_by,
        role,
        reason or "-",
    )
    return token_obj, "rejected"


def _stub_token(token_id: str, task_id: str, approved_by: str) -> ApprovalToken:
    return ApprovalToken(
        token_id=token_id,
        task_id=task_id,
        issued_at="",
        expires_at="",
        issued_by="",
        approved_by=approved_by,
        risk_level="",
        status="revoked",
        result="not_found",
    )


def validate_token(token_id: str, task_id: str) -> bool:
    _load_store()
    entry = _store.get(token_id)
    if not entry:
        return False
    if entry["task_id"] != task_id:
        return False
    if entry["status"] != "approved":
        return False
    expires = datetime.fromisoformat(entry["expires_at"])
    if _now() > expires:
        entry["status"] = "expired"
        entry["result"] = "expired"
        _append_event("token_expired", entry)
        return False
    return True


def revoke_token(token_id: str) -> None:
    _load_store()
    if token_id in _store:
        entry = _store[token_id]
        entry["status"] = "revoked"
        _append_event("token_revoked", entry)


def get_token(token_id: str) -> ApprovalToken | None:
    _load_store()
    entry = _store.get(token_id)
    return ApprovalToken(**entry) if entry else None


def issue_token_for_dev_reg(
    task_id: str,
    requested_by: str,
    risk_level: str,
    ttl_minutes: int = 30,
) -> ApprovalToken:
    """개발자 등록 신청 전용 승인 토큰 발행.

    issue_token() 은 TaskRequest / RiskAssessment 객체를 요구하지만,
    dev_reg 경로는 이를 생성하지 않으므로 최소 파라미터로 직접 발행한다.
    """
    _load_store()
    now = _now()
    token = ApprovalToken(
        token_id=str(uuid.uuid4()),
        public_id=_new_public_id(),
        task_id=task_id,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        issued_by=requested_by,
        approved_by=None,
        risk_level=risk_level,
        status="issued",
        used_at=None,
        result="",
    )
    entry = asdict(token)
    _store[token.token_id] = entry
    _append_event("token_created", entry)

    # Audit log: APPROVAL_ISSUED
    try:
        log_event(
            event_type="APPROVAL_ISSUED",
            task_id=token.task_id,
            risk_level=token.risk_level,
            actor=token.issued_by,
            action_type="",
            target="",
            note=f"public_id={token.public_id}",
        )
    except Exception as e:  # noqa: BLE001 - 승인 토큰 발급/승인/거절 감사로그(log_event) 기록 실패만 감싸는 except - 실제 승인/거절/만료 판정은 try 밖에서 이미 확정되어 상태값을 반환하므로 감사로그 실패가 승인 여부에 영향 없음
        logger.warning("개발자 등록 승인 발행 감사 기록 실패: %s", e)

    return token


def clear_rate_store() -> None:
    """테스트 전용: 승인/거절 rate limit 의 인메모리 카운터 초기화."""
    with _rate_lock:
        _rate_store.clear()
