"""Instagram 댓글→키워드→비공개DM 자동화 — 영속 저장 (stdlib sqlite3).

방침(naver_search_db.py 컨벤션 동일):
- SQLAlchemy/ORM 미사용, stdlib sqlite3만 사용.
- 중복 발송 방지는 UNIQUE 인덱스(comment/reply 모두 account+comment_id)로 DB 레벨 강제.
- multi-tenant 확장을 위해 모든 테이블에 instagram_account_id(또는 owner_user_id)를 둔다.
- 토큰은 이 모듈에 평문으로 넣지 않는다 — 암호화 저장은 상위 서비스(keyring)에서 처리하고
  여기 encrypted_access_token 컬럼에는 이미 암호화된 바이트/문자열만 저장한다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir
from ai_orchestrator.persistence.sqlite_schema import add_column_if_missing, apply_schema, set_busy_timeout

_DB_PATH = storage_dir() / "instagram_dm.db"


def _get_db_path() -> Path:
    return _DB_PATH


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_get_db_path()), timeout=30)
    con.row_factory = sqlite3.Row
    set_busy_timeout(con)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
    finally:
        con.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS instagram_accounts (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT,
            instagram_user_id TEXT UNIQUE NOT NULL,
            username TEXT,
            account_type TEXT,
            encrypted_access_token TEXT NOT NULL,
            token_expires_at TEXT,
            scopes TEXT,
            status TEXT NOT NULL DEFAULT 'connected',
            automation_enabled INTEGER NOT NULL DEFAULT 0,
            webhook_subscribed INTEGER NOT NULL DEFAULT 0,
            connected_at TEXT NOT NULL,
            disconnected_at TEXT,
            last_verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_rules (
            id TEXT PRIMARY KEY,
            instagram_account_id TEXT NOT NULL REFERENCES instagram_accounts(id),
            name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            scope_type TEXT NOT NULL DEFAULT 'ALL_MEDIA',
            media_id TEXT,
            match_type TEXT NOT NULL DEFAULT 'ANY_KEYWORD',
            reply_message TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_rule_keywords (
            id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL REFERENCES automation_rules(id),
            keyword TEXT NOT NULL,
            normalized_keyword TEXT NOT NULL,
            is_exclusion INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS instagram_comment_events (
            id TEXT PRIMARY KEY,
            instagram_account_id TEXT NOT NULL REFERENCES instagram_accounts(id),
            comment_id TEXT NOT NULL,
            media_id TEXT,
            media_product_type TEXT,
            commenter_ig_scoped_id TEXT,
            commenter_username TEXT,
            comment_text TEXT,
            normalized_text TEXT,
            comment_created_at TEXT,
            webhook_received_at TEXT NOT NULL,
            raw_payload_json TEXT,
            processing_status TEXT NOT NULL DEFAULT 'RECEIVED',
            matched_rule_id TEXT,
            matched_keyword TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(instagram_account_id, comment_id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS private_reply_logs (
            id TEXT PRIMARY KEY,
            instagram_account_id TEXT NOT NULL REFERENCES instagram_accounts(id),
            comment_event_id TEXT NOT NULL REFERENCES instagram_comment_events(id),
            rule_id TEXT,
            comment_id TEXT NOT NULL,
            request_message TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            blocked_reason TEXT,
            meta_recipient_id TEXT,
            meta_message_id TEXT,
            meta_error_code TEXT,
            meta_error_subcode TEXT,
            meta_error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            first_attempt_at TEXT,
            sent_at TEXT,
            last_attempt_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(instagram_account_id, comment_id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'instagram',
            event_type TEXT,
            external_account_id TEXT,
            external_object_id TEXT,
            signature_valid INTEGER NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RECEIVED',
            received_at TEXT NOT NULL,
            processed_at TEXT,
            error_message TEXT
        )
    """)


def _schema_v2_legacy_instagram_user_id(con: sqlite3.Connection) -> None:
    # 마이그레이션: legacy_instagram_user_id (2026-09-11 추가)
    # Meta 계정 연결(OAuth)은 graph.instagram.com 기준 ID를 instagram_user_id에 저장하지만,
    # 일부 계정(과거 Facebook 로그인 연동 이력이 있는 경우)의 webhook entry.id는
    # 구버전 graph.facebook.com 계열 ID로 온다. 두 ID가 달라 계정 매칭이 실패하는 걸 막기 위해
    # 별도 컬럼에 보조 ID를 저장하고 조회 시 OR로 매칭한다.
    add_column_if_missing(con, "instagram_accounts", "legacy_instagram_user_id", "TEXT")


# 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다(docs/specs/2026-10-01_sqlite_schema_versioning.md)
_SCHEMA_STEPS = [_schema_v1, _schema_v2_legacy_instagram_user_id]


def init_db() -> None:
    with _conn() as con:
        apply_schema(con, _SCHEMA_STEPS)


# ---- instagram_accounts ----


def upsert_account(
    *,
    instagram_user_id: str,
    username: str | None,
    account_type: str | None,
    encrypted_access_token: str,
    scopes: str | None = None,
    owner_user_id: str | None = None,
) -> str:
    now = _now()
    with _conn() as con:
        row = con.execute(
            "SELECT id FROM instagram_accounts WHERE instagram_user_id = ?", (instagram_user_id,)
        ).fetchone()
        if row:
            acc_id = row["id"]
            con.execute(
                """UPDATE instagram_accounts SET username=?, account_type=?, encrypted_access_token=?,
                   scopes=?, status='connected', disconnected_at=NULL, last_verified_at=?, updated_at=?
                   WHERE id=?""",
                (username, account_type, encrypted_access_token, scopes, now, now, acc_id),
            )
        else:
            acc_id = _new_id()
            con.execute(
                """INSERT INTO instagram_accounts
                   (id, owner_user_id, instagram_user_id, username, account_type,
                    encrypted_access_token, scopes, status, automation_enabled, webhook_subscribed,
                    connected_at, last_verified_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,'connected',0,0,?,?,?,?)""",
                (
                    acc_id,
                    owner_user_id,
                    instagram_user_id,
                    username,
                    account_type,
                    encrypted_access_token,
                    scopes,
                    now,
                    now,
                    now,
                    now,
                ),
            )
        con.commit()
        return acc_id


def get_account(account_id: str) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute("SELECT * FROM instagram_accounts WHERE id = ?", (account_id,)).fetchone()


def get_account_by_ig_user_id(instagram_user_id: str) -> sqlite3.Row | None:
    """webhook entry.id로 계정을 찾는다. graph.instagram.com ID(instagram_user_id)와
    구버전 graph.facebook.com 계열 ID(legacy_instagram_user_id) 둘 다 매칭 대상."""
    with _conn() as con:
        return con.execute(
            "SELECT * FROM instagram_accounts WHERE instagram_user_id = ? OR legacy_instagram_user_id = ?",
            (instagram_user_id, instagram_user_id),
        ).fetchone()


def list_accounts() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("SELECT * FROM instagram_accounts ORDER BY created_at DESC").fetchall()


def set_account_automation_enabled(account_id: str, enabled: bool) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE instagram_accounts SET automation_enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, _now(), account_id),
        )
        con.commit()


def set_account_status(account_id: str, status: str) -> None:
    now = _now()
    with _conn() as con:
        if status == "disconnected":
            con.execute(
                "UPDATE instagram_accounts SET status=?, disconnected_at=?, updated_at=? WHERE id=?",
                (status, now, now, account_id),
            )
        else:
            con.execute(
                "UPDATE instagram_accounts SET status=?, updated_at=? WHERE id=?",
                (status, now, account_id),
            )
        con.commit()


# ---- automation_rules ----


def create_rule(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    instagram_account_id: str,
    name: str,
    scope_type: str,
    media_id: str | None,
    reply_message: str,
    keywords: list[str],
    exclusion_keywords: list[str] | None = None,
    priority: int = 100,
    enabled: bool = True,
    match_type: str = "ANY_KEYWORD",
) -> str:
    from ai_orchestrator.connectors.instagram.instagram_dm_rule_engine import normalize_text

    now = _now()
    rule_id = _new_id()
    with _conn() as con:
        con.execute(
            """INSERT INTO automation_rules
               (id, instagram_account_id, name, enabled, scope_type, media_id, match_type,
                reply_message, priority, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rule_id,
                instagram_account_id,
                name,
                1 if enabled else 0,
                scope_type,
                media_id,
                match_type,
                reply_message,
                priority,
                now,
                now,
            ),
        )
        for kw in keywords:
            con.execute(
                """INSERT INTO automation_rule_keywords
                   (id, rule_id, keyword, normalized_keyword, is_exclusion, created_at)
                   VALUES (?,?,?,?,0,?)""",
                (_new_id(), rule_id, kw, normalize_text(kw), now),
            )
        for kw in exclusion_keywords or []:
            con.execute(
                """INSERT INTO automation_rule_keywords
                   (id, rule_id, keyword, normalized_keyword, is_exclusion, created_at)
                   VALUES (?,?,?,?,1,?)""",
                (_new_id(), rule_id, kw, normalize_text(kw), now),
            )
        con.commit()
    return rule_id


def list_rules(instagram_account_id: str) -> list[dict[str, Any]]:
    with _conn() as con:
        rules = con.execute(
            "SELECT * FROM automation_rules WHERE instagram_account_id = ? ORDER BY priority ASC, created_at ASC",
            (instagram_account_id,),
        ).fetchall()
        out = []
        for r in rules:
            kws = con.execute(
                "SELECT keyword, normalized_keyword, is_exclusion FROM automation_rule_keywords WHERE rule_id = ?",
                (r["id"],),
            ).fetchall()
            out.append(
                {
                    **dict(r),
                    "keywords": [k["keyword"] for k in kws if not k["is_exclusion"]],
                    "exclusion_keywords": [k["keyword"] for k in kws if k["is_exclusion"]],
                }
            )
        return out


def get_rule(rule_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        r = con.execute("SELECT * FROM automation_rules WHERE id = ?", (rule_id,)).fetchone()
        if not r:
            return None
        kws = con.execute(
            "SELECT keyword, normalized_keyword, is_exclusion FROM automation_rule_keywords WHERE rule_id = ?",
            (rule_id,),
        ).fetchall()
        return {
            **dict(r),
            "keywords": [k["keyword"] for k in kws if not k["is_exclusion"]],
            "exclusion_keywords": [k["keyword"] for k in kws if k["is_exclusion"]],
        }


def set_rule_enabled(rule_id: str, enabled: bool) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE automation_rules SET enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, _now(), rule_id),
        )
        con.commit()


def delete_rule(rule_id: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM automation_rule_keywords WHERE rule_id = ?", (rule_id,))
        con.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
        con.commit()


# ---- comment events / dedup ----


def insert_comment_event_if_new(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    instagram_account_id: str,
    comment_id: str,
    media_id: str | None,
    media_product_type: str | None,
    commenter_ig_scoped_id: str | None,
    commenter_username: str | None,
    comment_text: str | None,
    normalized_text: str | None,
    comment_created_at: str | None,
    raw_payload: dict[str, Any],
) -> tuple[str, bool]:
    """반환: (comment_event_id, is_new). 이미 존재하면 기존 id + False."""
    now = _now()
    with _conn() as con:
        try:
            eid = _new_id()
            con.execute(
                """INSERT INTO instagram_comment_events
                   (id, instagram_account_id, comment_id, media_id, media_product_type,
                    commenter_ig_scoped_id, commenter_username, comment_text, normalized_text,
                    comment_created_at, webhook_received_at, raw_payload_json, processing_status,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'RECEIVED',?,?)""",
                (
                    eid,
                    instagram_account_id,
                    comment_id,
                    media_id,
                    media_product_type,
                    commenter_ig_scoped_id,
                    commenter_username,
                    comment_text,
                    normalized_text,
                    comment_created_at,
                    now,
                    json.dumps(raw_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            con.commit()
            return eid, True
        except sqlite3.IntegrityError:
            row = con.execute(
                "SELECT id FROM instagram_comment_events WHERE instagram_account_id=? AND comment_id=?",
                (instagram_account_id, comment_id),
            ).fetchone()
            return (row["id"] if row else ""), False


def update_comment_event_status(
    comment_event_id: str, *, status: str, matched_rule_id: str | None = None, matched_keyword: str | None = None
) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE instagram_comment_events SET processing_status=?, matched_rule_id=?, matched_keyword=?,
               updated_at=? WHERE id=?""",
            (status, matched_rule_id, matched_keyword, _now(), comment_event_id),
        )
        con.commit()


def list_comment_events(instagram_account_id: str, limit: int = 100) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            """SELECT * FROM instagram_comment_events WHERE instagram_account_id = ?
               ORDER BY webhook_received_at DESC LIMIT ?""",
            (instagram_account_id, limit),
        ).fetchall()


# ---- private reply logs / dedup ----


def try_reserve_reply_slot(
    *, instagram_account_id: str, comment_event_id: str, comment_id: str, rule_id: str | None, request_message: str
) -> tuple[str, bool]:
    """댓글당 1회만 PENDING row 생성 시도. 반환: (reply_log_id, reserved).
    UNIQUE(instagram_account_id, comment_id) 로 동시성/중복 재전송을 DB 레벨에서 막는다."""
    now = _now()
    with _conn() as con:
        try:
            rid = _new_id()
            con.execute(
                """INSERT INTO private_reply_logs
                   (id, instagram_account_id, comment_event_id, rule_id, comment_id, request_message,
                    status, attempt_count, first_attempt_at, last_attempt_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,'PENDING',0,?,?,?,?)""",
                (rid, instagram_account_id, comment_event_id, rule_id, comment_id, request_message, now, now, now, now),
            )
            con.commit()
            return rid, True
        except sqlite3.IntegrityError:
            row = con.execute(
                "SELECT id FROM private_reply_logs WHERE instagram_account_id=? AND comment_id=?",
                (instagram_account_id, comment_id),
            ).fetchone()
            return (row["id"] if row else ""), False


def update_reply_result(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    reply_log_id: str,
    *,
    status: str,
    meta_recipient_id: str | None = None,
    meta_message_id: str | None = None,
    meta_error_code: str | None = None,
    meta_error_subcode: str | None = None,
    meta_error_message: str | None = None,
    blocked_reason: str | None = None,
) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """UPDATE private_reply_logs SET status=?, meta_recipient_id=?, meta_message_id=?,
               meta_error_code=?, meta_error_subcode=?, meta_error_message=?, blocked_reason=?,
               attempt_count=attempt_count+1, sent_at=CASE WHEN ?='SENT' THEN ? ELSE sent_at END,
               last_attempt_at=?, updated_at=? WHERE id=?""",
            (
                status,
                meta_recipient_id,
                meta_message_id,
                meta_error_code,
                meta_error_subcode,
                meta_error_message,
                blocked_reason,
                status,
                now,
                now,
                now,
                reply_log_id,
            ),
        )
        con.commit()


def list_reply_logs(instagram_account_id: str, limit: int = 100) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            """SELECT * FROM private_reply_logs WHERE instagram_account_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (instagram_account_id, limit),
        ).fetchall()


# ---- webhook_events (audit) ----


def log_webhook_event(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    *,
    event_type: str | None,
    external_account_id: str | None,
    external_object_id: str | None,
    signature_valid: bool,
    payload_hash: str,
    payload: dict[str, Any],
    status: str = "RECEIVED",
    error_message: str | None = None,
) -> str:
    now = _now()
    eid = _new_id()
    with _conn() as con:
        con.execute(
            """INSERT INTO webhook_events
               (id, provider, event_type, external_account_id, external_object_id, signature_valid,
                payload_hash, payload_json, status, received_at, error_message)
               VALUES (?, 'instagram', ?,?,?,?,?,?,?,?,?)""",
            (
                eid,
                event_type,
                external_account_id,
                external_object_id,
                1 if signature_valid else 0,
                payload_hash,
                json.dumps(payload, ensure_ascii=False),
                status,
                now,
                error_message,
            ),
        )
        con.commit()
    return eid


# ---- dashboard ----


def dashboard_stats(instagram_account_id: str) -> dict[str, Any]:
    with _conn() as con:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        comments_today = con.execute(
            "SELECT COUNT(*) c FROM instagram_comment_events WHERE instagram_account_id=? AND webhook_received_at LIKE ?",
            (instagram_account_id, f"{today}%"),
        ).fetchone()["c"]
        matched_today = con.execute(
            """SELECT COUNT(*) c FROM instagram_comment_events WHERE instagram_account_id=? AND webhook_received_at LIKE ?
               AND processing_status IN ('MATCHED','SENT','QUEUED','PROCESSING')""",
            (instagram_account_id, f"{today}%"),
        ).fetchone()["c"]
        sent_today = con.execute(
            "SELECT COUNT(*) c FROM private_reply_logs WHERE instagram_account_id=? AND created_at LIKE ? AND status='SENT'",
            (instagram_account_id, f"{today}%"),
        ).fetchone()["c"]
        failed_today = con.execute(
            "SELECT COUNT(*) c FROM private_reply_logs WHERE instagram_account_id=? AND created_at LIKE ? AND status='FAILED'",
            (instagram_account_id, f"{today}%"),
        ).fetchone()["c"]
        return {
            "comments_today": comments_today,
            "matched_today": matched_today,
            "dm_sent_today": sent_today,
            "dm_failed_today": failed_today,
        }
