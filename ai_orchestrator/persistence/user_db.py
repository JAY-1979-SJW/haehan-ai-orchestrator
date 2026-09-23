"""L7 Persistence — 회원 SQLite DB.

users 테이블: id, email, name, password_hash, role, plan, created_at, enabled
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent / "storage" / "users.db"


def _get_db_path() -> Path:
    return _DB_PATH


@contextmanager
def _conn():
    con = sqlite3.connect(str(_get_db_path()))
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                plan TEXT NOT NULL DEFAULT 'free',
                created_at TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        con.commit()


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256${salt}${h}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored.startswith("sha256$"):
        return False
    parts = stored.split("$", 2)
    if len(parts) != 3:
        return False
    _, salt, hash_hex = parts
    computed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(computed, hash_hex)


def create_user(email: str, name: str, password: str) -> dict:
    """신규 가입자는 enabled=0(승인 대기)으로 생성. 관리자 승인 후 enabled=1."""
    init_db()
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    pw_hash = _hash_password(password)
    with _conn() as con:
        con.execute(
            "INSERT INTO users (id, email, name, password_hash, role, plan, created_at, enabled) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, email.lower().strip(), name.strip(), pw_hash, "user", "free", now, 0),
        )
        con.commit()
    # 승인 전(enabled=0)에도 가입 결과를 반환해야 하므로 enabled 필터 없는 조회 사용
    return _get_user_unfiltered(user_id)


def _get_user_unfiltered(user_id: str) -> dict | None:
    """enabled 여부와 무관하게 조회 (가입 직후·승인 처리용 내부 헬퍼)."""
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_pending_users() -> list[dict]:
    """승인 대기(enabled=0) 사용자 목록 — 관리자 콘솔용."""
    init_db()
    with _conn() as con:
        rows = con.execute("SELECT * FROM users WHERE enabled=0 ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def approve_user(user_id: str) -> bool:
    """승인 대기 사용자를 enabled=1로 전환. 성공 시 True."""
    init_db()
    with _conn() as con:
        cur = con.execute("UPDATE users SET enabled=1 WHERE id=?", (user_id,))
        con.commit()
    return cur.rowcount > 0


def get_user_by_email(email: str) -> dict | None:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email=? AND enabled=1", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id=? AND enabled=1", (user_id,)).fetchone()
    return dict(row) if row else None


def authenticate_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return user


def is_pending_login(email: str, password: str) -> bool:
    """이메일+비밀번호가 일치하지만 승인 대기(enabled=0)인 경우 True.

    로그인 시 '승인 대기' 안내를 비밀번호가 맞을 때만 보여주기 위함.
    (비밀번호 오류 시 이메일 존재 여부를 노출하지 않도록 분리)
    """
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email=? AND enabled=0", (email.lower().strip(),)).fetchone()
    if not row:
        return False
    return _verify_password(password, dict(row)["password_hash"])


def update_password(user_id: str, new_password: str) -> bool:
    pw_hash = _hash_password(new_password)
    with _conn() as con:
        cur = con.execute(
            "UPDATE users SET password_hash=? WHERE id=? AND enabled=1",
            (pw_hash, user_id),
        )
        con.commit()
    return cur.rowcount > 0


def email_exists(email: str) -> bool:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT 1 FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    return row is not None


def safe_user(user: dict) -> dict:
    """password_hash 제거한 안전한 dict 반환."""
    return {k: v for k, v in user.items() if k != "password_hash"}
