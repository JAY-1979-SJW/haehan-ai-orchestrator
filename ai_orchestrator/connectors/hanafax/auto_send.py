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
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

from ai_orchestrator.connectors.hanafax import send_policy as policy
from ai_orchestrator.connectors.hanafax import authorization_store as store

logger = logging.getLogger(__name__)

# 발송기: (수신번호 숫자, 수신자 이름, 제목) -> {"success": bool, "job_id": str|None, "message": str, "simulated": bool}
# 요청이 나가기 전의 명확한 실패는 {"success": False, "definite_failure": True, ...} 로 알린다.
Sender = Callable[[str, str, str], dict[str, Any]]
# 묶음 발송기(하나팩스 단체발송: 로그인·업로드 1회로 여러 번호): (수신자 목록[{fax,name}], 제목) ->
# {"success": bool, "job_id": str|None, "sent_faxes": [번호], "missing_faxes": [번호], "message": str, "definite_failure": bool?}
BulkSender = Callable[[list[dict[str, str]], str], dict[str, Any]]
BULK_CHUNK = 50


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
    """값이 있는데 읽지 못하면 예외 — 만료를 조용히 무시하지 않는다(fail-closed, 호출부가 deny 처리)."""
    if not value:
        return None
    return datetime.fromisoformat(value)


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
    """오늘 현지 자정을 **UTC 문자열**로 — 저장소 created_at(UTC)과 같은 형식이라 문자열 비교가 맞는다(날짜 경계 어긋남 방지)."""
    local_midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(UTC).isoformat(timespec="seconds")


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
    """건·묶음마다 호출 — 정지·취소뿐 아니라 허용 시간대·유효기간이 지났어도 멈춘다(저장소를 다시 읽는다)."""
    if store.kill_switch_on():
        return False
    row = store.get_authorization(auth_id)
    if not row or not row["approved"] or row["revoked"]:
        return False
    try:
        return not policy.recheck(_to_policy_authorization(row), datetime.now().astimezone())
    except ValueError:
        return False


_PHONE_LIKE = re.compile(r"\d{8,}")


def _safe_message(message: str) -> str:
    """이력에 남기는 메시지 — 사이트 본문이 섞여도 길이를 줄이고 긴 숫자열(번호·계정)은 가린다."""
    return _PHONE_LIKE.sub("********", " ".join(str(message).split()))[:120]


def _claim(auth_id: str, document_hash: str, number: str) -> None:
    """전송 직전 선점 기록. 기록하지 못하면 예외가 나므로 발송하지 않는다(fail-closed)."""
    _record(auth_id, document_hash, number, store.CLAIMED, None, "전송 요청 직전")


def _record(auth_id: str, document_hash: str, number: str, status: str, job_id: str | None, message: str) -> None:
    store.record_send(
        store.SendRecord(
            authorization_id=auth_id,
            fax_digits=number,
            document_hash=document_hash,
            status=status,
            job_id=job_id,
            message=_safe_message(message),
        )
    )


# 하나팩스 결과 화면의 성공 문구 — 엔진(`sender._run`)이 이 문구를 확인했을 때만 이 메시지로 돌려준다.
# 접수번호는 화면에서 못 읽는 경우가 있어(실측 2026-10-02) 필수로 두지 않는다. 사이트의 명시적 성공 확인이 있어야만 성공으로 본다.
SITE_SUCCESS_MESSAGE = "팩스 전송 완료"


def _confirmed(result: dict[str, Any]) -> bool:
    return bool(result.get("success")) and (bool(result.get("job_id")) or str(result.get("message", "")) == SITE_SUCCESS_MESSAGE)


def _send_one(sender: Sender, auth: policy.Authorization, recipient: dict[str, str]) -> str:
    """한 건 발송하고 이력 상태를 돌려준다(sent | failed | unknown). 재전송은 하지 않는다."""
    number = recipient["fax"]
    _claim(auth.id, auth.document_hash, number)
    try:
        result = sender(number, recipient.get("name", ""), auth.subject)
    except Exception as exc:  # noqa: BLE001 - 요청이 나갔는지 알 수 없는 예외 — 재전송하지 않고 unknown 으로 멈춘다(중복 발송 방지)
        logger.warning("팩스 발송 결과 불명(%s): %s", policy.mask_number(number), type(exc).__name__)
        _record(auth.id, auth.document_hash, number, store.UNKNOWN, None, f"예외: {type(exc).__name__}")
        return store.UNKNOWN
    job_id = result.get("job_id")
    message = str(result.get("message", ""))
    if _confirmed(result):
        _record(auth.id, auth.document_hash, number, store.SENT, str(job_id) if job_id else None, message)
        return store.SENT
    if result.get("definite_failure"):
        _record(auth.id, auth.document_hash, number, store.FAILED, None, message)
        return store.FAILED
    # 성공 표시가 없고 접수번호도 없고 '명확한 실패'라고 알리지도 않았다 — 요청이 나갔을 수 있으므로 불명
    logger.warning("팩스 발송 결과 확정 불가(%s)", policy.mask_number(number))
    _record(auth.id, auth.document_hash, number, store.UNKNOWN, None, message or "결과 확인 불가")
    return store.UNKNOWN


def _run(auth_id: str, sender: Sender, now: datetime) -> RunResult:
    """승인서 하나를 한 번 실행한다. 정책이 허용한 수신자에게만, 한도 안에서 발송한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        return RunResult(auth_id, policy.DENY, policy.NOT_APPROVED)
    try:
        auth = _to_policy_authorization(row)
    except ValueError:  # 유효기간 값을 읽지 못함 — 발송하지 않는다
        return RunResult(auth_id, policy.DENY, "invalid_validity_period")
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
        if recipient["fax"] in store.opt_out_numbers():  # 실행 중에 추가된 수신거부
            result.skipped.append({"number": policy.mask_number(recipient["fax"]), "reason": policy.OPTED_OUT})
            continue
        status = _send_one(sender, auth, recipient)
        if status == store.SENT:
            result.sent += 1
        elif status == store.FAILED:
            result.failed += 1
        else:
            result.unknown += 1
    return result


def _send_chunk(sender: BulkSender, auth: policy.Authorization, chunk: list[dict[str, str]]) -> tuple[int, int, int]:
    """한 묶음을 단체발송하고 (성공, 실패, 불명) 건수를 돌려준다. 재전송은 하지 않는다."""
    numbers = [r["fax"] for r in chunk]
    for n in numbers:
        _claim(auth.id, auth.document_hash, n)
    try:
        result = sender(chunk, auth.subject)
    except Exception as exc:  # noqa: BLE001 - 요청이 나갔는지 알 수 없는 예외 — 묶음 전체를 unknown 으로 멈춘다(중복 발송 방지)
        logger.warning("팩스 단체발송 결과 불명(%d건): %s", len(numbers), type(exc).__name__)
        for n in numbers:
            _record(auth.id, auth.document_hash, n, store.UNKNOWN, None, f"예외: {type(exc).__name__}")
        return 0, 0, len(numbers)
    job_id = result.get("job_id")
    message = str(result.get("message", ""))
    if _confirmed(result):
        accepted = {policy.normalize_number(n) for n in result.get("sent_faxes", [])}
        sent = failed = 0
        for n in numbers:
            if n in accepted:
                _record(auth.id, auth.document_hash, n, store.SENT, str(job_id) if job_id else None, message)
                sent += 1
            else:  # 사이트가 번호를 받아들이지 않아 접수 목록에 없다 — 전송 요청에 포함되지 않았다
                _record(auth.id, auth.document_hash, n, store.FAILED, None, "하나팩스에 등록되지 않은 번호")
                failed += 1
        return sent, failed, 0
    status = store.FAILED if result.get("definite_failure") else store.UNKNOWN
    for n in numbers:
        _record(auth.id, auth.document_hash, n, status, None, message or "결과 확인 불가")
    return (0, len(numbers), 0) if status == store.FAILED else (0, 0, len(numbers))


def _run_bulk(auth_id: str, sender: BulkSender, now: datetime, chunk_size: int) -> RunResult:
    """`run` 과 같은 정책 판정을 거치되, 허용된 수신자를 묶음(chunk)으로 단체발송한다. 묶음마다 정지·취소를 다시 확인한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        return RunResult(auth_id, policy.DENY, policy.NOT_APPROVED)
    try:
        auth = _to_policy_authorization(row)
    except ValueError:  # 유효기간 값을 읽지 못함 — 발송하지 않는다
        return RunResult(auth_id, policy.DENY, "invalid_validity_period")
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
    if decision.dry_run:
        for recipient in decision.to_send:
            _record(auth_id, auth.document_hash, recipient["fax"], store.DRY_RUN, None, "드라이런 — 전송하지 않음")
        return result
    targets = list(decision.to_send)
    for start in range(0, len(targets), chunk_size):
        if not _still_allowed(auth_id):
            result.stopped_midway = True
            logger.warning("팩스 자동 발송 중단(정지 또는 취소): %s", auth_id)
            break
        opted_out = store.opt_out_numbers()  # 실행 중에 추가된 수신거부도 남은 묶음에 적용한다
        chunk = [r for r in targets[start : start + chunk_size] if r["fax"] not in opted_out]
        if not chunk:
            continue
        sent, failed, unknown = _send_chunk(sender, auth, chunk)
        result.sent += sent
        result.failed += failed
        result.unknown += unknown
        if unknown:  # 결과 불명 — 다음 묶음도 보내지 않고 사람이 확인할 때까지 멈춘다
            result.stopped_midway = True
            break
    return result


# 같은 프로세스에서 발송 실행은 한 번에 하나만 — 사람이 '지금 발송'을 누르는 것과 예약 작업이 겹쳐도 같은 번호에 두 번 나가지 않는다.
# (멀티 프로세스로 띄우는 구성이면 이 락은 무의미하다 — 선점(claimed) 기록이 2차 방어선이지만 완전하지 않으므로 단일 프로세스로만 운영한다.)
_SEND_LOCK = threading.Lock()


def run(auth_id: str, sender: Sender, now: datetime) -> RunResult:
    if not _SEND_LOCK.acquire(blocking=False):
        return RunResult(auth_id, policy.DENY, "already_running")
    try:
        return _run(auth_id, sender, now)
    finally:
        _SEND_LOCK.release()


def run_bulk(auth_id: str, sender: BulkSender, now: datetime, chunk_size: int = BULK_CHUNK) -> RunResult:
    if not _SEND_LOCK.acquire(blocking=False):
        return RunResult(auth_id, policy.DENY, "already_running")
    try:
        return _run_bulk(auth_id, sender, now, chunk_size)
    finally:
        _SEND_LOCK.release()
