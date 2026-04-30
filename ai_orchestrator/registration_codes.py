"""로컬 에이전트 등록코드 (REGCODE-1).

데스크톱 agent 가 admin Basic Auth 없이 1회용 코드로 등록할 수 있게 하는
in-memory 저장소 + 발급/교환/조회/폐기 헬퍼.

보안:
  - registration_code 원문은 발급 직후 1회만 호출자에게 반환된다.
  - 서버는 SHA-256(salt + normalized_code) 만 저장한다.
  - 코드 원문/해시/salt 는 list/detail/audit 응답에 노출되지 않는다.
  - 1회 사용 후 status=used 로 잠긴다. 만료/폐기/사용 모두 일관 generic
    "invalid_registration_code" 결과로 처리해 외부에서 상태를 구분하지 못하게 한다.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


# 사람이 손으로 입력 가능한 문자 — 0/1/I/O 등 혼동 문자 제외.
_CODE_ALPHABET: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN: int = 12  # 4-4-4 그루핑 → 12 chars × log2(32) = 60bit 엔트로피

DEFAULT_TTL_MINUTES: int = 30
MAX_TTL_MINUTES: int = 60 * 24  # 24h

# 교환 시 generic 에러 메시지 (오류 원인을 외부에 노출하지 않음).
INVALID_CODE_MESSAGE: str = "invalid_registration_code"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _generate_code() -> str:
    chars = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
    return f"{chars[0:4]}-{chars[4:8]}-{chars[8:12]}"


def _normalize_code(raw: str) -> str:
    """입력 코드를 비교 가능한 정규형으로 변환.

    - 대소문자 무시
    - 하이픈/공백 등 비-알파벳 문자 제거
    - 알파벳 외 문자가 섞이면 그 결과는 정규형 길이 검사에서 탈락한다.
    """
    if not raw:
        return ""
    return "".join(c for c in raw.upper() if c in _CODE_ALPHABET)


def _hash_code(normalized: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + normalized).encode("utf-8")).hexdigest()


# ── 데이터 모델 ──────────────────────────────────────────────────────────

@dataclass
class RegistrationCode:
    code_id: str
    label: str
    code_hash: str
    code_salt: str
    allowed_actions: list[str]
    expires_at: str          # ISO
    created_at: str
    issued_by: str
    issuer_role: str
    note: str = ""
    used_at: str = ""
    used_by_agent_id: str = ""
    revoked_at: str = ""
    revoked_by: str = ""

    def status(self, now: Optional[datetime] = None) -> str:
        if self.revoked_at:
            return "revoked"
        if self.used_at:
            return "used"
        ts_now = now if now is not None else _now()
        try:
            exp = datetime.fromisoformat(self.expires_at)
        except (TypeError, ValueError):
            return "expired"
        if ts_now >= exp:
            return "expired"
        return "active"

    def to_safe(self) -> dict:
        """list/detail 응답용 — code 원문/hash/salt 미포함."""
        return {
            "code_id": self.code_id,
            "label": self.label,
            "allowed_actions": list(self.allowed_actions),
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "issued_by": self.issued_by,
            "issuer_role": self.issuer_role,
            "note": self.note,
            "status": self.status(),
            "used_at": self.used_at,
            "used_by_agent_id": self.used_by_agent_id,
            "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by,
        }


# ── 저장소 ───────────────────────────────────────────────────────────────

_lock = threading.Lock()
_codes: dict[str, RegistrationCode] = {}


def clear() -> None:
    """테스트 전용: 저장소 초기화."""
    with _lock:
        _codes.clear()


# ── 발급 ─────────────────────────────────────────────────────────────────

class InvalidTTLError(ValueError):
    """expires_in_minutes 가 허용 범위를 벗어남."""


@dataclass
class IssueResult:
    code: RegistrationCode
    registration_code: str  # 평문 — 호출자가 1회만 응답에 포함하고 폐기


def issue_code(
    *,
    label: str,
    expires_in_minutes: int = DEFAULT_TTL_MINUTES,
    allowed_actions: Optional[list[str]] = None,
    note: str = "",
    issued_by: str,
    issuer_role: str = "",
) -> IssueResult:
    """새 등록코드 발급. 평문은 결과 객체에만 1회 노출.

    - expires_in_minutes 는 [1, MAX_TTL_MINUTES] 범위여야 한다.
    - allowed_actions 는 그대로 저장된다 (라우터에서 ACTION_RISK 검증).
    - registration_code 평문은 IssueResult.registration_code 로만 반환되고,
      서버는 해시+솔트만 영속화한다.
    """
    if expires_in_minutes is None or int(expires_in_minutes) < 1:
        raise InvalidTTLError("expires_in_minutes must be >= 1")
    if int(expires_in_minutes) > MAX_TTL_MINUTES:
        raise InvalidTTLError(
            f"expires_in_minutes must be <= {MAX_TTL_MINUTES}"
        )

    label = (label or "").strip()[:80]
    if not label:
        raise ValueError("label is required")
    note = (note or "").strip()[:200]
    actions = [str(a).strip().lower()[:40] for a in (allowed_actions or []) if a]

    code_plain = _generate_code()
    salt = secrets.token_hex(16)
    code_hash = _hash_code(_normalize_code(code_plain), salt)

    now = _now()
    rec = RegistrationCode(
        code_id=f"rc-{uuid.uuid4().hex[:12]}",
        label=label,
        code_hash=code_hash,
        code_salt=salt,
        allowed_actions=actions,
        expires_at=(now + timedelta(minutes=int(expires_in_minutes))).isoformat(),
        created_at=now.isoformat(),
        issued_by=(issued_by or "")[:80],
        issuer_role=(issuer_role or "")[:40],
        note=note,
    )
    with _lock:
        _codes[rec.code_id] = rec
    return IssueResult(code=rec, registration_code=code_plain)


# ── 조회 / 폐기 ──────────────────────────────────────────────────────────

def get_code(code_id: str) -> Optional[RegistrationCode]:
    return _codes.get(code_id)


def list_codes() -> list[dict]:
    with _lock:
        items = list(_codes.values())
    items.sort(key=lambda r: r.created_at, reverse=True)
    return [r.to_safe() for r in items]


def revoke_code(code_id: str, *, actor: str) -> Optional[RegistrationCode]:
    """active/expired/used 어떤 상태에서도 idempotent.

    - 이미 revoked → 그대로 반환 (필드 변경 없음).
    - 그 외 상태 → revoked_at/revoked_by 세팅 후 status=revoked.
      (used 상태에서도 revoke 가능 — 추후 동일 코드 재사용 시도 차단 일관성)
    """
    with _lock:
        rec = _codes.get(code_id)
        if rec is None:
            return None
        if rec.revoked_at:
            return rec
        rec.revoked_at = _now_iso()
        rec.revoked_by = (actor or "")[:80]
        return rec


# ── 교환 (register-with-code 내부) ──────────────────────────────────────

class CodeExchangeError(Exception):
    """generic 교환 실패. 상세 reason 은 audit 용으로만 사용."""

    def __init__(self, reason: str):
        super().__init__(INVALID_CODE_MESSAGE)
        self.reason = reason


def consume_code(raw_code: str) -> RegistrationCode:
    """raw 입력을 정규화·검증 후 사용 처리. 성공 시 코드 레코드 반환.

    실패는 모두 CodeExchangeError(reason=...) 로 통일.
    reason 값은 audit 전용 — 클라이언트 응답에는 generic 메시지만 노출한다.
    """
    normalized = _normalize_code(raw_code or "")
    if len(normalized) != _CODE_LEN:
        raise CodeExchangeError("malformed")

    now = _now()
    with _lock:
        # 선형 탐색 — 발급량이 많지 않으므로 인덱스 미도입.
        target: Optional[RegistrationCode] = None
        for rec in _codes.values():
            cand = _hash_code(normalized, rec.code_salt)
            if secrets.compare_digest(cand, rec.code_hash):
                target = rec
                break
        if target is None:
            raise CodeExchangeError("not_found")
        if target.revoked_at:
            raise CodeExchangeError("revoked")
        if target.used_at:
            raise CodeExchangeError("used")
        try:
            exp = datetime.fromisoformat(target.expires_at)
        except (TypeError, ValueError):
            raise CodeExchangeError("expired")
        if now >= exp:
            raise CodeExchangeError("expired")
        # 사용 처리 — used_by_agent_id 는 호출자가 register_agent 후 set.
        target.used_at = now.isoformat()
        return target


def attach_used_agent(code_id: str, agent_id: str) -> None:
    """consume_code 성공 후 발급된 agent_id 를 코드에 연결."""
    with _lock:
        rec = _codes.get(code_id)
        if rec is None:
            return
        rec.used_by_agent_id = agent_id


__all__ = [
    "RegistrationCode", "IssueResult",
    "InvalidTTLError", "CodeExchangeError", "INVALID_CODE_MESSAGE",
    "DEFAULT_TTL_MINUTES", "MAX_TTL_MINUTES",
    "issue_code", "list_codes", "get_code", "revoke_code",
    "consume_code", "attach_used_agent", "clear",
]
