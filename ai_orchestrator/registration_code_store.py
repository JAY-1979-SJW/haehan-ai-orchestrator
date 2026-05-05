"""Registration code store abstraction (REGCODE-2).

Backend selection:
  - memory: process-local in-memory (default, no DB required)
  - db: PostgreSQL-backed (requires migration + config)

환경변수:
  LOCAL_AGENT_REGISTRATION_CODE_STORE=memory|db (기본값: memory)

보안:
  - registration_code 원문은 발급 응답에서 1회만 반환
  - DB에는 code_hash + code_salt만 저장
  - code 원문은 메모리에서도 발급 후 즉시 폐기 (IssueResult로만 반환)
  - consume/revoke 시 DB 접근 최소화
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _generate_code() -> str:
    """4-4-4 형식 registration code 생성."""
    CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    CODE_LEN = 12
    chars = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
    return f"{chars[0:4]}-{chars[4:8]}-{chars[8:12]}"


def _normalize_code(raw: str) -> str:
    """입력 코드를 비교 가능한 정규형으로 변환."""
    CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    if not raw:
        return ""
    return "".join(c for c in raw.upper() if c in CODE_ALPHABET)


def _hash_code(normalized: str, salt: str) -> str:
    """code_hash = SHA-256(salt + ':' + normalized)."""
    return hashlib.sha256((salt + ":" + normalized).encode("utf-8")).hexdigest()


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TTL_MINUTES: int = 30
MAX_TTL_MINUTES: int = 60 * 24
INVALID_CODE_MESSAGE: str = "invalid_registration_code"
CODE_LEN: int = 12


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class RegistrationCode:
    """Registration code record (공통 데이터 구조)."""
    code_id: str
    label: str
    code_hash: str
    code_salt: str
    allowed_actions: list[str]
    expires_at: str  # ISO format
    created_at: str
    issued_by: str
    issuer_role: str
    note: str = ""
    used_at: str = ""
    used_by_agent_id: str = ""
    revoked_at: str = ""
    revoked_by: str = ""

    def status(self, now: Optional[datetime] = None) -> str:
        """현재 code 상태 반환: revoked | used | expired | active."""
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
        """API response용 — code_hash, code_salt, registration_code 미포함."""
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


@dataclass
class IssueResult:
    """Code 발급 결과 — registration_code 평문은 1회만 반환."""
    code: RegistrationCode
    registration_code: str  # 평문 — 호출자가 1회만 사용 후 폐기


# ── Exceptions ───────────────────────────────────────────────────────────────

class InvalidTTLError(ValueError):
    """TTL이 허용 범위를 벗어남."""


class CodeExchangeError(Exception):
    """Code exchange 실패 (generic 메시지, 상세는 audit용만)."""

    def __init__(self, reason: str):
        super().__init__(INVALID_CODE_MESSAGE)
        self.reason = reason  # audit용: "not_found", "malformed", "used", "revoked", "expired"


# ── Store Interface ──────────────────────────────────────────────────────────

class RegistrationCodeStore(ABC):
    """Registration code store 추상 인터페이스."""

    @abstractmethod
    def issue(
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: Optional[list[str]] = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
    ) -> IssueResult:
        """새 등록코드 발급."""
        pass

    @abstractmethod
    def consume(self, raw_code: str) -> RegistrationCode:
        """Code를 검증·사용 처리하고 record 반환."""
        pass

    @abstractmethod
    def get(self, code_id: str) -> Optional[RegistrationCode]:
        """code_id로 code record 조회."""
        pass

    @abstractmethod
    def list(self) -> list[dict]:
        """모든 code (safe response) 조회."""
        pass

    @abstractmethod
    def revoke(self, code_id: str, *, actor: str) -> Optional[RegistrationCode]:
        """Code revoke."""
        pass

    @abstractmethod
    def attach_used_agent(self, code_id: str, agent_id: str) -> None:
        """Used code에 agent_id 연결."""
        pass

    @abstractmethod
    def clear_for_tests(self) -> None:
        """테스트 전용: 저장소 초기화."""
        pass


# ── In-Memory Store (기본값) ────────────────────────────────────────────────────

class InMemoryRegistrationCodeStore(RegistrationCodeStore):
    """Process-local in-memory store (기본값, 운영 migration 전까지)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._codes: dict[str, RegistrationCode] = {}

    def issue(
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: Optional[list[str]] = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
    ) -> IssueResult:
        if expires_in_minutes is None or int(expires_in_minutes) < 1:
            raise InvalidTTLError("expires_in_minutes must be >= 1")
        if int(expires_in_minutes) > MAX_TTL_MINUTES:
            raise InvalidTTLError(f"expires_in_minutes must be <= {MAX_TTL_MINUTES}")

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
        with self._lock:
            self._codes[rec.code_id] = rec
        return IssueResult(code=rec, registration_code=code_plain)

    def consume(self, raw_code: str) -> RegistrationCode:
        normalized = _normalize_code(raw_code or "")
        if len(normalized) != CODE_LEN:
            raise CodeExchangeError("malformed")

        now = _now()
        with self._lock:
            target: Optional[RegistrationCode] = None
            for rec in self._codes.values():
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
            target.used_at = now.isoformat()
            return target

    def get(self, code_id: str) -> Optional[RegistrationCode]:
        with self._lock:
            return self._codes.get(code_id)

    def list(self) -> list[dict]:
        with self._lock:
            items = list(self._codes.values())
        items.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_safe() for r in items]

    def revoke(self, code_id: str, *, actor: str) -> Optional[RegistrationCode]:
        with self._lock:
            rec = self._codes.get(code_id)
            if rec is None:
                return None
            if rec.revoked_at:
                return rec
            rec.revoked_at = _now_iso()
            rec.revoked_by = (actor or "")[:80]
            return rec

    def attach_used_agent(self, code_id: str, agent_id: str) -> None:
        with self._lock:
            rec = self._codes.get(code_id)
            if rec is None:
                return
            rec.used_by_agent_id = agent_id

    def clear_for_tests(self) -> None:
        """테스트 전용: 저장소 초기화."""
        with self._lock:
            self._codes.clear()


# ── DB-Backed Store (미구현, placeholder) ────────────────────────────────────

class DbRegistrationCodeStore(RegistrationCodeStore):
    """PostgreSQL-backed store (migration 적용 후 활성화)."""

    def __init__(self, db_connection_string: str):
        self.db_conn_str = db_connection_string
        # TODO: DB connection pooling 구성
        # TODO: SQL helper 함수들 구현

    def issue(
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: Optional[list[str]] = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
    ) -> IssueResult:
        """DB에 code_hash, code_salt, metadata 저장.

        1. code_plain 생성
        2. normalized_code 생성
        3. salt 생성
        4. code_hash = SHA-256(salt + ':' + normalized)
        5. DB insert (code_plain은 절대 저장하지 않음)
        6. IssueResult로 code_plain 1회만 반환
        """
        if expires_in_minutes is None or int(expires_in_minutes) < 1:
            raise InvalidTTLError("expires_in_minutes must be >= 1")
        if int(expires_in_minutes) > MAX_TTL_MINUTES:
            raise InvalidTTLError(f"expires_in_minutes must be <= {MAX_TTL_MINUTES}")

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

        # TODO: DB insert
        # INSERT INTO registration_codes (
        #   code_id, code_hash, code_salt, label, note, allowed_actions,
        #   expires_at, created_at, created_by, metadata
        # ) VALUES (...)
        # NOTE: code_plain은 DB에 저장하지 않음 (메모리에서도 즉시 폐기)

        return IssueResult(code=rec, registration_code=code_plain)

    def consume(self, raw_code: str) -> RegistrationCode:
        """DB에서 hash 비교, used_at 갱신.

        1. 입력 code 정규화
        2. DB에서 후보 조회 (모든 code의 salt 이용)
        3. hash 계산 및 constant-time compare
        4. revoked_at, used_at, expires_at 검증
        5. 성공 시 DB에서 used_at = NOW() 업데이트
        6. RegistrationCode 객체 반환 또는 CodeExchangeError 발생

        실패 reason (audit용만):
        - malformed: normalized length != 12
        - not_found: 어떤 code_hash도 일치 안 함
        - revoked: revoked_at 존재
        - used: used_at 존재
        - expired: NOW() >= expires_at
        """
        normalized = _normalize_code(raw_code or "")
        if len(normalized) != CODE_LEN:
            raise CodeExchangeError("malformed")

        now = _now()

        # TODO: DB select all records where revoked_at is null and expires_at > now
        # for each record:
        #   cand = _hash_code(normalized, record.code_salt)
        #   if secrets.compare_digest(cand, record.code_hash):
        #     # found match
        #     if record.used_at:
        #       raise CodeExchangeError("used")
        #     if record.revoked_at:
        #       raise CodeExchangeError("revoked")
        #     if now >= record.expires_at:
        #       raise CodeExchangeError("expired")
        #     # 성공: UPDATE registration_codes SET used_at = now WHERE code_id = ?
        #     return record

        # TODO: if no match found:
        #   raise CodeExchangeError("not_found")

        raise NotImplementedError("DB backend not yet implemented")

    def get(self, code_id: str) -> Optional[RegistrationCode]:
        """DB에서 code 조회.

        TODO: SELECT * FROM registration_codes WHERE code_id = ?
        """
        raise NotImplementedError("DB backend not yet implemented")

    def list(self) -> list[dict]:
        """DB에서 code 목록 조회 (safe response only).

        응답에는 code_hash, code_salt, registration_code 미포함.

        TODO: SELECT code_id, label, allowed_actions, expires_at, created_at, ...
              FROM registration_codes ORDER BY created_at DESC
        """
        raise NotImplementedError("DB backend not yet implemented")

    def revoke(self, code_id: str, *, actor: str) -> Optional[RegistrationCode]:
        """DB에서 code revoke.

        TODO: UPDATE registration_codes
              SET revoked_at = now(), revoked_by = ?
              WHERE code_id = ? AND revoked_at IS NULL
        """
        raise NotImplementedError("DB backend not yet implemented")

    def attach_used_agent(self, code_id: str, agent_id: str) -> None:
        """DB에서 agent_id 연결.

        TODO: UPDATE registration_codes
              SET metadata = jsonb_set(metadata, '{used_by_agent_id}', to_jsonb(?))
              WHERE code_id = ?
        """
        raise NotImplementedError("DB backend not yet implemented")

    def clear_for_tests(self) -> None:
        """테스트 전용: DB 초기화 (운영은 절대 호출 금지).

        금지: DELETE FROM registration_codes (실제 실행 불가)
        권장: 테스트는 in-memory 저장소만 사용하거나, mock/fake DB 사용
        """
        raise RuntimeError("clear_for_tests not allowed in DB backend")


# ── Global Store Instance ────────────────────────────────────────────────────

_store: Optional[RegistrationCodeStore] = None


def get_registration_code_store() -> RegistrationCodeStore:
    """Global registration code store 인스턴스 획득."""
    global _store
    if _store is not None:
        return _store

    # 환경변수로 backend 선택
    store_type = os.environ.get("LOCAL_AGENT_REGISTRATION_CODE_STORE", "memory").strip().lower()

    if store_type == "db":
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if not db_url:
            raise RuntimeError("DATABASE_URL not set, cannot use db backend")
        _store = DbRegistrationCodeStore(db_url)
    else:
        # 기본값: memory (안전)
        _store = InMemoryRegistrationCodeStore()

    return _store


def reset_store_for_tests(backend: str = "memory") -> RegistrationCodeStore:
    """테스트 전용: store 재설정."""
    global _store
    if backend == "memory":
        _store = InMemoryRegistrationCodeStore()
    else:
        raise ValueError(f"unsupported backend in tests: {backend}")
    return _store
