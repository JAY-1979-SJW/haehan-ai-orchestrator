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

import contextlib
import hashlib
import json
import logging
import os
import secrets
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


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
    # Fields with defaults must come after required fields
    smoke_test: bool = False  # smoke test marker for cleanup eligibility
    note: str = ""
    used_at: str = ""
    used_by_agent_id: str = ""
    revoked_at: str = ""
    revoked_by: str = ""

    def status(self, now: datetime | None = None) -> str:
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
            "smoke_test": self.smoke_test,
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
    def issue(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: list[str] | None = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
        smoke_test: bool = False,
    ) -> IssueResult:
        """새 등록코드 발급."""
        pass

    @abstractmethod
    def consume(self, raw_code: str) -> RegistrationCode:
        """Code를 검증·사용 처리하고 record 반환."""
        pass

    @abstractmethod
    def get(self, code_id: str) -> RegistrationCode | None:
        """code_id로 code record 조회."""
        pass

    @abstractmethod
    def list(self) -> list[dict]:
        """모든 code (safe response) 조회."""
        pass

    @abstractmethod
    def revoke(self, code_id: str, *, actor: str) -> RegistrationCode | None:
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

    def issue(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: list[str] | None = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
        smoke_test: bool = False,
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
            smoke_test=smoke_test,
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
            target: RegistrationCode | None = None
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
            except (TypeError, ValueError) as exc:
                raise CodeExchangeError("expired") from exc
            if now >= exp:
                raise CodeExchangeError("expired")
            target.used_at = now.isoformat()
            return target

    def get(self, code_id: str) -> RegistrationCode | None:
        with self._lock:
            return self._codes.get(code_id)

    def list(self) -> list[dict]:
        with self._lock:
            items = list(self._codes.values())
        items.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_safe() for r in items]

    def revoke(self, code_id: str, *, actor: str) -> RegistrationCode | None:
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


# ── DB-Backed Store (Fake DB 기반 구현) ──────────────────────────────────────


class _FakeDbTable:
    """테스트용 fake registration_codes 테이블 (in-memory SQL 시뮬레이션)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows: dict[str, RegistrationCode] = {}  # code_id -> RegistrationCode

    def insert(self, rec: RegistrationCode) -> None:
        """INSERT registration_codes (code_id, code_hash, code_salt, ...)."""
        with self._lock:
            if rec.code_id in self._rows:
                raise ValueError(f"code_id already exists: {rec.code_id}")
            self._rows[rec.code_id] = rec

    def select_by_id(self, code_id: str) -> RegistrationCode | None:
        """SELECT * FROM registration_codes WHERE code_id = ?."""
        with self._lock:
            return self._rows.get(code_id)

    def select_all(self) -> list[RegistrationCode]:
        """SELECT * FROM registration_codes."""
        with self._lock:
            return list(self._rows.values())

    def update_used_at(self, code_id: str, used_at: str) -> None:
        """UPDATE registration_codes SET used_at = ? WHERE code_id = ?."""
        with self._lock:
            if code_id in self._rows:
                self._rows[code_id].used_at = used_at

    def update_revoked_at(self, code_id: str, revoked_at: str, revoked_by: str) -> None:
        """UPDATE registration_codes SET revoked_at = ?, revoked_by = ? WHERE code_id = ?."""
        with self._lock:
            if code_id in self._rows:
                self._rows[code_id].revoked_at = revoked_at
                self._rows[code_id].revoked_by = revoked_by

    def update_used_by_agent_id(self, code_id: str, agent_id: str) -> None:
        """UPDATE registration_codes SET used_by_agent_id = ? WHERE code_id = ?."""
        with self._lock:
            if code_id in self._rows:
                self._rows[code_id].used_by_agent_id = agent_id

    def clear(self) -> None:
        """테스트용: 테이블 초기화."""
        with self._lock:
            self._rows.clear()


# ── PostgreSQL Executor ──────────────────────────────────────────────────────


class _PostgresDbExecutor:
    """PostgreSQL 연결 및 쿼리 실행 (connection-per-operation)."""

    _conn: Any  # 타입 선언만(값 미할당) — 동작 불변

    def __init__(self, connection_string: str):
        """connection_string: postgresql://user:pass@host:port/dbname"""
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:
            raise RuntimeError("psycopg2 not installed. Install via: pip install psycopg2-binary>=2.9.0") from exc

        self.conn_str = connection_string
        self._lock = threading.Lock()
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras

    def _get_connection(self):
        """새 connection 생성 (connection-per-operation으로 stale connection 방지)."""
        try:
            conn = self._psycopg2.connect(self.conn_str)
            conn.autocommit = False
            return conn
        except (self._psycopg2.OperationalError, self._psycopg2.InterfaceError) as exc:
            logger.error("PostgreSQL connection failed")
            raise RuntimeError("Cannot connect to PostgreSQL") from exc
        except Exception as exc:
            logger.error("Unexpected error connecting to PostgreSQL")
            raise RuntimeError("Unexpected error connecting to PostgreSQL") from exc

    def insert(self, rec: RegistrationCode) -> None:
        """INSERT registration_codes."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO registration_codes
                        (code_id, code_hash, code_salt, label, note, allowed_actions,
                         expires_at, created_at, issued_by, issuer_role, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        rec.code_id,
                        rec.code_hash,
                        rec.code_salt,
                        rec.label,
                        rec.note,
                        json.dumps(rec.allowed_actions),  # JSONB
                        rec.expires_at,
                        rec.created_at,
                        rec.issued_by,
                        rec.issuer_role,
                        json.dumps({"smoke_test": rec.smoke_test}),  # metadata (smoke_test 포함)
                    ),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("INSERT failed")
                raise ValueError(f"code_id already exists: {rec.code_id}") from e
            finally:
                cur.close()
                conn.close()

    def select_by_id(self, code_id: str) -> RegistrationCode | None:
        """SELECT * FROM registration_codes WHERE code_id = ?."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=self._extras.RealDictCursor)
            try:
                cur.execute(
                    "SELECT * FROM registration_codes WHERE code_id = %s",
                    (code_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_record(dict(row))
            finally:
                cur.close()
                conn.close()

    def select_all(self) -> list[RegistrationCode]:
        """SELECT * FROM registration_codes."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=self._extras.RealDictCursor)
            try:
                cur.execute("SELECT * FROM registration_codes ORDER BY created_at DESC")
                rows = cur.fetchall()
                return [self._row_to_record(dict(row)) for row in rows]
            finally:
                cur.close()
                conn.close()

    def update_used_at(self, code_id: str, used_at: str) -> None:
        """UPDATE registration_codes SET used_at = ? WHERE code_id = ?."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE registration_codes SET used_at = %s WHERE code_id = %s",
                    (used_at, code_id),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("UPDATE used_at failed")
                # fail-closed: 조용히 넘어가면 호출자(consume())는 DB 반영을 확인하지
                # 않고 "사용됨" 처리를 계속하므로, DB에는 미사용 상태로 남아 같은
                # 1회용 등록코드가 재사용될 수 있다(2026-09-28 STD-04 재검토로 발견).
                raise RuntimeError("registration code used_at 기록 실패") from e
            finally:
                cur.close()
                conn.close()

    def update_revoked_at(self, code_id: str, revoked_at: str, revoked_by: str) -> None:
        """UPDATE registration_codes SET revoked_at = ?, revoked_by = ? WHERE code_id = ?."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE registration_codes SET revoked_at = %s, revoked_by = %s WHERE code_id = %s",
                    (revoked_at, revoked_by, code_id),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("UPDATE revoked_at failed")
                # fail-closed: 조용히 넘어가면 호출자(revoke())는 DB 반영을 확인하지
                # 않고 revoke 성공으로 응답하므로, DB에는 미revoke 상태로 남아 이미
                # 취소된 코드가 계속 유효한 것처럼 사용될 수 있다.
                raise RuntimeError("registration code revoked_at 기록 실패") from e
            finally:
                cur.close()
                conn.close()

    def update_used_by_agent_id(self, code_id: str, agent_id: str) -> None:
        """UPDATE registration_codes SET used_by_agent_id = ? WHERE code_id = ?."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE registration_codes SET used_by_agent_id = %s WHERE code_id = %s",
                    (agent_id, code_id),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("UPDATE used_by_agent_id failed")
                # fail-closed: 감사 연결 정보 유실을 조용히 넘기지 않고 알린다
                # (used_at/revoked_at 만큼 치명적이진 않지만 감사 추적성 저하).
                raise RuntimeError("registration code used_by_agent_id 기록 실패") from e
            finally:
                cur.close()
                conn.close()

    def clear(self) -> None:
        """테스트 전용: 모든 code 삭제 (운영 금지)."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM registration_codes")
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error("CLEAR failed")
                # fail-closed: 테스트 정리가 실패했는데 조용히 넘어가면 다음 테스트가
                # 이전 테스트의 잔여 데이터를 보고 오판할 수 있다.
                raise RuntimeError("registration code 테스트 초기화(DELETE) 실패") from e
            finally:
                cur.close()
                conn.close()

    def _row_to_record(self, row: dict) -> RegistrationCode:
        """DB row를 RegistrationCode로 변환."""
        allowed_actions_raw = row.get("allowed_actions", "[]")
        if isinstance(allowed_actions_raw, str):
            allowed_actions = json.loads(allowed_actions_raw)
        elif isinstance(allowed_actions_raw, list):
            allowed_actions = allowed_actions_raw
        else:
            allowed_actions = []

        # metadata에서 smoke_test 추출
        metadata_raw = row.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        elif isinstance(metadata_raw, dict):
            metadata = metadata_raw
        else:
            metadata = {}
        smoke_test = bool(metadata.get("smoke_test", False))

        # psycopg2 RealDictCursor returns datetime objects for timestamp columns,
        # but RegistrationCode expects ISO format strings
        def dt_to_iso(val):
            if isinstance(val, datetime):
                return val.isoformat()
            return val or ""

        return RegistrationCode(
            code_id=row["code_id"],
            label=row.get("label", ""),
            code_hash=row["code_hash"],
            code_salt=row["code_salt"],
            allowed_actions=list(allowed_actions) if allowed_actions else [],
            expires_at=dt_to_iso(row.get("expires_at")),
            created_at=dt_to_iso(row.get("created_at")),
            issued_by=row.get("issued_by", ""),
            issuer_role=row.get("issuer_role", ""),
            smoke_test=smoke_test,
            note=row.get("note", ""),
            used_at=dt_to_iso(row.get("used_at")),
            used_by_agent_id=row.get("used_by_agent_id", ""),
            revoked_at=dt_to_iso(row.get("revoked_at")),
            revoked_by=row.get("revoked_by", ""),
        )

    def close(self) -> None:
        """DB 연결 종료."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None


class DbRegistrationCodeStore(RegistrationCodeStore):
    """PostgreSQL-backed store (fake DB 또는 실제 PostgreSQL)."""

    def __init__(self, db_connection_string: str):
        """db_connection_string: fake:// 또는 postgresql://user:pass@host/db"""
        self.db_conn_str = db_connection_string

        if db_connection_string.startswith("fake://"):
            # 테스트용 fake DB
            self._db: _FakeDbTable | _PostgresDbExecutor = _FakeDbTable()
            self._is_fake = True
        else:
            # 실제 PostgreSQL
            try:
                self._db = _PostgresDbExecutor(db_connection_string)
                self._is_fake = False
            except RuntimeError as e:
                logger.error(f"PostgreSQL init failed: {e}")
                raise

    def issue(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
        self,
        *,
        label: str,
        expires_in_minutes: int = DEFAULT_TTL_MINUTES,
        allowed_actions: list[str] | None = None,
        note: str = "",
        issued_by: str,
        issuer_role: str = "",
        smoke_test: bool = False,
    ) -> IssueResult:
        """DB (fake)에 code_hash, code_salt, metadata 저장."""
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
            smoke_test=smoke_test,
            note=note,
        )

        # DB insert (fake DB만 사용, 운영 DB 접속 금지)
        self._db.insert(rec)

        return IssueResult(code=rec, registration_code=code_plain)

    def consume(self, raw_code: str) -> RegistrationCode:
        """DB에서 hash 비교, used_at 갱신."""
        normalized = _normalize_code(raw_code or "")
        if len(normalized) != CODE_LEN:
            raise CodeExchangeError("malformed")

        now = _now()

        # DB select all
        all_records = self._db.select_all()

        # hash 비교
        target: RegistrationCode | None = None
        for rec in all_records:
            cand = _hash_code(normalized, rec.code_salt)
            if secrets.compare_digest(cand, rec.code_hash):
                target = rec
                break

        if target is None:
            raise CodeExchangeError("not_found")

        # 상태 검증
        if target.revoked_at:
            raise CodeExchangeError("revoked")
        if target.used_at:
            raise CodeExchangeError("used")

        try:
            exp = datetime.fromisoformat(target.expires_at)
        except (TypeError, ValueError) as exc:
            raise CodeExchangeError("expired") from exc

        if now >= exp:
            raise CodeExchangeError("expired")

        # 성공: used_at 기록
        self._db.update_used_at(target.code_id, now.isoformat())
        target.used_at = now.isoformat()

        return target

    def get(self, code_id: str) -> RegistrationCode | None:
        """DB에서 code 조회."""
        return self._db.select_by_id(code_id)

    def list(self) -> list[dict]:
        """DB에서 code 목록 조회 (safe response only)."""
        all_records = self._db.select_all()
        all_records.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_safe() for r in all_records]

    def revoke(self, code_id: str, *, actor: str) -> RegistrationCode | None:
        """DB에서 code revoke."""
        rec = self._db.select_by_id(code_id)
        if rec is None:
            return None
        if rec.revoked_at:
            return rec
        revoked_at = _now_iso()
        self._db.update_revoked_at(code_id, revoked_at, (actor or "")[:80])
        rec.revoked_at = revoked_at
        rec.revoked_by = (actor or "")[:80]
        return rec

    def attach_used_agent(self, code_id: str, agent_id: str) -> None:
        """DB에서 agent_id 연결."""
        rec = self._db.select_by_id(code_id)
        if rec is None:
            return
        self._db.update_used_by_agent_id(code_id, agent_id)
        rec.used_by_agent_id = agent_id

    def clear_for_tests(self) -> None:
        """테스트 전용: fake DB 초기화 (운영 DB DELETE 절대 금지)."""
        self._db.clear()


# ── Global Store Instance ────────────────────────────────────────────────────

_store: RegistrationCodeStore | None = None


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
