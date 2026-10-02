"""L2 정책 — 메일 순차 대량 발송 판정 (순수 함수, I/O 없음).

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md (하나팩스 `fax_send_policy` 와 같은 뼈대)

사용자가 미리 승인한 "대량 발송 승인서" 범위 안에서만 **한 명씩 차례로** 보낸다. 이 모듈은 판정만 한다:
승인서 + 현재 상태를 받아 `Decision` 을 돌려주고, 파일·DB·네트워크·환경변수에 접근하지 않는다.
fail-closed: 필요한 정보가 하나라도 없거나 모호하면 보내지 않는다.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

SEND = "send"
SKIP = "skip"
DENY = "deny"

# 거부/건너뜀 사유 코드
KILL_SWITCH = "kill_switch"
NOT_APPROVED = "not_approved"
REVOKED = "revoked"
PAUSED = "paused"
EXPIRED = "expired"
NOT_YET_VALID = "not_yet_valid"
SCOPE_CHANGED = "scope_changed"
OUTSIDE_HOURS = "outside_allowed_hours"
LIMIT_REACHED = "limit_reached"
INVALID_ADDRESS = "invalid_address"
OPTED_OUT = "opted_out"
ALREADY_SENT = "already_sent"
UNKNOWN_RESULT_PENDING = "unknown_result_pending"

# 메일 성격
KIND_TRANSACTION = "transaction"  # 거래·업무 안내
KIND_PROMO = "promo"  # 홍보·광고
KINDS = (KIND_TRANSACTION, KIND_PROMO)

# 발송 오류 분류(SMTP 응답 → 다음 행동)
ERR_RECIPIENT = "recipient"  # 이 수신자만 거부됨 — 다음 사람 계속
ERR_TRANSIENT = "transient"  # 일시 오류 — 연속 실패 계수에 반영
ERR_LIMIT = "limit"  # 한도·차단·스팸 의심 — 즉시 회차 중단
ERR_AUTH = "auth"  # 로그인 거부 — 즉시 회차 중단

MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_INTERVAL_SEC = 30
MIN_INTERVAL_SEC = 5
MAX_INTERVAL_SEC = 3600
JITTER_RATIO = 0.2
DEFAULT_DAILY_CAP = 200
HARD_DAILY_CAP = 5000
AD_MARK = "(광고)"
OPT_OUT_HINT = "수신거부"

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_PLACEHOLDER = re.compile(r"\{(이름|업체명)\}")
_LIMIT_WORDS = (
    "quota",
    "limit",
    "too many",
    "rate",
    "spam",
    "blocked",
    "blacklist",
    "exceed",
    "초과",
    "제한",
    "차단",
    "스팸",
)


def normalize_email(raw: str) -> str:
    return str(raw or "").strip().lower()


def is_valid_email(raw: str) -> bool:
    value = normalize_email(raw)
    return len(value) <= 254 and bool(_EMAIL.match(value))


def mask_email(raw: str) -> str:
    """로그·화면 표시용: 아이디의 앞부분만 남기고(3글자 이하는 1글자, 그 이상은 2글자) 도메인은 그대로 둔다."""
    value = normalize_email(raw)
    local, _, domain = value.partition("@")
    if not domain:
        return "*" * len(value)
    keep = 1 if len(local) <= 3 else 2
    return local[:keep] + "*" * max(1, len(local) - keep) + "@" + domain


def scope_hash(recipients: Iterable[dict[str, str]], subject: str, body: str, attachments_hash: str, kind: str) -> str:
    """승인 범위 해시. 수신자·제목·본문·첨부·성격 중 하나라도 달라지면 달라진다(순서·대소문자·공백은 무시)."""
    normalized = sorted(
        (normalize_email(r.get("email", "")), str(r.get("name", "")).strip(), str(r.get("company", "")).strip())
        for r in recipients
    )
    payload = json.dumps(
        {
            "recipients": normalized,
            "subject": str(subject).strip(),
            "body": str(body).strip(),
            "attachments": str(attachments_hash).strip(),
            "kind": kind,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def document_hash(subject: str, body: str, attachments_hash: str) -> str:
    """수신자와 무관한 '내용' 해시 — 같은 내용을 같은 사람에게 두 번 보내지 않는 기준."""
    payload = json.dumps(
        {"subject": str(subject).strip(), "body": str(body).strip(), "attachments": str(attachments_hash).strip()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── 개별화·성격별 필수 항목 ─────────────────────────────────────────────────


def render(template: str, fields: dict[str, str], *, html: bool = False) -> str:
    """`{이름}`·`{업체명}` 치환. 값이 없으면 빈 문자열. HTML 본문이면 값을 이스케이프한다(주입 방지)."""

    def _sub(m: re.Match[str]) -> str:
        value = str(fields.get(m.group(1), "") or "").strip()
        return html_lib.escape(value) if html else value

    return _PLACEHOLDER.sub(_sub, template)


def compliance_errors(kind: str, subject: str, body: str) -> list[str]:
    """성격별 필수 항목 점검. 홍보·광고는 제목 `(광고)` 표기와 수신거부 안내 문구가 있어야 한다."""
    if kind not in KINDS:
        return [f"메일 성격은 {', '.join(KINDS)} 중 하나여야 합니다"]
    errors: list[str] = []
    if kind == KIND_PROMO:
        if not subject.lstrip().startswith(AD_MARK):
            errors.append(f"홍보·광고 메일은 제목이 '{AD_MARK}' 로 시작해야 합니다")
        if OPT_OUT_HINT not in body:
            errors.append(f"홍보·광고 메일은 본문에 '{OPT_OUT_HINT}' 안내 문구가 있어야 합니다")
    return errors


# ── 순차 발송 보조 판정 ────────────────────────────────────────────────────


def next_delay_sec(interval_sec: int, rand01: float) -> float:
    """다음 발송까지 기다릴 초. 간격 ±20% 무작위(`rand01` 은 0~1, 호출자가 주입 — 테스트 가능)."""
    base = max(MIN_INTERVAL_SEC, min(int(interval_sec), MAX_INTERVAL_SEC))
    factor = 1 + JITTER_RATIO * (2 * min(1.0, max(0.0, rand01)) - 1)
    return round(base * factor, 3)


def classify_error(code: int | None, message: str = "") -> str:
    """SMTP 응답 코드·문구로 오류를 분류한다. 모르면 일시 오류(연속 실패 계수에만 반영)."""
    text = str(message or "").lower()
    auth_failed = code in (530, 534, 535, 538) or ("auth" in text and "fail" in text)
    if auth_failed:
        return ERR_AUTH
    if any(w in text for w in _LIMIT_WORDS):
        return ERR_LIMIT
    if code in (550, 551, 553, 501, 511, 512, 513):
        return ERR_RECIPIENT
    return ERR_TRANSIENT


def should_pause(error_kind: str, consecutive_failures: int) -> str:
    """회차를 멈춰야 하면 사유 문자열, 계속해도 되면 빈 문자열."""
    if error_kind == ERR_AUTH:
        return "auth_failed"
    if error_kind == ERR_LIMIT:
        return "limit_or_block"
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return "consecutive_failures"
    return ""


# ── 승인서 판정 ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Authorization:
    """사용자가 승인한 발송 범위(저장소에서 읽은 값)."""

    id: str
    recipients: tuple[dict[str, str], ...]
    subject: str
    body: str
    attachments_hash: str
    kind: str
    approved_scope_hash: str
    approved: bool
    revoked: bool
    paused: bool
    live: bool  # False 면 드라이런
    valid_from: datetime | None
    valid_until: datetime | None
    max_per_run: int
    max_per_day: int
    max_total: int
    allowed_start: time
    allowed_end: time


@dataclass(frozen=True)
class State:
    now: datetime
    kill_switch_on: bool
    sent_today: int
    sent_total: int
    already_sent: Collection[str]  # (이 내용 해시로) 이미 성공한 주소(정규화)
    opted_out: Collection[str]
    unknown_result: Collection[str]


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str = ""
    to_send: tuple[dict[str, str], ...] = ()
    skipped: tuple[tuple[str, str], ...] = field(default=())
    dry_run: bool = False


def _within_hours(now: datetime, start: time, end: time) -> bool:
    current = now.time().replace(tzinfo=None)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def in_allowed_hours(now: datetime, start: time, end: time) -> bool:
    """실행기가 건마다 허용 시간대를 다시 확인할 때 쓴다."""
    return _within_hours(now, start, end)


def _compare_aware(value: datetime, now: datetime) -> tuple[datetime, datetime]:
    if value.tzinfo is None and now.tzinfo is not None:
        return value.replace(tzinfo=now.tzinfo), now
    if value.tzinfo is not None and now.tzinfo is None:
        return value, now.replace(tzinfo=value.tzinfo)
    return value, now


def _gate_period(auth: Authorization, state: State) -> Decision | None:
    """유효 기간·허용 시간대."""
    if auth.valid_from is not None:
        start, now = _compare_aware(auth.valid_from, state.now)
        if now < start:
            return Decision(SKIP, NOT_YET_VALID)
    if auth.valid_until is not None:
        end, now = _compare_aware(auth.valid_until, state.now)
        if now > end:
            return Decision(DENY, EXPIRED)
    if not _within_hours(state.now, auth.allowed_start, auth.allowed_end):
        return Decision(SKIP, OUTSIDE_HOURS)
    return None


def _gate_authorization(auth: Authorization, state: State) -> Decision | None:
    """승인서 자체의 상태(정지·승인·취소·멈춤·범위·기간). 통과하면 None."""
    if state.kill_switch_on:
        return Decision(DENY, KILL_SWITCH)
    if not auth.approved:
        return Decision(DENY, NOT_APPROVED)
    if auth.revoked:
        return Decision(DENY, REVOKED)
    if auth.paused:
        return Decision(DENY, PAUSED)  # 자동 멈춤 후에는 사람이 재개하기 전까지 보내지 않는다
    if (
        scope_hash(auth.recipients, auth.subject, auth.body, auth.attachments_hash, auth.kind)
        != auth.approved_scope_hash
    ):
        return Decision(DENY, SCOPE_CHANGED)
    return _gate_period(auth, state)


def _recipient_skip_reason(address: str, state: State) -> str:
    if not is_valid_email(address):
        return INVALID_ADDRESS
    if address in state.opted_out:
        return OPTED_OUT
    if address in state.unknown_result:
        return UNKNOWN_RESULT_PENDING
    if address in state.already_sent:
        return ALREADY_SENT
    return ""


def remaining_capacity(auth: Authorization, state: State) -> int:
    return max(0, min(auth.max_per_run, auth.max_per_day - state.sent_today, auth.max_total - state.sent_total))


def evaluate(auth: Authorization, state: State) -> Decision:
    """승인서와 현재 상태로 이번 회차의 발송 여부·대상(순서 유지)을 판정한다."""
    blocked = _gate_authorization(auth, state)
    if blocked is not None:
        return blocked

    capacity = remaining_capacity(auth, state)
    seen: set[str] = set()
    to_send: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for recipient in auth.recipients:
        address = normalize_email(recipient.get("email", ""))
        if address in seen:
            skipped.append((mask_email(address), ALREADY_SENT))
            continue
        seen.add(address)
        reason = _recipient_skip_reason(address, state)
        if reason:
            skipped.append((mask_email(address), reason))
            continue
        if len(to_send) >= capacity:
            skipped.append((mask_email(address), LIMIT_REACHED))
            continue
        to_send.append(
            {
                "email": address,
                "name": str(recipient.get("name", "")).strip(),
                "company": str(recipient.get("company", "")).strip(),
            }
        )

    if not to_send:
        return Decision(SKIP, LIMIT_REACHED if capacity == 0 else "nothing_to_send", skipped=tuple(skipped))
    return Decision(SEND, "", to_send=tuple(to_send), skipped=tuple(skipped), dry_run=not auth.live)


def describe(decision: Decision, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """감사 기록·화면용 요약(주소는 이미 마스킹돼 있다)."""
    out: dict[str, Any] = {
        "action": decision.action,
        "reason": decision.reason,
        "dry_run": decision.dry_run,
        "send_count": len(decision.to_send),
        "skipped": [{"address": a, "reason": r} for a, r in decision.skipped],
    }
    if extra:
        out.update(extra)
    return out
