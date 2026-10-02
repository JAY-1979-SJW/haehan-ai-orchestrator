"""L6 서비스 — 팩스 승인 PIN (사람만 아는 값). 승인·정지 해제는 PIN 을 알아야 한다.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §13
이유: 로컬 앱은 `AUTH_ENABLED=false` 라 API 만으로는 사람과 AI·다른 프로세스를 구분할 수 없다. 승인 버튼을 눌러도 PIN 이 맞아야
승인되므로, AI 에이전트나 같은 PC 의 다른 프로그램이 승인 API 를 직접 불러도 발송을 시작할 수 없다.
- PIN 은 salt + scrypt 해시로만 저장한다(원문 저장·로그 금지). PIN 이 설정되지 않았으면 승인하지 않는다(fail-closed).
- 연속 5회 틀리면 10분간 잠근다(맞으면 횟수 초기화).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from ai_orchestrator.persistence import fax_authorization_store as store

MIN_LENGTH = 6
MAX_FAILURES = 5
LOCK_MINUTES = 10
_PIN_KEY = "approval_pin"
_FAIL_KEY = "approval_pin_failures"
_LOCK_KEY = "approval_pin_locked_until"


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def is_configured() -> bool:
    return bool(store.get_flag(_PIN_KEY))


def locked_until() -> datetime | None:
    raw = store.get_flag(_LOCK_KEY)
    if not raw:
        return None
    until = datetime.fromisoformat(raw)
    return until if until > datetime.now(UTC) else None


def status() -> dict[str, object]:
    until = locked_until()
    return {"configured": is_configured(), "locked_until": until.isoformat(timespec="seconds") if until else None}


def _matches(pin: str) -> bool:
    stored = store.get_flag(_PIN_KEY) or ""
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        return False
    return hmac.compare_digest(_hash(pin, bytes.fromhex(parts[1])), parts[2])


def verify(pin: str) -> None:
    """맞으면 통과, 아니면 ValueError. 설정 전이면 거부(fail-closed), 연속 실패 시 잠근다."""
    if not is_configured():
        raise ValueError("승인 PIN 이 아직 없습니다 — 먼저 PIN 을 설정하세요")
    until = locked_until()
    if until:
        raise ValueError(
            f"PIN 을 여러 번 틀려 잠겼습니다 — {until.astimezone().strftime('%H:%M')} 이후 다시 시도하세요"
        )
    if pin and _matches(str(pin)):
        store.set_flag(_FAIL_KEY, "0")
        return
    failures = int(store.get_flag(_FAIL_KEY) or "0") + 1
    store.set_flag(_FAIL_KEY, str(failures))
    if failures >= MAX_FAILURES:
        store.set_flag(_LOCK_KEY, (datetime.now(UTC) + timedelta(minutes=LOCK_MINUTES)).isoformat())
        store.set_flag(_FAIL_KEY, "0")
        raise ValueError(f"PIN 을 {MAX_FAILURES}회 틀려 {LOCK_MINUTES}분간 잠겼습니다")
    raise ValueError(f"PIN 이 맞지 않습니다 (남은 시도 {MAX_FAILURES - failures}회)")


def set_pin(new_pin: str, *, old_pin: str = "", user: str = "") -> None:
    """처음 설정하거나(old_pin 불필요) 바꾼다(기존 PIN 필요)."""
    if len(new_pin or "") < MIN_LENGTH:
        raise ValueError(f"PIN 은 {MIN_LENGTH}자 이상이어야 합니다")
    if is_configured():
        verify(old_pin)
    salt = secrets.token_bytes(16)
    store.set_flag(_PIN_KEY, f"scrypt${salt.hex()}${_hash(new_pin, salt)}", user=user)
