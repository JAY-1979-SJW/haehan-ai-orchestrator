"""L7 Persistence — 네이버 메일 AI 초안·업무 지침·하루 발송 카운터·감사 기록 (sqlite).

기준서: docs/specs/2026-10-02_mailbox_ai_window.md
스키마 버전: `sqlite_schema.apply_schema` (docs/specs/2026-10-01_sqlite_schema_versioning.md). 이 DB 파일은 이 모듈만 소유한다.

설계 원칙
- 초안의 **상태 전이는 원자적**이다(`UPDATE … WHERE status IN (…)` 의 영향 행 수로 판정) — 같은 초안을 두 번 보내지 못한다.
- 받는 사람 전체 주소는 이 DB 에만 둔다. 감사 기록(events)에는 주소를 넣지 않는다(건수만).
- 비밀번호·앱 비밀번호는 저장하지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir

from ai_orchestrator.connectors.naver_mail import draft_states as states
from ai_orchestrator.persistence.sqlite_schema import apply_schema, set_busy_timeout

_DB_PATH = storage_dir() / "naver_mail_drafts.db"

_JSON_FIELDS = ("to", "cc", "bcc", "attachments", "result")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            account TEXT NOT NULL,
            to_json TEXT NOT NULL,
            cc_json TEXT NOT NULL DEFAULT '[]',
            bcc_json TEXT NOT NULL DEFAULT '[]',
            subject TEXT NOT NULL,
            body_text TEXT NOT NULL,
            body_html TEXT NOT NULL DEFAULT '',
            attachments_json TEXT NOT NULL DEFAULT '[]',
            in_reply_to TEXT NOT NULL DEFAULT '',
            references_header TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            approved_by TEXT,
            approved_at TEXT,
            sent_at TEXT,
            result_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_drafts_account_status ON drafts(account, status)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS instructions (
            account TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS send_counter (
            day TEXT NOT NULL,
            account TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, account)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id TEXT NOT NULL,
            at TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        )
        """
    )


_SCHEMA_STEPS = [_schema_v1]


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)  # 자동 커밋, 필요한 곳만 명시 트랜잭션
    set_busy_timeout(con)
    con.row_factory = sqlite3.Row
    try:
        apply_schema(con, _SCHEMA_STEPS)
        yield con
    finally:
        con.close()


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for key, col in (
        ("to", "to_json"),
        ("cc", "cc_json"),
        ("bcc", "bcc_json"),
        ("attachments", "attachments_json"),
        ("result", "result_json"),
    ):
        d[key] = json.loads(d.pop(col) or "null")
    d["references"] = d.pop("references_header")
    return d


def today() -> str:
    """하루 발송 카운터의 날짜 키 — 이 PC 의 날짜."""
    return datetime.now().astimezone().date().isoformat()


# ── 초안 ────────────────────────────────────────────────────────────────


def create_draft(  # noqa: PLR0913 - 초안 한 통의 필드(받는 사람·참조·숨은참조·제목·본문·첨부·답장 헤더·생성자)
    account: str,
    *,
    to: list[str],
    subject: str,
    body_text: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    body_html: str = "",
    attachments: list[dict[str, Any]] | None = None,
    in_reply_to: str = "",
    references: str = "",
    created_by: str = "ai",
) -> dict[str, Any]:
    draft_id = uuid.uuid4().hex
    now = _now()
    expires = (datetime.now(UTC) + timedelta(days=states.DRAFT_TTL_DAYS)).isoformat(timespec="seconds")
    with _conn() as con:
        con.execute(
            "INSERT INTO drafts (id, account, to_json, cc_json, bcc_json, subject, body_text, body_html, attachments_json, "
            "in_reply_to, references_header, status, created_by, created_at, updated_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                draft_id, account, json.dumps(to, ensure_ascii=False), json.dumps(cc or [], ensure_ascii=False),
                json.dumps(bcc or [], ensure_ascii=False), subject, body_text, body_html,
                json.dumps(attachments or [], ensure_ascii=False), in_reply_to, references, states.PENDING,
                created_by, now, now, expires,
            ),
        )  # fmt: skip
        con.execute(
            "INSERT INTO events (draft_id, at, event, detail) VALUES (?,?,?,?)",
            (draft_id, now, "created", f"by={created_by} recipients={len(to) + len(cc or []) + len(bcc or [])}"),
        )
    return get_draft(draft_id) or {}


def get_draft(draft_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        return _row(con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone())


def list_drafts(
    account: str | None = None, statuses: tuple[str, ...] | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM drafts WHERE 1=1"
    args: list[Any] = []
    if account:
        sql += " AND account = ?"
        args.append(account)
    if statuses:
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        args += list(statuses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    with _conn() as con:
        return [d for d in (_row(r) for r in con.execute(sql, args).fetchall()) if d]


def count_pending(account: str) -> int:
    with _conn() as con:
        return int(
            con.execute(
                "SELECT COUNT(*) FROM drafts WHERE account = ? AND status IN (?, ?)", (account, *states.OPEN_STATUSES)
            ).fetchone()[0]
        )


def transition(draft_id: str, to_status: str, *, only_from: tuple[str, ...], **fields: Any) -> bool:
    """상태를 `only_from` 중 하나일 때만 바꾼다(원자적). 바뀌었으면 True — 동시에 두 번 눌러도 한 쪽만 True."""
    allowed = [s for s in only_from if states.can_transition(s, to_status)]
    if not allowed:
        return False
    now = _now()
    sets, args = ["status = ?", "updated_at = ?"], [to_status, now]
    for key, value in fields.items():
        col = {
            "result": "result_json",
            "approved_by": "approved_by",
            "approved_at": "approved_at",
            "sent_at": "sent_at",
        }[key]
        sets.append(f"{col} = ?")
        args.append(json.dumps(value, ensure_ascii=False) if key == "result" else value)
    args += [draft_id, *allowed]
    with _conn() as con:
        cur = con.execute(
            f"UPDATE drafts SET {', '.join(sets)} WHERE id = ? AND status IN ({','.join('?' * len(allowed))})", args
        )  # 열 이름은 위 고정 표에서만 온다
        changed = cur.rowcount == 1
        if changed:
            con.execute(
                "INSERT INTO events (draft_id, at, event, detail) VALUES (?,?,?,?)",
                (draft_id, now, f"status:{to_status}", ""),
            )
    return changed


def expire_old() -> int:
    """유효 기간이 지난 대기 초안을 만료 처리한다."""
    now = _now()
    with _conn() as con:
        ids = [
            r[0]
            for r in con.execute(
                "SELECT id FROM drafts WHERE status IN (?, ?) AND expires_at < ?", (*states.OPEN_STATUSES, now)
            ).fetchall()
        ]
    return sum(1 for i in ids if transition(i, states.EXPIRED, only_from=states.OPEN_STATUSES))


def is_expired(draft: dict[str, Any]) -> bool:
    return str(draft.get("expires_at", "")) < _now()


# ── 하루 발송 카운터 ────────────────────────────────────────────────────


def sent_today(account: str) -> int:
    with _conn() as con:
        row = con.execute("SELECT count FROM send_counter WHERE day = ? AND account = ?", (today(), account)).fetchone()
    return int(row[0]) if row else 0


def add_sent(account: str, n: int = 1) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO send_counter (day, account, count) VALUES (?,?,?) ON CONFLICT(day, account) DO UPDATE SET count = count + excluded.count",
            (today(), account, n),
        )


# ── 업무 지침 ───────────────────────────────────────────────────────────


def get_instructions(account: str) -> str:
    with _conn() as con:
        row = con.execute("SELECT text FROM instructions WHERE account = ?", (account,)).fetchone()
    return str(row[0]) if row else ""


def set_instructions(account: str, text: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO instructions (account, text, updated_at) VALUES (?,?,?) ON CONFLICT(account) DO UPDATE SET text = excluded.text, updated_at = excluded.updated_at",
            (account, text, _now()),
        )


def events(draft_id: str) -> list[dict[str, Any]]:
    with _conn() as con:
        return [
            dict(r)
            for r in con.execute(
                "SELECT at, event, detail FROM events WHERE draft_id = ? ORDER BY id", (draft_id,)
            ).fetchall()
        ]
