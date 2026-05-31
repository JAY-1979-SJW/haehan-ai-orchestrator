"""L7 Persistence — 회원 SQLite DB.

users 테이블: id, email, name, password_hash, role, plan, created_at, enabled
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    init_db()
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = _hash_password(password)
    with _conn() as con:
        con.execute(
            "INSERT INTO users (id, email, name, password_hash, role, plan, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, email.lower().strip(), name.strip(), pw_hash, "user", "free", now),
        )
        con.commit()
    return get_user_by_id(user_id)


def get_user_by_email(email: str) -> Optional[dict]:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE email=? AND enabled=1", (email.lower().strip(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE id=? AND enabled=1", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = get_user_by_email(email)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return user


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
        row = con.execute(
            "SELECT 1 FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
    return row is not None


def safe_user(user: dict) -> dict:
    """password_hash 제거한 안전한 dict 반환."""
    return {k: v for k, v in user.items() if k != "password_hash"}
