"""L6 워크플로 — 하나팩스 자동 발송 (승인서 → 정책 판정 → 발송기 호출 → 이력 기록).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md

**발송기는 인자로 주입한다.** 이 모듈은 실제 전송 코드를 import 하지 않는다 — 테스트는 가짜 발송기만 쓰고, 운영 연결
(`scripts.hanafax.sender.send_fax`)은 호출부가 한다. 그래서 테스트가 실수로 실제 팩스를 보낼 수 없다.

안전 규칙
- 발송 직전과 **건마다** 정지(킬 스위치)·승인서 취소를 다시 확인한다(긴 배치 도중 정지 버튼이 눌리면 남은 건을 즉시 멈춘다).
- 전송 요청이 나간 뒤 결과가 불명확하면(예외·확인 불가) **재전송하지 않고 `unknown` 으로 기록**하고 그 번호는 사람이 확인할 때까지 멈춘다.
  요청이 나가기 전의 명확한 실패(자격증명 없음·번호 오류)만 `failed` 로 기록한다.
- 드라이런(승인서 live=False)은 발송기를 호출하지 않고 이력에 `dry_run` 만 남긴다.
- 로그·반환값에는 마스킹한 번호만 쓴다. 자격증명·문서 본문은 쓰지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from ai_orchestrator.gates import fax_send_policy as policy
from ai_orchestrator.persistence import fax_authorization_store as store

logger = logging.getLogger(__name__)

# 발송기: (수신번호 숫자, 수신자 이름, 제목) -> {"success": bool, "job_id": str|None, "message": str, "simulated": bool}
# 요청이 나가기 전의 명확한 실패는 {"success": False, "definite_failure": True, ...} 로 알린다.
Sender = Callable[[str, str, str], dict[str, Any]]


@dataclass
class RunResult:
    authorization_id: str
    decision: str  # send | skip | deny
    reason: str = ""
    dry_run: bool = False
    sent: int = 0
    failed: int = 0
    unknown: int = 0
    stopped_midway: bool = False
    skipped: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "decision": self.decision,
            "reason": self.reason,
            "dry_run": self.dry_run,
            "sent": self.sent,
            "failed": self.failed,
            "unknown": self.unknown,
            "stopped_midway": self.stopped_midway,
            "skipped": self.skipped,
        }


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hour, minute = str(value).split(":")
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        return default


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_policy_authorization(row: dict[str, Any]) -> policy.Authorization:
    return policy.Authorization(
        id=row["id"],
        recipients=tuple(row["recipients"]),
        subject=row["subject"],
        document_hash=row["document_hash"],
        approved_scope_hash=row.get("approved_scope_hash") or "",
        approved=row["approved"],
        revoked=row["revoked"],
        live=row["live"],
        valid_from=_parse_dt(row.get("valid_from")),
        valid_until=_parse_dt(row.get("valid_until")),
        max_per_run=int(row["max_per_run"]),
        max_per_day=int(row["max_per_day"]),
        max_total=int(row["max_total"]),
        allowed_start=_parse_hhmm(row["allowed_start"], time(9, 0)),
        allowed_end=_parse_hhmm(row["allowed_end"], time(18, 0)),
    )


def _day_start_iso(now: datetime) -> str:
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def _state(auth_id: str, document_hash: str, now: datetime) -> policy.State:
    return policy.State(
        now=now,
        kill_switch_on=store.kill_switch_on(),
        sent_today=store.count_sent(auth_id, since_iso=_day_start_iso(now)),
        sent_total=store.count_sent(auth_id),
        already_sent=store.sent_numbers(document_hash),
        opted_out=store.opt_out_numbers(),
        unknown_result=store.unknown_numbers(document_hash),
    )


def _still_allowed(auth_id: str) -> bool:
    """건마다 호출 — 정지되었거나 취소되었으면 즉시 멈춘다(저장소를 다시 읽는다)."""
    if store.kill_switch_on():
        return False
    row = store.get_authorization(auth_id)
    return bool(row) and row["approved"] and not row["revoked"]


def _record(auth_id: str, document_hash: str, number: str, status: str, job_id: str | None, message: str) -> None:
    store.record_send(
        store.SendRecord(
            authorization_id=auth_id,
            fax_digits=number,
            document_hash=document_hash,
            status=status,
            job_id=job_id,
            message=message,
        )
    )


def _send_one(sender: Sender, auth: policy.Authorization, recipient: dict[str, str]) -> str:
    """한 건 발송하고 이력 상태를 돌려준다(sent | failed | unknown). 재전송은 하지 않는다."""
    number = recipient["fax"]
    try:
        result = sender(number, recipient.get("name", ""), auth.subject)
    except Exception as exc:  # noqa: BLE001 - 요청이 나갔는지 알 수 없는 예외 — 재전송하지 않고 unknown 으로 멈춘다(중복 발송 방지)
        logger.warning("팩스 발송 결과 불명(%s): %s", policy.mask_number(number), type(exc).__name__)
        _record(auth.id, auth.document_hash, number, store.UNKNOWN, None, f"예외: {type(exc).__name__}")
        return store.UNKNOWN
    job_id = result.get("job_id")
    message = str(result.get("message", ""))
    if result.get("success") and job_id:
        _record(auth.id, auth.document_hash, number, store.SENT, str(job_id), message)
        return store.SENT
    if result.get("definite_failure"):
        _record(auth.id, auth.document_hash, number, store.FAILED, None, message)
        return store.FAILED
    # 성공 표시가 없고 접수번호도 없고 '명확한 실패'라고 알리지도 않았다 — 요청이 나갔을 수 있으므로 불명
    logger.warning("팩스 발송 결과 확정 불가(%s)", policy.mask_number(number))
    _record(auth.id, auth.document_hash, number, store.UNKNOWN, None, message or "결과 확인 불가")
    return store.UNKNOWN


def run(auth_id: str, sender: Sender, now: datetime) -> RunResult:
    """승인서 하나를 한 번 실행한다. 정책이 허용한 수신자에게만, 한도 안에서 발송한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        return RunResult(auth_id, policy.DENY, policy.NOT_APPROVED)
    auth = _to_policy_authorization(row)
    decision = policy.evaluate(auth, _state(auth_id, auth.document_hash, now))
    result = RunResult(
        auth_id,
        decision.action,
        decision.reason,
        dry_run=decision.dry_run,
        skipped=[{"number": n, "reason": r} for n, r in decision.skipped],
    )
    if decision.action != policy.SEND:
        return result

    for recipient in decision.to_send:
        if decision.dry_run:
            _record(auth_id, auth.document_hash, recipient["fax"], store.DRY_RUN, None, "드라이런 — 전송하지 않음")
            continue
        if not _still_allowed(auth_id):
            result.stopped_midway = True
            logger.warning("팩스 자동 발송 중단(정지 또는 취소): %s", auth_id)
            break
        status = _send_one(sender, auth, recipient)
        if status == store.SENT:
            result.sent += 1
        elif status == store.FAILED:
            result.failed += 1
        else:
            result.unknown += 1
    return result
