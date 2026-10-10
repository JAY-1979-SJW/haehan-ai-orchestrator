"""L6 워크플로 — 메일 순차 대량 발송 (승인서 → 정책 판정 → **한 명씩 차례로** 발송 → 이력 기록).

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md (하나팩스 `hanafax_auto_send` 와 같은 뼈대)

**발송기는 인자로 주입한다.** 이 모듈은 실제 SMTP 코드를 import 하지 않는다 — 테스트는 가짜 발송기만 쓰고, 운영 연결
(`scripts.naver.mail.imap.bulk_sender.BulkSmtp.send`)은 서비스가 맺는다. 그래서 테스트가 실수로 실제 메일을 보낼 수 없다.

안전 규칙
- 한 통을 보낸 뒤 **간격(±20% 무작위)** 만큼 기다렸다가 다음 사람에게 보낸다. 건마다 정지·취소·멈춤·허용 시간대를 다시 확인한다.
- 결과가 불확실(`send_unknown`)하면 그 주소는 `unknown` 으로 남기고 **재시도하지 않으며 회차를 멈춘다**(승인서 `paused`).
- 로그인 거부·한도/차단 응답은 즉시 회차를 멈춘다. 일시 오류는 연속 3회에서 멈춘다. 수신자 한 명만 거부된 경우는 다음 사람으로 계속한다.
- 멈춘 승인서는 사람이 재개하기 전에는 정책이 보내지 않는다.
- 드라이런(승인서 live=False)은 발송기를 호출하지 않고 이력에 `dry_run` 만 남긴다.
- 로그·반환값에는 마스킹한 주소만 쓴다. 자격증명·본문은 쓰지 않는다.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as dtime
from typing import Any

from ai_orchestrator.connectors.naver_mail import bulk_policy as policy
from ai_orchestrator.connectors.naver_mail import bulk_store as store
from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import sender as smtp_draft

logger = logging.getLogger(__name__)

# 발송기: Draft -> {"ok": bool, "error": str, "code": int|None, "message": str, "refused": list}
Send = Callable[[smtp_draft.Draft], dict[str, Any]]


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
    paused_reason: str = ""
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
            "paused_reason": self.paused_reason,
            "skipped": self.skipped,
        }


def _parse_hhmm(value: str, default: dtime) -> dtime:
    try:
        hh, mm = str(value).split(":")
        return dtime(int(hh), int(mm))
    except (ValueError, TypeError):
        return default


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def to_policy_authorization(row: dict[str, Any]) -> policy.Authorization:
    return policy.Authorization(
        id=row["id"],
        recipients=tuple(row["recipients"]),
        subject=row["subject"],
        body=row["body"],
        attachments_hash=row["attachments_hash"],
        kind=row["kind"],
        approved_scope_hash=row["approved_scope_hash"] or "",
        approved=row["approved"],
        revoked=row["revoked"],
        paused=row["paused"],
        live=row["live"],
        valid_from=_parse_dt(row["valid_from"]),
        valid_until=_parse_dt(row["valid_until"]),
        max_per_run=row["max_per_run"],
        max_per_day=row["max_per_day"],
        max_total=row["max_total"],
        allowed_start=_parse_hhmm(row["allowed_start"], dtime(9, 0)),
        allowed_end=_parse_hhmm(row["allowed_end"], dtime(18, 0)),
    )


def _day_start_utc_iso(now: datetime) -> str:
    """오늘 0시(현지)를 발송 이력의 시각 형식(UTC)으로 바꾼다 — 형식이 다르면 문자열 비교가 어긋난다."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat(timespec="seconds")


def _state(auth: policy.Authorization, now: datetime, document_hash: str) -> policy.State:
    return policy.State(
        now=now,
        kill_switch_on=store.kill_switch_on(),
        sent_today=store.count_sent(auth.id, since_iso=_day_start_utc_iso(now)),
        sent_total=store.count_sent(auth.id),
        already_sent=store.sent_emails(document_hash),
        opted_out=store.opt_out_emails(),
        unknown_result=store.unknown_emails(document_hash),
    )


def _still_allowed(auth_id: str, now: datetime) -> bool:
    """건마다 호출 — 정지·취소·멈춤·시간대를 저장소에서 다시 읽어 확인한다."""
    if store.kill_switch_on():
        return False
    row = store.get_authorization(auth_id)
    if not row or not row["approved"] or row["revoked"] or row["paused"]:
        return False
    start = _parse_hhmm(row["allowed_start"], dtime(9, 0))
    end = _parse_hhmm(row["allowed_end"], dtime(18, 0))
    return policy.in_allowed_hours(now, start, end)


def _record(auth: policy.Authorization, document_hash: str, email: str, status: str, message: str) -> None:
    store.record_send(store.SendRecord(auth.id, email, document_hash, status, message))


def _build_draft(
    account: str, auth: policy.Authorization, recipient: dict[str, str], uploads: list[att.Upload]
) -> smtp_draft.Draft:
    fields = {"이름": recipient.get("name", ""), "업체명": recipient.get("company", "")}
    return smtp_draft.make_draft(
        account,
        recipient["email"],
        policy.render(auth.subject, fields),
        policy.render(auth.body, fields),
        uploads=uploads,
    )


def _error_kind(result: dict[str, Any]) -> str:
    error = result.get("error", "")
    if error in ("auth_failed", "no_password"):
        return policy.ERR_AUTH
    if error == "connect_failed":
        return policy.ERR_TRANSIENT
    return policy.classify_error(result.get("code"), str(result.get("message", "")))


def _apply_result(
    auth: policy.Authorization, document_hash: str, email: str, result: dict[str, Any], out: RunResult, streak: int
) -> tuple[int, str]:
    """발송 결과를 기록하고 (연속 실패 수, 멈출 사유) 를 돌려준다."""
    masked = policy.mask_email(email)
    if result.get("ok"):
        if result.get("refused"):
            _record(auth, document_hash, email, store.FAILED, "수신자 거부")
            out.failed += 1
            return 0, ""
        _record(auth, document_hash, email, store.SENT, "")
        out.sent += 1
        return 0, ""
    if result.get("error") == "send_unknown":
        logger.warning("메일 발송 결과 불명(%s)", masked)
        _record(auth, document_hash, email, store.UNKNOWN, str(result.get("message", ""))[:200])
        out.unknown += 1
        return streak, "unknown_result"
    kind = _error_kind(result)
    if kind != policy.ERR_AUTH:  # 로그인 거부는 그 수신자의 문제가 아니므로 이력에 남기지 않아 나중에 다시 보낼 수 있다
        _record(auth, document_hash, email, store.FAILED, str(result.get("message", ""))[:200])
        out.failed += 1
    streak = streak + 1 if kind == policy.ERR_TRANSIENT else 0
    return streak, policy.should_pause(kind, streak)


def _stop(out: RunResult, auth_id: str, reason: str) -> None:
    store.pause(auth_id, reason)
    out.paused_reason = reason
    out.stopped_midway = True
    logger.warning("메일 대량 발송 멈춤(%s): %s", reason, auth_id)


def run(
    auth_id: str,
    send: Send,
    now_fn: Callable[[], datetime],
    *,
    uploads: list[att.Upload] | None = None,
    sleep: Callable[[float], None] | None = None,
    rand: Callable[[], float] = random.random,
) -> RunResult:
    """승인서 하나를 한 번 실행한다. 정책이 허용한 수신자에게만, 한도 안에서, 한 명씩 차례로 보낸다."""
    row = store.get_authorization(auth_id)
    if row is None:
        return RunResult(auth_id, policy.DENY, policy.NOT_APPROVED)
    auth = to_policy_authorization(row)
    decision = policy.evaluate(auth, _state(auth, now_fn(), row["document_hash"]))
    out = RunResult(
        auth_id,
        decision.action,
        decision.reason,
        dry_run=decision.dry_run,
        skipped=[{"address": a, "reason": r} for a, r in decision.skipped],
    )
    if decision.action != policy.SEND:
        return out

    wait = sleep or time.sleep  # 호출 시점에 해석한다(기본값으로 묶으면 시험에서 time.sleep 을 바꿔도 먹히지 않는다)
    streak, sent_any = 0, False
    for recipient in decision.to_send:
        email = recipient["email"]
        if decision.dry_run:
            _record(auth, row["document_hash"], email, store.DRY_RUN, "드라이런 — 전송하지 않음")
            continue
        if sent_any:
            wait(policy.next_delay_sec(row["interval_sec"], rand()))
        if not _still_allowed(auth_id, now_fn()):
            out.stopped_midway = True
            break
        try:
            draft = _build_draft(row["account"], auth, recipient, uploads or [])
        except ValueError as exc:  # 이 수신자의 내용이 발송 규칙에 맞지 않음 — 다음 사람 계속
            _record(auth, row["document_hash"], email, store.FAILED, str(exc)[:200])
            out.failed += 1
            continue
        try:
            result = send(draft)
        except Exception as exc:  # noqa: BLE001 - 요청이 나갔는지 알 수 없는 예외 — 재시도하지 않고 unknown 으로 멈춘다(중복 발송 방지)
            result = {"ok": False, "error": "send_unknown", "message": f"예외: {type(exc).__name__}"}
        sent_any = True
        streak, pause_reason = _apply_result(auth, row["document_hash"], email, result, out, streak)
        if pause_reason:
            _stop(out, auth_id, pause_reason)
            break
    return out
