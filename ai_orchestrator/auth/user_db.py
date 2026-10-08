"""L7 Persistence — 회원 SQLite DB.

users 테이블: id, email, name, password_hash, role, plan, created_at, enabled
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import storage_dir

_DB_PATH = storage_dir() / "users.db"


def _get_db_path() -> Path:
    return _DB_PATH


@contextmanager
def _conn():
    _get_db_path().parent.mkdir(
        parents=True, exist_ok=True
    )  # 데스크톱: 새 데이터 루트(userData\storage)가 아직 없을 수 있다
    con = sqlite3.connect(str(_get_db_path()), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# 경로별 1회 초기화 가드 (핫패스에서 매 호출 CREATE+commit 방지)
_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()


def init_db() -> None:
    key = str(_get_db_path())
    # 파일이 삭제된 경우(시험·복구)에는 재초기화
    if key in _INITIALIZED and Path(key).exists():
        return
    with _INIT_LOCK:
        if key in _INITIALIZED and Path(key).exists():
            return
        _create_schema()
        _INITIALIZED.add(key)


def _create_schema() -> None:
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
        # 데스크톱 자동 세션이 '마지막으로 쓴 owner' 를 고르는 데 쓴다 — 옛 DB 에는 컬럼이 없으므로 한 번 추가한다.
        columns = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "last_session_at" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN last_session_at TEXT")
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
    created = _get_user_unfiltered(user_id)
    if created is None:
        raise RuntimeError("가입 직후 조회 실패")
    return created


def create_user_bootstrapping(
    email: str, name: str, password: str, *, allow_bootstrap: bool, only_bootstrap: bool = False
) -> tuple[dict | None, bool]:
    """가입 처리 + (허용될 때) 첫 가입자 owner 부트스트랩. 반환: (사용자, 부트스트랩으로 owner 가 되었는가).

    allow_bootstrap 이 True 이고 users 테이블이 **완전히 비어 있을 때** 들어온 가입 한 명만 enabled=1, role=owner 가 된다.
    경쟁 조건 차단: BEGIN IMMEDIATE 로 쓰기 잠금을 먼저 잡은 뒤 '비어 있는가' 확인과 INSERT 를 한 트랜잭션으로 처리하고,
    INSERT 자체도 `WHERE NOT EXISTS` 로 한 번 더 막는다 → 동시에 두 가입이 와도 한 명만 owner, 나머지는 승인 대기.
    allow_bootstrap=False(서버 모드 등)면 늘 enabled=0, role=user — create_user 와 같다.
    only_bootstrap=True 면 부트스트랩이 안 될 때(이미 사용자가 있음) 아무 행도 만들지 않고 (None, False) 를 돌려준다
    (데스크톱 첫 실행 설정: 승인 대기 계정이 따로 생기면 안 된다).
    """
    init_db()
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    pw_hash = _hash_password(password)
    with _conn() as con:
        con.isolation_level = None  # 아래에서 트랜잭션을 직접 관리
        con.execute("BEGIN IMMEDIATE")
        try:
            if allow_bootstrap:
                con.execute(
                    "INSERT INTO users (id, email, name, password_hash, role, plan, created_at, enabled) "
                    "SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM users)",
                    (user_id, email.lower().strip(), name.strip(), pw_hash, "owner", "free", now, 1),
                )
                inserted = con.execute("SELECT changes()").fetchone()[0] == 1
            else:
                inserted = False
            if not inserted and only_bootstrap:
                con.execute("ROLLBACK")
                return None, False
            if not inserted:
                con.execute(
                    "INSERT INTO users (id, email, name, password_hash, role, plan, created_at, enabled) VALUES (?,?,?,?,?,?,?,?)",
                    (user_id, email.lower().strip(), name.strip(), pw_hash, "user", "free", now, 0),
                )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    created = _get_user_unfiltered(user_id)
    if created is None:
        raise RuntimeError("가입 직후 조회 실패")
    return created, bool(inserted)


def count_users() -> int:
    """승인 대기·비활성 포함 전체 사용자 수."""
    init_db()
    with _conn() as con:
        return int(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def select_desktop_owner() -> dict | None:
    """데스크톱 자동 세션을 만들 owner — 활성(enabled=1) owner 중 마지막으로 세션을 쓴 계정, 그런 기록이 없으면 가장 먼저 만든 owner.

    owner 가 없으면(비어 있거나 승인 대기 일반 계정뿐) None."""
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE role='owner' AND enabled=1 "
            "ORDER BY (last_session_at IS NULL), last_session_at DESC, created_at ASC, id ASC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def touch_session(user_id: str) -> None:
    """자동 세션 발급 시각 기록(마지막으로 쓴 owner 를 고르는 기준)."""
    init_db()
    with _conn() as con:
        con.execute("UPDATE users SET last_session_at=? WHERE id=?", (datetime.now(UTC).isoformat(), user_id))
        con.commit()


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


def delete_pending_user(user_id: str) -> str:
    """승인 대기(enabled=0) 계정만 삭제한다. 승인된 계정은 지우지 않는다.

    반환: "deleted" | "not_pending"(이미 승인된 계정) | "not_found". 삭제하면 그 이메일로 다시 가입할 수 있다."""
    init_db()
    with _conn() as con:
        cur = con.execute("DELETE FROM users WHERE id=? AND enabled=0", (user_id,))
        deleted = cur.rowcount > 0
        exists = deleted or con.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is not None
        con.commit()
    if deleted:
        return "deleted"
    return "not_pending" if exists else "not_found"


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
