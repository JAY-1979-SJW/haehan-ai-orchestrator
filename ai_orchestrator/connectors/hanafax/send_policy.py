"""L2 정책 — 하나팩스 자동 발송 판정 (순수 함수, I/O 없음).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md

사용자가 미리 승인한 "발송 승인서"의 범위 안에서만 자동 발송한다. 이 모듈은 **판정만** 한다:
승인서 + 현재 상태(시각·이력·정지 여부 등)를 인자로 받아 `Decision` 을 돌려준다. 파일·DB·네트워크·환경변수에 접근하지 않는다.

fail-closed: 판정에 필요한 정보가 하나라도 없거나 모호하면 발송하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

SEND = "send"
SKIP = "skip"
DENY = "deny"

# 거부/건너뜀 사유 코드(감사 기록·화면 표시에 쓴다)
KILL_SWITCH = "kill_switch"
NOT_APPROVED = "not_approved"
REVOKED = "revoked"
EXPIRED = "expired"
NOT_YET_VALID = "not_yet_valid"
SCOPE_CHANGED = "scope_changed"
OUTSIDE_HOURS = "outside_allowed_hours"
LIMIT_REACHED = "limit_reached"
INVALID_NUMBER = "invalid_number"
OPTED_OUT = "opted_out"
ALREADY_SENT = "already_sent"
UNKNOWN_RESULT_PENDING = "unknown_result_pending"
DRY_RUN = "dry_run"

_DIGITS = re.compile(r"[^0-9]")
_MIN_DIGITS = 8
_MAX_DIGITS = 12


def normalize_number(raw: str) -> str:
    """팩스번호를 숫자만 남긴다(하이픈·공백 제거)."""
    return _DIGITS.sub("", str(raw or ""))


def is_valid_number(raw: str) -> bool:
    """국내 일반 팩스번호인지. 국제 접두(00)·휴대폰(01x)·유료 부가서비스(060/080)는 거부한다(요금·오발송 방지)."""
    digits = normalize_number(raw)
    return (
        _MIN_DIGITS <= len(digits) <= _MAX_DIGITS
        and digits.startswith("0")
        and not digits.startswith(("00", "01", "060", "080"))
    )


_ALLOWED_INPUT = re.compile(r"^[0-9\s().\-]+$")


def parse_number(raw: object) -> str | None:
    """사용자·파일 입력의 팩스번호를 검증해 숫자만 돌려준다. 못 쓰는 입력이면 None.

    숫자·공백·하이픈·괄호·점만 허용한다 — '#5'(내선)·'+82'·글자가 섞이면 숫자만 남겨 다른 번호가 되므로 통째로 거부한다.
    """
    text = str(raw or "").strip()
    if not _ALLOWED_INPUT.match(text):
        return None
    digits = normalize_number(text)
    return digits if is_valid_number(digits) else None


def mask_number(raw: str) -> str:
    """로그·화면 표시용 마스킹: 앞 3자리와 뒤 2자리만 남긴다."""
    digits = normalize_number(raw)
    if len(digits) <= 5:
        return "*" * len(digits)
    return digits[:3] + "*" * (len(digits) - 5) + digits[-2:]


def scope_hash(recipients: Iterable[dict[str, str]], subject: str, document_hash: str) -> str:
    """승인 범위 해시. 수신자(번호·이름)·제목·문서 해시를 정규화해 SHA-256 으로 묶는다.

    수신자 순서·번호 표기(하이픈 유무)·앞뒤 공백이 달라도 같은 내용이면 같은 해시가 되고,
    번호·이름·제목·문서 중 하나라도 달라지면 다른 해시가 된다.
    """
    normalized = sorted((normalize_number(r.get("fax", "")), str(r.get("name", "")).strip()) for r in recipients)
    payload = json.dumps(
        {"recipients": normalized, "subject": str(subject).strip(), "document": str(document_hash).strip()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Authorization:
    """사용자가 승인한 발송 범위(저장소에서 읽은 값)."""

    id: str
    recipients: tuple[dict[str, str], ...]
    subject: str
    document_hash: str
    approved_scope_hash: str  # 승인 당시 계산한 범위 해시
    approved: bool
    revoked: bool
    live: bool  # False 면 드라이런(실제 전송 안 함)
    valid_from: datetime | None
    valid_until: datetime | None
    max_per_run: int
    max_per_day: int
    max_total: int
    allowed_start: time  # 허용 시간대(현지 시각)
    allowed_end: time


@dataclass(frozen=True)
class State:
    """판정 시점의 현재 상태(호출자가 저장소에서 읽어 넘긴다)."""

    now: datetime  # 현지 시각(타임존 포함 가능)
    kill_switch_on: bool
    sent_today: int  # 이 승인서로 오늘 보낸 건수
    sent_total: int  # 이 승인서로 지금까지 보낸 건수
    already_sent: Collection[str]  # (이 문서 해시로) 이미 성공한 수신번호(숫자만)
    opted_out: Collection[str]  # 수신거부 번호(숫자만)
    unknown_result: Collection[str]  # 결과가 불명확해 "확인 필요" 로 멈춘 수신번호(숫자만)


@dataclass(frozen=True)
class Decision:
    action: str  # SEND | SKIP | DENY
    reason: str = ""
    # SEND 일 때만 의미: 이번 실행에서 실제로 보낼 수신자(순서 유지, 한도 적용 후)
    to_send: tuple[dict[str, str], ...] = ()
    # 건너뛴 수신자와 사유(감사 기록용): [(마스킹 번호, 사유)]
    skipped: tuple[tuple[str, str], ...] = field(default=())
    # 드라이런이면 True — 실제 전송하지 않고 계획만 만든다
    dry_run: bool = False


def _within_hours(now: datetime, start: time, end: time) -> bool:
    current = now.time().replace(tzinfo=None)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end  # 자정을 넘는 시간대


def _as_utc_naive_compare(value: datetime, now: datetime) -> tuple[datetime, datetime]:
    """타임존 유무가 섞여 있으면 비교가 깨지므로 같은 기준으로 맞춘다."""
    if value.tzinfo is None and now.tzinfo is not None:
        return value.replace(tzinfo=now.tzinfo), now
    if value.tzinfo is not None and now.tzinfo is None:
        return value, now.replace(tzinfo=value.tzinfo)
    return value, now


def _gate_authorization(auth: Authorization, state: State) -> Decision | None:
    """승인서 자체의 상태(정지·승인·취소·기간·범위). 통과하면 None, 막으면 Decision."""
    if state.kill_switch_on:
        return Decision(DENY, KILL_SWITCH)
    if not auth.approved:
        return Decision(DENY, NOT_APPROVED)
    if auth.revoked:
        return Decision(DENY, REVOKED)
    if auth.valid_from is not None:
        start, now = _as_utc_naive_compare(auth.valid_from, state.now)
        if now < start:
            return Decision(SKIP, NOT_YET_VALID)
    if auth.valid_until is not None:
        end, now = _as_utc_naive_compare(auth.valid_until, state.now)
        if now > end:
            return Decision(DENY, EXPIRED)
    current = scope_hash(auth.recipients, auth.subject, auth.document_hash)
    if current != auth.approved_scope_hash:
        # 승인한 뒤 수신자·제목·문서가 바뀌었다 — 재승인 전에는 절대 보내지 않는다
        return Decision(DENY, SCOPE_CHANGED)
    if not _within_hours(state.now, auth.allowed_start, auth.allowed_end):
        return Decision(SKIP, OUTSIDE_HOURS)
    return None


def recheck(auth: Authorization, now: datetime) -> str:
    """긴 실행 도중 다시 확인한다 — 승인·취소·기간·범위·허용 시간대. 막아야 하면 사유, 계속해도 되면 빈 문자열."""
    blocked = _gate_authorization(auth, State(now, False, 0, 0, (), (), ()))
    return blocked.reason if blocked is not None else ""


def _recipient_skip_reason(number: str, state: State) -> str:
    if not is_valid_number(number):
        return INVALID_NUMBER
    if number in state.opted_out:
        return OPTED_OUT
    if number in state.unknown_result:
        return UNKNOWN_RESULT_PENDING
    if number in state.already_sent:
        return ALREADY_SENT
    return ""


def _remaining_capacity(auth: Authorization, state: State) -> int:
    return max(0, min(auth.max_per_run, auth.max_per_day - state.sent_today, auth.max_total - state.sent_total))


def evaluate(auth: Authorization, state: State) -> Decision:
    """승인서와 현재 상태로 이번 실행의 발송 여부·대상을 판정한다."""
    blocked = _gate_authorization(auth, state)
    if blocked is not None:
        return blocked

    capacity = _remaining_capacity(auth, state)
    seen: set[str] = set()
    to_send: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for recipient in auth.recipients:
        number = normalize_number(recipient.get("fax", ""))
        if number in seen:
            skipped.append((mask_number(number), ALREADY_SENT))  # 목록 안 중복은 한 번만
            continue
        seen.add(number)
        reason = _recipient_skip_reason(number, state)
        if reason:
            skipped.append((mask_number(number), reason))
            continue
        if len(to_send) >= capacity:
            skipped.append((mask_number(number), LIMIT_REACHED))
            continue
        to_send.append({"fax": number, "name": str(recipient.get("name", "")).strip()})

    if not to_send:
        return Decision(SKIP, LIMIT_REACHED if capacity == 0 else "nothing_to_send", skipped=tuple(skipped))
    return Decision(SEND, "", to_send=tuple(to_send), skipped=tuple(skipped), dry_run=not auth.live)


def describe(decision: Decision, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """감사 기록·화면용 요약(번호는 이미 마스킹돼 있다)."""
    out: dict[str, Any] = {
        "action": decision.action,
        "reason": decision.reason,
        "dry_run": decision.dry_run,
        "send_count": len(decision.to_send),
        "skipped": [{"number": n, "reason": r} for n, r in decision.skipped],
    }
    if extra:
        out.update(extra)
    return out
