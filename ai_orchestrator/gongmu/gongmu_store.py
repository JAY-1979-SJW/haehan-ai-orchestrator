"""L7 Persistence — 건설업 공무 업무판 (현장·계약·기준표·업무·서류·변경 이력, sqlite).

기준서: docs/specs/2026-10-02_construction_gongmu.md (§3-1)
스키마 버전: `sqlite_schema.apply_schema`. 이 DB 파일은 이 모듈만 소유한다.

- **이력(`events`)은 추가만 한다**(수정·삭제 없음). 현장·계약·업무는 삭제 API 가 없다(상태 '해당 없음'으로 닫는다).
- 업무는 `dedupe_key`(UNIQUE)로 중복 생성을 막는다 — 같은 키를 다시 넣어도 무시된다.
- 기준표는 코드 상수(`DEFAULT_CATALOG`)에서 **없는 코드만** 시드한다(사용자가 고친 값은 덮어쓰지 않는다).
- 계약서 원본·인증서·비밀번호는 저장하지 않는다(서류는 경로·해시만).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir

from ..persistence.sqlite_schema import apply_schema, set_busy_timeout
from . import gongmu_defaults as defaults

_DB_PATH = storage_dir() / "gongmu.db"

_SITE_FIELDS = (
    "name",
    "client",
    "location",
    "start_date",
    "end_date",
    "role",
    "contract_amount",
    "manager",
    "memo",
)
_TASK_EDITABLE = ("due_date", "assignee", "memo")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex


def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, client TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '', start_date TEXT, end_date TEXT,
            role TEXT NOT NULL, contract_amount INTEGER, manager TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id TEXT PRIMARY KEY, site_id TEXT NOT NULL, counterparty TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL, amount INTEGER, contract_date TEXT,
            changes TEXT NOT NULL DEFAULT '[]', file_path TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_gm_contract_site ON contracts(site_id)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS task_catalog (
            code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
            trigger TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', basis TEXT NOT NULL DEFAULT '',
            condition TEXT NOT NULL DEFAULT '{}', due_rule TEXT NOT NULL DEFAULT '{}',
            docs TEXT NOT NULL DEFAULT '[]', submit_to TEXT NOT NULL DEFAULT '',
            verify_law INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, site_id TEXT NOT NULL,
            contract_id TEXT NOT NULL DEFAULT '', catalog_code TEXT NOT NULL, period TEXT NOT NULL DEFAULT '',
            due_date TEXT, status TEXT NOT NULL, assignee TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_gm_task_site ON tasks(site_id, status)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS task_docs (
            task_id TEXT NOT NULL, doc_name TEXT NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
            PRIMARY KEY (task_id, doc_name)
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
            action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")


def _schema_v2(con: sqlite3.Connection) -> None:
    # G2 — AI 초안(승인 대기). 확정·취소는 사람만, 한 번 정해지면 바뀌지 않는다.
    con.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            site_id TEXT, task_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
            created_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            decided_by TEXT NOT NULL DEFAULT '', decided_at TEXT
        )""")


# 한 번 배포된 단계는 수정하지 않고 새 단계를 뒤에 추가한다
_SCHEMA_STEPS = [_schema_v1, _schema_v2]


@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, isolation_level=None)
    set_busy_timeout(con)
    con.row_factory = sqlite3.Row
    try:
        apply_schema(con, _SCHEMA_STEPS)
        _seed_catalog_once(con)
        yield con
    finally:
        con.close()


_SEEDED: set[tuple[str, int]] = (
    set()
)  # (DB 경로, inode) — 프로세스당 1회. 파일이 지워져 새로 생기면 inode 가 달라 다시 시드한다


def _seed_catalog_once(con: sqlite3.Connection) -> None:
    """_seed_catalog 는 INSERT OR IGNORE(멱등)이므로 DB 파일당 프로세스에서 한 번만 돌려 연결마다 반복되는 쓰기를 없앤다."""
    try:
        key = (str(_DB_PATH), _DB_PATH.stat().st_ino)
    except OSError:
        _seed_catalog(con)
        return
    if key in _SEEDED:
        return
    _seed_catalog(con)
    _SEEDED.add(key)


def _seed_catalog(con: sqlite3.Connection) -> None:
    """없는 코드만 넣는다. 화면이 요청 여러 개를 동시에 보내면 연결마다 시드가 겹치므로 INSERT OR IGNORE 로 경합을 흡수한다."""
    for item in defaults.DEFAULT_CATALOG:
        con.execute(
            "INSERT OR IGNORE INTO task_catalog(code,name,category,trigger,description,basis,condition,due_rule,docs,"
            "submit_to,verify_law,enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
            (
                item["code"],
                item["name"],
                item["category"],
                item["trigger"],
                item["description"],
                item["basis"],
                json.dumps(item["condition"], ensure_ascii=False),
                json.dumps(item["due_rule"], ensure_ascii=False),
                json.dumps(item["docs"], ensure_ascii=False),
                item["submit_to"],
                int(item["verify_law"]),
            ),
        )


def _log(con: sqlite3.Connection, actor: str, action: str, target: str, detail: str = "") -> None:
    con.execute(
        "INSERT INTO events(at,actor,action,target,detail) VALUES(?,?,?,?,?)", (_now(), actor, action, target, detail)
    )


def _catalog_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in ("condition", "due_rule", "docs"):
        data[key] = json.loads(data[key])
    data["verify_law"], data["enabled"] = bool(data["verify_law"]), bool(data["enabled"])
    return data


def _contract_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["changes"] = json.loads(data["changes"])
    return data


# ── 설정·기준표 ───────────────────────────────────────────────────────────


def get_settings() -> dict[str, int]:
    with _conn() as con:
        stored = {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings")}
    return defaults.merged_settings(stored)


def update_settings(values: dict[str, int], *, actor: str) -> dict[str, int]:
    with _conn() as con:
        for key, value in values.items():
            con.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, str(int(value)), _now()),
            )
        _log(con, actor, "settings.update", "settings", json.dumps(values, ensure_ascii=False))
    return get_settings()


def list_catalog() -> list[dict[str, Any]]:
    with _conn() as con:
        return [_catalog_row(r) for r in con.execute("SELECT * FROM task_catalog ORDER BY category, code")]


# ── 현장 ──────────────────────────────────────────────────────────────────


def create_site(fields: dict[str, Any], *, actor: str) -> dict[str, Any]:
    site_id, now = _id(), _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO sites(id,name,client,location,start_date,end_date,role,contract_amount,manager,memo,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (site_id, *(fields.get(k) for k in _SITE_FIELDS), now, now),  # 값 정리는 서비스가 끝낸다
        )
        _log(con, actor, "site.create", site_id, fields.get("name", ""))
    return get_site(site_id)  # type: ignore[return-value]


def update_site(site_id: str, fields: dict[str, Any], *, actor: str) -> dict[str, Any] | None:
    changes = {k: v for k, v in fields.items() if k in _SITE_FIELDS}
    with _conn() as con:
        if con.execute("SELECT 1 FROM sites WHERE id=?", (site_id,)).fetchone() is None:
            return None
        if changes:
            sets = ",".join(f"{k}=?" for k in changes)  # 키는 _SITE_FIELDS 화이트리스트
            con.execute(f"UPDATE sites SET {sets}, updated_at=? WHERE id=?", (*changes.values(), _now(), site_id))
            _log(con, actor, "site.update", site_id, json.dumps(changes, ensure_ascii=False, default=str))
    return get_site(site_id)


def get_site(site_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    return dict(row) if row else None


def list_sites() -> list[dict[str, Any]]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM sites ORDER BY created_at DESC")]


# ── 계약 ──────────────────────────────────────────────────────────────────


def create_contract(site_id: str, fields: dict[str, Any], *, actor: str) -> dict[str, Any] | None:
    contract_id = _id()
    with _conn() as con:
        if con.execute("SELECT 1 FROM sites WHERE id=?", (site_id,)).fetchone() is None:
            return None
        con.execute(
            "INSERT INTO contracts(id,site_id,counterparty,kind,amount,contract_date,file_path,memo,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                contract_id,
                site_id,
                fields.get("counterparty", ""),
                fields["kind"],
                fields.get("amount"),
                fields.get("contract_date"),
                fields.get("file_path", ""),
                fields.get("memo", ""),
                _now(),
            ),
        )
        _log(con, actor, "contract.create", contract_id, f"site={site_id}")
    return get_contract(contract_id)


def add_contract_change(contract_id: str, change: dict[str, Any], *, actor: str) -> dict[str, Any] | None:
    """변경 이력을 **덧붙인다**(기존 항목은 고치지 않는다). 금액이 바뀌면 현재 금액도 갱신한다."""
    with _conn() as con:
        row = con.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
        if row is None:
            return None
        changes = json.loads(row["changes"])
        changes.append({**change, "recorded_at": _now()})
        amount = change.get("amount") if change.get("amount") is not None else row["amount"]
        con.execute(
            "UPDATE contracts SET changes=?, amount=? WHERE id=?",
            (json.dumps(changes, ensure_ascii=False), amount, contract_id),
        )
        _log(con, actor, "contract.change", contract_id, json.dumps(change, ensure_ascii=False))
    return get_contract(contract_id)


def get_contract(contract_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
    return _contract_row(row) if row else None


def list_contracts(site_id: str) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM contracts WHERE site_id=? ORDER BY created_at", (site_id,)).fetchall()
    return [_contract_row(r) for r in rows]


# ── 업무 ──────────────────────────────────────────────────────────────────


def insert_planned(planned: list[defaults.PlannedTask], *, actor: str) -> list[str]:
    """계획된 업무를 넣는다. dedupe_key 가 이미 있으면 건너뛴다. 새로 만든 task id 목록을 돌려준다."""
    created: list[str] = []
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            for item in planned:
                task_id, now = _id(), _now()
                cur = con.execute(
                    "INSERT OR IGNORE INTO tasks(id,dedupe_key,site_id,contract_id,catalog_code,period,due_date,status,"
                    "reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        item.dedupe_key,
                        item.site_id,
                        item.contract_id,
                        item.catalog_code,
                        item.period,
                        item.due_date.isoformat() if item.due_date else None,
                        defaults.TODO,
                        item.reason,
                        now,
                        now,
                    ),
                )
                if cur.rowcount:
                    created.append(task_id)
                    _log(con, actor, "task.create", task_id, f"{item.catalog_code} {item.reason}")
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
    return created


_TASK_SELECT = (
    "SELECT t.*, c.name AS catalog_name, c.category, c.basis, c.verify_law, c.submit_to, c.docs AS catalog_docs, "
    "s.name AS site_name FROM tasks t "
    "JOIN task_catalog c ON c.code = t.catalog_code JOIN sites s ON s.id = t.site_id"
)


def _task_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["verify_law"] = bool(data["verify_law"])
    data["catalog_docs"] = json.loads(data["catalog_docs"])
    return data


def list_tasks(site_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    where, args = [], []
    if site_id:
        where.append("t.site_id=?")
        args.append(site_id)
    if status:
        where.append("t.status=?")
        args.append(status)
    sql = _TASK_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY (t.due_date IS NULL), t.due_date, t.catalog_code"
    with _conn() as con:
        return [_task_row(r) for r in con.execute(sql, args)]


def get_task(task_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute(_TASK_SELECT + " WHERE t.id=?", (task_id,)).fetchone()
        if row is None:
            return None
        data = _task_row(row)
        data["docs"] = [
            dict(r) | {"ready": bool(r["ready"])}
            for r in con.execute("SELECT * FROM task_docs WHERE task_id=? ORDER BY doc_name", (task_id,))
        ]
    return data


def set_task_status(task_id: str, status: str, *, actor: str) -> bool:
    if status not in defaults.STATUSES:
        raise ValueError(f"알 수 없는 상태: {status}")
    with _conn() as con:
        done_at = _now() if status == defaults.DONE else None
        cur = con.execute(
            "UPDATE tasks SET status=?, completed_at=?, updated_at=? WHERE id=?", (status, done_at, _now(), task_id)
        )
        if cur.rowcount:
            _log(con, actor, "task.status", task_id, status)
        return bool(cur.rowcount)


def update_task(task_id: str, fields: dict[str, Any], *, actor: str) -> bool:
    changes = {k: v for k, v in fields.items() if k in _TASK_EDITABLE}
    if not changes:
        return False
    with _conn() as con:
        sets = ",".join(f"{k}=?" for k in changes)  # 키는 _TASK_EDITABLE 화이트리스트
        cur = con.execute(f"UPDATE tasks SET {sets}, updated_at=? WHERE id=?", (*changes.values(), _now(), task_id))
        if cur.rowcount:
            _log(con, actor, "task.update", task_id, json.dumps(changes, ensure_ascii=False))
        return bool(cur.rowcount)


def set_doc(task_id: str, doc_name: str, *, ready: bool, file_path: str, sha256: str, actor: str) -> bool:
    with _conn() as con:
        if con.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
            return False
        con.execute(
            "INSERT INTO task_docs(task_id,doc_name,ready,file_path,sha256,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(task_id,doc_name) DO UPDATE SET ready=excluded.ready, file_path=excluded.file_path, "
            "sha256=excluded.sha256, updated_at=excluded.updated_at",
            (task_id, doc_name, int(ready), file_path, sha256, _now()),
        )
        _log(con, actor, "doc.set", task_id, f"{doc_name} ready={ready}")
    return True


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(limit),))]


# ── G2 AI 초안 ────────────────────────────────────────────────────────────


def create_draft(fields: dict[str, Any], *, actor: str) -> dict[str, Any]:
    draft_id = _id()
    with _conn() as con:
        con.execute(
            "INSERT INTO drafts(id,kind,title,body,site_id,task_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                draft_id,
                fields["kind"],
                fields["title"],
                fields["body"],
                fields.get("site_id"),
                fields.get("task_id"),
                actor,
                _now(),
            ),
        )
        _log(con, actor, "draft.create", draft_id, fields["kind"])
    created = get_draft(draft_id)
    if created is None:  # 방금 넣은 행이므로 없을 수 없다 — 조용히 None 을 돌려주지 않는다
        raise RuntimeError("초안 저장 직후 조회에 실패했습니다")
    return created


def get_draft(draft_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    return dict(row) if row else None


def list_drafts(status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM drafts"
    args: tuple[str, ...] = ()
    if status:
        sql, args = sql + " WHERE status=?", (status,)
    with _conn() as con:
        return [dict(r) for r in con.execute(sql + " ORDER BY created_at DESC, id", args)]


def decide_draft(draft_id: str, *, confirm: bool, actor: str) -> dict[str, Any] | None:
    """승인 대기 초안을 확정/취소한다. 이미 결정됐거나 없는 초안은 None. 확정하면 연결된 업무 메모 끝에 덧붙인다(같은 트랜잭션)."""
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            row = con.execute("SELECT * FROM drafts WHERE id=? AND status='pending'", (draft_id,)).fetchone()
            if row is None:
                con.execute("ROLLBACK")
                return None
            now = _now()
            con.execute(
                "UPDATE drafts SET status=?, decided_by=?, decided_at=? WHERE id=?",
                ("confirmed" if confirm else "cancelled", actor, now, draft_id),
            )
            if confirm and row["task_id"]:
                note = f"[AI 초안 확정 {now[:10]}] {row['title']}\n{row['body']}"
                con.execute(
                    "UPDATE tasks SET memo=CASE WHEN memo='' THEN ? ELSE memo || char(10) || char(10) || ? END, "
                    "updated_at=? WHERE id=?",
                    (note, note, now, row["task_id"]),
                )
            _log(con, actor, "draft.confirm" if confirm else "draft.cancel", draft_id, row["kind"])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return get_draft(draft_id)
