"""L7 Persistence — 작업 기록 저장소(Work Record Store, WRS) SQLite 스토어.

기준서: docs/specs/2026-10-05_work_record_store.md (M1). 이 DB 파일은 이 모듈만 소유한다.
스키마 버전: `sqlite_schema.apply_schema` (한 번 배포된 단계는 수정하지 않고 뒤에 추가).

- 메타데이터는 SQLite, 산출물은 파일(경로+sha256+크기). 값은 기본 미저장 — 화이트리스트 밖 키·과대 값은 거부한다.
- job 상태 전이는 허용표(L1)만, 원자적 `UPDATE ... WHERE status IN (...)` + `BEGIN IMMEDIATE` 로 한다.
- `wrs_events` 는 append-only(트리거로 UPDATE/DELETE 차단). `wrs_artifacts` 도 UPDATE 불가(불변). 하드 삭제 API 없음.
- 조회는 `Scope`(테넌트·소유자) 필수. 쓰기 메서드는 job_id 만 받는다 — 권한 판정은 서비스(L6, M2)가 `get_job(scope)` 로 선행한다.
- 이 모듈은 CDP·브라우저·네트워크·환경변수를 쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import storage_dir

from ..persistence.sqlite_schema import apply_schema, set_busy_timeout
from .work_record import (
    ARTIFACT_MAX_BYTES,
    ERROR_MAX,
    EVENT_DETAIL_MAX,
    JOB_INITIAL_STATUSES,
    JOB_TERMINAL,
    PAGE_LIMIT_MAX,
    SUMMARY_MAX,
    Artifact,
    ArtifactSpec,
    Event,
    InvalidTransitionError,
    Job,
    JobDraft,
    JobPage,
    JobPatch,
    JobQuery,
    JobStatus,
    Link,
    NotFoundError,
    Scope,
    Step,
    StepDraft,
    StepStatus,
    StepUpdate,
    ValidationError,
    can_transition_step,
    canonical_json,
    check_text,
    compute_input_hash,
    job_sources_for,
    onboard_host,
    validate_actor,
    validate_artifact_kind,
    validate_artifact_rel_path,
    validate_event_name,
    validate_host,
    validate_iso,
    validate_job_kind,
    validate_job_status,
    validate_link_type,
    validate_media_type,
    validate_params,
    validate_ref,
    validate_retention,
    validate_risk,
    validate_sensitivity,
    validate_step_kind,
    validate_step_status,
    validate_tags,
    validate_tenant,
    validate_title,
)

_REPO_ROOT = repo_root()
_DB_PATH = storage_dir() / "work_records.db"
# 산출물으로 참조할 수 있는 루트(저장소 기준 상대). 두 번째는 6a 지도 이력 파일 참조용(기준서 §4 조정 제안 c).
_DEFAULT_ARTIFACT_ROOTS = ("data/work_records", "data/site_task_map")

_LINEAGE = ("rerun_of", "forked_from", "resumed_from")
_HASH_CHUNK = 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ── 스키마 ────────────────────────────────────────────────────────────────
def _schema_v1(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            site_id TEXT,
            host TEXT,
            input_params_json TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            starred INTEGER NOT NULL DEFAULT 0 CHECK (starred IN (0, 1)),
            archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
            rerun_of TEXT REFERENCES wrs_jobs(job_id),
            forked_from TEXT REFERENCES wrs_jobs(job_id),
            resumed_from TEXT REFERENCES wrs_jobs(job_id),
            version INTEGER NOT NULL DEFAULT 1,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            created_by TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            retention_class TEXT NOT NULL DEFAULT 'standard',
            workflow_run_id TEXT,
            task_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            CHECK ((rerun_of IS NOT NULL) + (forked_from IS NOT NULL) + (resumed_from IS NOT NULL) <= 1),
            CHECK (rerun_of IS NULL OR rerun_of <> job_id),
            CHECK (forked_from IS NULL OR forked_from <> job_id),
            CHECK (resumed_from IS NULL OR resumed_from <> job_id)
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_status ON wrs_jobs(status, updated_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_host ON wrs_jobs(host, updated_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_kind ON wrs_jobs(kind, created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_rerun_of ON wrs_jobs(rerun_of)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_forked_from ON wrs_jobs(forked_from)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_resumed_from ON wrs_jobs(resumed_from)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_input_hash ON wrs_jobs(input_hash)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_jobs_scope ON wrs_jobs(tenant_id, created_by, created_at)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_job_tags (
            job_id TEXT NOT NULL REFERENCES wrs_jobs(job_id),
            tag TEXT NOT NULL,
            PRIMARY KEY (job_id, tag)
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_tags_tag ON wrs_job_tags(tag)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_steps (
            job_id TEXT NOT NULL REFERENCES wrs_jobs(job_id),
            seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            risk TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            input_summary TEXT,
            output_summary TEXT,
            error TEXT,
            approval_ref TEXT,
            attempt INTEGER NOT NULL DEFAULT 1,
            irreversible INTEGER NOT NULL DEFAULT 0 CHECK (irreversible IN (0, 1)),
            PRIMARY KEY (job_id, seq)
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_artifacts (
            artifact_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES wrs_jobs(job_id),
            step_seq INTEGER,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            sensitivity TEXT NOT NULL,
            retention_class TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id, step_seq) REFERENCES wrs_steps(job_id, seq)
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_artifacts_job ON wrs_artifacts(job_id)")
    con.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_wrs_artifacts_immutable BEFORE UPDATE ON wrs_artifacts
        BEGIN SELECT RAISE(ABORT, 'wrs_artifacts is immutable'); END""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES wrs_jobs(job_id),
            step_seq INTEGER,
            at TEXT NOT NULL,
            actor TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wrs_events_job ON wrs_events(job_id, event_id)")
    con.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_wrs_events_no_update BEFORE UPDATE ON wrs_events
        BEGIN SELECT RAISE(ABORT, 'wrs_events is append-only'); END""")
    con.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_wrs_events_no_delete BEFORE DELETE ON wrs_events
        BEGIN SELECT RAISE(ABORT, 'wrs_events is append-only'); END""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS wrs_links (
            job_id TEXT NOT NULL REFERENCES wrs_jobs(job_id),
            link_type TEXT NOT NULL,
            ref_store TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (job_id, link_type, ref_store, ref_id)
        )""")


_SCHEMA_STEPS = [_schema_v1]


# ── 변환 보조 ─────────────────────────────────────────────────────────────
def _sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK):
            total += len(chunk)
            if total > ARTIFACT_MAX_BYTES:
                raise ValidationError("artifact 파일이 너무 크다")
            digest.update(chunk)
    return digest.hexdigest(), total


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_TAG_EXISTS = "EXISTS (SELECT 1 FROM wrs_job_tags t WHERE t.job_id = j.job_id AND t.tag = ?)"
_TEXT_MATCH = (
    "(j.title LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM wrs_job_tags t2"
    " WHERE t2.job_id = j.job_id AND t2.tag LIKE ? ESCAPE '\\'))"
)


def _filter_clauses(q: JobQuery) -> tuple[list[str], list[Any]]:
    """JobQuery 를 (WHERE 조각, 바인딩) 으로. 값은 전부 검증 후 바인딩한다."""
    rules: tuple[tuple[Any, str, Callable[[Any], Any]], ...] = (
        (q.status, "j.status = ?", lambda v: validate_job_status(v).value),
        (q.host, "j.host = ?", validate_host),
        (q.kind, "j.kind = ?", validate_job_kind),
        (q.kind_prefix, "j.kind LIKE ? ESCAPE '\\'", lambda v: _like_escape(v) + "%"),
        (q.tag, _TAG_EXISTS, lambda v: validate_tags([v])[0]),
        (q.starred, "j.starred = ?", int),
        (q.archived, "j.archived = ?", int),
        (q.created_from, "j.created_at >= ?", lambda v: validate_iso(v, "created_from")),
        (q.created_to, "j.created_at <= ?", lambda v: validate_iso(v, "created_to")),
    )
    clauses: list[str] = []
    args: list[Any] = []
    for value, clause, convert in rules:
        if value is not None:
            clauses.append(clause)
            args.append(convert(value))
    if q.text:
        pattern = f"%{_like_escape(q.text)}%"
        clauses.append(_TEXT_MATCH)
        args += [pattern, pattern]
    return clauses, args


def _job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        job_id=row["job_id"],
        kind=row["kind"],
        title=row["title"],
        status=JobStatus(row["status"]),
        site_id=row["site_id"],
        host=row["host"],
        params=json.loads(row["input_params_json"]),
        input_hash=row["input_hash"],
        tags=tuple(json.loads(row["tags_json"])),
        starred=bool(row["starred"]),
        archived=bool(row["archived"]),
        rerun_of=row["rerun_of"],
        forked_from=row["forked_from"],
        resumed_from=row["resumed_from"],
        version=row["version"],
        tenant_id=row["tenant_id"],
        created_by=row["created_by"],
        updated_by=row["updated_by"],
        retention_class=row["retention_class"],
        workflow_run_id=row["workflow_run_id"],
        task_id=row["task_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )


def _step_from_row(row: sqlite3.Row) -> Step:
    return Step(
        job_id=row["job_id"],
        seq=row["seq"],
        kind=row["kind"],
        status=StepStatus(row["status"]),
        risk=row["risk"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        input_summary=row["input_summary"],
        output_summary=row["output_summary"],
        error=row["error"],
        approval_ref=row["approval_ref"],
        attempt=row["attempt"],
        irreversible=bool(row["irreversible"]),
    )


def _artifact_from_row(row: sqlite3.Row) -> Artifact:
    return Artifact(
        artifact_id=row["artifact_id"],
        job_id=row["job_id"],
        step_seq=row["step_seq"],
        kind=row["kind"],
        path=row["path"],
        sha256=row["sha256"],
        size_bytes=row["size_bytes"],
        media_type=row["media_type"],
        sensitivity=row["sensitivity"],
        retention_class=row["retention_class"],
        created_at=row["created_at"],
    )


class WorkRecordStore:
    """WRS SQLite 스토어. 한 인스턴스 = 한 DB 파일 + 산출물 허용 루트 집합."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        base_dir: Path | str | None = None,
        allowed_roots: Sequence[str] | None = None,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DB_PATH
        self._base_dir = Path(base_dir).resolve() if base_dir is not None else _REPO_ROOT
        self._roots = tuple((self._base_dir / r).resolve() for r in (allowed_roots or _DEFAULT_ARTIFACT_ROOTS))
        self._now = now_fn or _now

    # ── 연결·트랜잭션 ─────────────────────────────────────────────────────
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self._db_path), timeout=30, isolation_level=None)
        set_busy_timeout(con)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys = ON")
            apply_schema(con, _SCHEMA_STEPS)
            yield con
        finally:
            con.close()

    @staticmethod
    @contextmanager
    def _tx(con: sqlite3.Connection) -> Iterator[None]:
        con.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")

    # ── 내부 조회 ─────────────────────────────────────────────────────────
    @staticmethod
    def _scope_sql(scope: Scope, alias: str = "") -> tuple[str, list[Any]]:
        pre = f"{alias}." if alias else ""
        sql = f"{pre}tenant_id = ?"
        args: list[Any] = [scope.tenant_id]
        if scope.created_by is not None:
            sql += f" AND {pre}created_by = ?"
            args.append(scope.created_by)
        return sql, args

    @staticmethod
    def _live_job(con: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        row = con.execute("SELECT * FROM wrs_jobs WHERE job_id = ? AND deleted_at IS NULL", (job_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"job 없음: {job_id}")
        return row

    def _visible_job(
        self, con: sqlite3.Connection, job_id: str, scope: Scope, *, include_deleted: bool = False
    ) -> sqlite3.Row:
        sql, args = self._scope_sql(scope)
        row = con.execute(f"SELECT * FROM wrs_jobs WHERE job_id = ? AND {sql}", [job_id, *args]).fetchone()
        if row is None or (row["deleted_at"] is not None and not include_deleted):
            raise NotFoundError(f"job 없음: {job_id}")
        return row

    def _event(
        self,
        con: sqlite3.Connection,
        job_id: str,
        event: str,
        actor: str,
        detail: str | None,
        step_seq: int | None = None,
    ) -> int:
        cur = con.execute(
            "INSERT INTO wrs_events (job_id, step_seq, at, actor, event, detail) VALUES (?,?,?,?,?,?)",
            (job_id, step_seq, self._now(), actor, event, detail),
        )
        return int(cur.lastrowid or 0)

    # ── job ──────────────────────────────────────────────────────────────
    def create_job(self, draft: JobDraft) -> str:
        kind = validate_job_kind(draft.kind)
        title = validate_title(draft.title)
        actor = validate_actor(draft.actor)
        tenant = validate_tenant(draft.tenant_id)
        params = validate_params(draft.params)
        tags = validate_tags(draft.tags)
        retention = validate_retention(draft.retention_class)
        status = JobStatus(draft.status)
        if status not in JOB_INITIAL_STATUSES:
            raise ValidationError(f"생성 시 허용되지 않는 초기 상태: {status.value}")
        host = validate_host(draft.host) if draft.host is not None else None
        onboard = onboard_host(kind)
        if onboard is not None:
            if host is not None and host != onboard:
                raise ValidationError("kind 의 host 와 host 필드가 다르다")
            host = onboard
        site_id = validate_ref(draft.site_id, "site_id") if draft.site_id is not None else None
        run_id = validate_ref(draft.workflow_run_id, "workflow_run_id") if draft.workflow_run_id is not None else None
        task_id = validate_ref(draft.task_id, "task_id") if draft.task_id is not None else None
        parents = {k: getattr(draft, k) for k in _LINEAGE if getattr(draft, k) is not None}
        if len(parents) > 1:
            raise ValidationError("rerun_of/forked_from/resumed_from 는 하나만 지정할 수 있다")
        for parent in parents.values():
            validate_ref(parent, "parent job_id")

        job_id = uuid.uuid4().hex
        input_hash = compute_input_hash(kind, host, params)
        now = self._now()
        with self._conn() as con, self._tx(con):
            for parent in parents.values():
                if (
                    con.execute(
                        "SELECT 1 FROM wrs_jobs WHERE job_id = ? AND tenant_id = ?", (parent, tenant)
                    ).fetchone()
                    is None
                ):
                    raise NotFoundError(f"부모 job 없음: {parent}")
            version = int(
                con.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM wrs_jobs WHERE input_hash = ? AND tenant_id = ?",
                    (input_hash, tenant),
                ).fetchone()[0]
            )
            con.execute(
                "INSERT INTO wrs_jobs (job_id, kind, title, status, site_id, host, input_params_json, input_hash,"
                " tags_json, rerun_of, forked_from, resumed_from, version, tenant_id, created_by, updated_by,"
                " retention_class, workflow_run_id, task_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id, kind, title, status.value, site_id, host, canonical_json(params), input_hash,
                    json.dumps(list(tags), ensure_ascii=False), parents.get("rerun_of"), parents.get("forked_from"),
                    parents.get("resumed_from"), version, tenant, actor, actor, retention, run_id, task_id, now, now,
                ),
            )  # fmt: skip
            con.executemany("INSERT INTO wrs_job_tags (job_id, tag) VALUES (?, ?)", [(job_id, t) for t in tags])
            self._event(con, job_id, "job_created", actor, f"kind={kind} status={status.value}")
        return job_id

    def get_job(self, job_id: str, scope: Scope, *, include_deleted: bool = False) -> Job | None:
        sql, args = self._scope_sql(scope)
        with self._conn() as con:
            row = con.execute(f"SELECT * FROM wrs_jobs WHERE job_id = ? AND {sql}", [job_id, *args]).fetchone()
        if row is None or (row["deleted_at"] is not None and not include_deleted):
            return None
        return _job_from_row(row)

    def list_jobs(self, scope: Scope, query: JobQuery | None = None, *, limit: int = 30, offset: int = 0) -> JobPage:
        q = query or JobQuery()
        sql, args = self._scope_sql(scope, "j")
        where = [sql]
        if not q.include_deleted:
            where.append("j.deleted_at IS NULL")
        extra, extra_args = _filter_clauses(q)
        where += extra
        args += extra_args
        limit = max(1, min(PAGE_LIMIT_MAX, int(limit)))
        offset = max(0, int(offset))
        clause = " AND ".join(where)
        with self._conn() as con:
            total = int(con.execute(f"SELECT COUNT(*) FROM wrs_jobs j WHERE {clause}", args).fetchone()[0])
            rows = con.execute(
                f"SELECT j.* FROM wrs_jobs j WHERE {clause} ORDER BY j.created_at DESC, j.rowid DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return JobPage(items=[_job_from_row(r) for r in rows], total=total, limit=limit, offset=offset)

    def list_children(self, job_id: str, scope: Scope, *, relation: str) -> list[Job]:
        """`job_id` 를 부모로 가진 job 들(relation: rerun_of / forked_from / resumed_from)."""
        if relation not in _LINEAGE:
            raise ValidationError(f"허용되지 않는 relation: {relation!r}")
        sql, args = self._scope_sql(scope, "j")
        with self._conn() as con:
            rows = con.execute(
                f"SELECT j.* FROM wrs_jobs j WHERE j.{relation} = ? AND j.deleted_at IS NULL AND {sql}"
                " ORDER BY j.created_at, j.rowid",
                [job_id, *args],
            ).fetchall()
        return [_job_from_row(r) for r in rows]

    def transition_job(self, job_id: str, new_status: str, *, actor: str, detail: str | None = None) -> None:
        """허용 전이만 원자적으로 적용한다. 허용되지 않거나 동시 전이에서 졌으면 InvalidTransitionError."""
        new = validate_job_status(new_status)
        actor = validate_actor(actor)
        detail = check_text(detail, "detail", EVENT_DETAIL_MAX // 2)
        sources = job_sources_for(new)
        with self._conn() as con, self._tx(con):
            old = self._live_job(con, job_id)["status"]
            changed = 0
            if sources:
                marks = ",".join("?" * len(sources))
                changed = con.execute(
                    f"UPDATE wrs_jobs SET status = ?, updated_by = ?, updated_at = ?"
                    f" WHERE job_id = ? AND deleted_at IS NULL AND status IN ({marks})",
                    [new.value, actor, self._now(), job_id, *[s.value for s in sources]],
                ).rowcount
            if changed != 1:
                raise InvalidTransitionError(f"{old} -> {new.value} 전이는 허용되지 않는다")
            self._event(
                con, job_id, "status_changed", actor, f"{old} -> {new.value}" + (f": {detail}" if detail else "")
            )

    def patch_job(self, job_id: str, patch: JobPatch, *, actor: str) -> None:
        """가변 필드(title/tags/starred/archived)만 바꾼다."""
        actor = validate_actor(actor)
        sets: list[str] = []
        args: list[Any] = []
        if patch.title is not None:
            sets.append("title = ?")
            args.append(validate_title(patch.title))
        clean_tags = validate_tags(patch.tags) if patch.tags is not None else None
        if clean_tags is not None:
            sets.append("tags_json = ?")
            args.append(json.dumps(list(clean_tags), ensure_ascii=False))
        for name in ("starred", "archived"):
            value = getattr(patch, name)
            if value is not None:
                sets.append(f"{name} = ?")
                args.append(int(bool(value)))
        if not sets:
            raise ValidationError("변경할 필드가 없다")
        changed = ",".join(c.split(" = ")[0].removesuffix("_json") for c in sets)
        with self._conn() as con, self._tx(con):
            self._live_job(con, job_id)
            con.execute(
                f"UPDATE wrs_jobs SET {', '.join(sets)}, updated_by = ?, updated_at = ? WHERE job_id = ?",
                [*args, actor, self._now(), job_id],
            )
            if clean_tags is not None:
                con.execute("DELETE FROM wrs_job_tags WHERE job_id = ?", (job_id,))
                con.executemany(
                    "INSERT INTO wrs_job_tags (job_id, tag) VALUES (?, ?)", [(job_id, t) for t in clean_tags]
                )
            self._event(con, job_id, "job_patched", actor, changed)

    def soft_delete_job(self, job_id: str, *, actor: str) -> None:
        """소프트 삭제(목록 제외). 이벤트·산출물 메타는 보존한다. 실행 중 job 은 거부."""
        actor = validate_actor(actor)
        with self._conn() as con, self._tx(con):
            row = self._live_job(con, job_id)
            if row["status"] == JobStatus.RUNNING.value:
                raise InvalidTransitionError("실행 중인 job 은 삭제할 수 없다")
            now = self._now()
            con.execute(
                "UPDATE wrs_jobs SET deleted_at = ?, updated_by = ?, updated_at = ? WHERE job_id = ?",
                (now, actor, now, job_id),
            )
            self._event(con, job_id, "job_deleted", actor, None)

    # ── step ─────────────────────────────────────────────────────────────
    def add_step(self, job_id: str, draft: StepDraft, *, actor: str = "system") -> int:
        kind = validate_step_kind(draft.kind)
        risk = validate_risk(draft.risk)
        status = StepStatus(draft.status)
        in_sum = check_text(draft.input_summary, "input_summary", SUMMARY_MAX)
        out_sum = check_text(draft.output_summary, "output_summary", SUMMARY_MAX)
        error = check_text(draft.error, "error", ERROR_MAX)
        approval_ref = validate_ref(draft.approval_ref, "approval_ref") if draft.approval_ref is not None else None
        if draft.seq is not None and (not isinstance(draft.seq, int) or draft.seq < 1):
            raise ValidationError("seq 는 1 이상의 정수")
        actor = validate_actor(actor)
        now = self._now()
        started = now if status != StepStatus.PENDING else None
        finished = now if status in (StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED) else None
        with self._conn() as con, self._tx(con):
            job = self._live_job(con, job_id)
            if JobStatus(job["status"]) in JOB_TERMINAL:
                raise InvalidTransitionError("종료된 job 에는 step 을 추가할 수 없다")
            if draft.seq is None:
                seq = int(
                    con.execute(
                        "SELECT COALESCE(MAX(seq), 0) + 1 FROM wrs_steps WHERE job_id = ?", (job_id,)
                    ).fetchone()[0]
                )
            else:
                seq = draft.seq
                if con.execute("SELECT 1 FROM wrs_steps WHERE job_id = ? AND seq = ?", (job_id, seq)).fetchone():
                    raise ValidationError(f"이미 있는 step seq: {seq}")
            con.execute(
                "INSERT INTO wrs_steps (job_id, seq, kind, status, risk, started_at, finished_at, input_summary,"
                " output_summary, error, approval_ref, attempt, irreversible) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (job_id, seq, kind, status.value, risk, started, finished, in_sum, out_sum, error, approval_ref,
                 int(draft.irreversible)),
            )  # fmt: skip
            self._event(con, job_id, "step_added", actor, f"{kind}:{status.value}", seq)
        return seq

    def update_step(self, job_id: str, seq: int, update: StepUpdate, *, actor: str = "system") -> None:
        """step 상태를 전이표대로 바꾼다(요약·오류·승인 참조는 상태 변경과 함께만 갱신)."""
        new = validate_step_status(update.status)
        out_sum = check_text(update.output_summary, "output_summary", SUMMARY_MAX)
        err = check_text(update.error, "error", ERROR_MAX)
        ref = validate_ref(update.approval_ref, "approval_ref") if update.approval_ref is not None else None
        actor = validate_actor(actor)
        with self._conn() as con, self._tx(con):
            self._live_job(con, job_id)
            row = con.execute("SELECT * FROM wrs_steps WHERE job_id = ? AND seq = ?", (job_id, seq)).fetchone()
            if row is None:
                raise NotFoundError(f"step 없음: {job_id}#{seq}")
            old = StepStatus(row["status"])
            if not can_transition_step(old, new):
                raise InvalidTransitionError(f"step {old.value} -> {new.value} 전이는 허용되지 않는다")
            now = self._now()
            started = row["started_at"] or (now if new == StepStatus.RUNNING else None)
            finished = now if new in (StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED) else None
            attempt = row["attempt"] + (1 if old == StepStatus.FAILED and new == StepStatus.RUNNING else 0)
            changed = con.execute(
                "UPDATE wrs_steps SET status = ?, started_at = ?, finished_at = ?, attempt = ?,"
                " output_summary = COALESCE(?, output_summary), error = COALESCE(?, error),"
                " approval_ref = COALESCE(?, approval_ref) WHERE job_id = ? AND seq = ? AND status = ?",
                (new.value, started, finished, attempt, out_sum, err, ref, job_id, seq, old.value),
            ).rowcount
            if changed != 1:
                raise InvalidTransitionError("step 이 동시에 변경되었다")
            self._event(con, job_id, "step_status", actor, f"{old.value} -> {new.value}", seq)

    def list_steps(self, job_id: str, scope: Scope) -> list[Step]:
        with self._conn() as con:
            self._visible_job(con, job_id, scope)
            rows = con.execute("SELECT * FROM wrs_steps WHERE job_id = ? ORDER BY seq", (job_id,)).fetchall()
        return [_step_from_row(r) for r in rows]

    # ── artifact ─────────────────────────────────────────────────────────
    def _resolve_artifact_path(self, raw: str) -> tuple[Path, str]:
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            raise ValidationError("artifact 경로가 비었다")
        candidate = Path(raw)
        if ".." in candidate.parts:
            raise ValidationError("artifact 경로에 '..' 금지")
        if not candidate.is_absolute():
            candidate = self._base_dir / candidate
        resolved = candidate.resolve(strict=False)  # 심볼릭 링크는 실제 위치로 따라간 뒤 루트 안인지 본다
        if not any(resolved.is_relative_to(root) for root in self._roots):
            raise ValidationError("artifact 경로가 허용 루트 밖이다")
        if not resolved.is_file():
            raise ValidationError("artifact 파일이 없거나 일반 파일이 아니다")
        rel = validate_artifact_rel_path(resolved.relative_to(self._base_dir).as_posix())
        return resolved, rel

    def attach_artifact(self, job_id: str, spec: ArtifactSpec, *, actor: str = "system") -> str:
        """파일을 읽어 sha256·크기를 계산하고 경로(저장소 상대)와 함께 기록한다. 파일은 복사하지 않는다."""
        kind = validate_artifact_kind(spec.kind)
        sensitivity = validate_sensitivity(spec.sensitivity)
        media = validate_media_type(spec.media_type)
        retention = validate_retention(spec.retention_class)
        actor = validate_actor(actor)
        resolved, rel = self._resolve_artifact_path(spec.src_path)
        if resolved.stat().st_size > ARTIFACT_MAX_BYTES:
            raise ValidationError("artifact 파일이 너무 크다")
        digest, size = _sha256_of(resolved)
        artifact_id = uuid.uuid4().hex
        with self._conn() as con, self._tx(con):
            self._live_job(con, job_id)
            if spec.step_seq is not None and (
                con.execute("SELECT 1 FROM wrs_steps WHERE job_id = ? AND seq = ?", (job_id, spec.step_seq)).fetchone()
                is None
            ):
                raise NotFoundError(f"step 없음: {job_id}#{spec.step_seq}")
            con.execute(
                "INSERT INTO wrs_artifacts (artifact_id, job_id, step_seq, kind, path, sha256, size_bytes, media_type,"
                " sensitivity, retention_class, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    job_id,
                    spec.step_seq,
                    kind,
                    rel,
                    digest,
                    size,
                    media,
                    sensitivity,
                    retention,
                    self._now(),
                ),
            )
            self._event(con, job_id, "artifact_attached", actor, f"{kind} {rel}", spec.step_seq)
        return artifact_id

    def get_artifact(self, artifact_id: str, scope: Scope) -> Artifact | None:
        sql, args = self._scope_sql(scope, "j")
        with self._conn() as con:
            row = con.execute(
                "SELECT a.* FROM wrs_artifacts a JOIN wrs_jobs j ON j.job_id = a.job_id"
                f" WHERE a.artifact_id = ? AND j.deleted_at IS NULL AND {sql}",
                [artifact_id, *args],
            ).fetchone()
        return _artifact_from_row(row) if row else None

    def list_artifacts(self, job_id: str, scope: Scope) -> list[Artifact]:
        with self._conn() as con:
            self._visible_job(con, job_id, scope)
            rows = con.execute(
                "SELECT * FROM wrs_artifacts WHERE job_id = ? ORDER BY created_at, rowid", (job_id,)
            ).fetchall()
        return [_artifact_from_row(r) for r in rows]

    def verify_artifact(self, artifact_id: str, scope: Scope) -> bool:
        """저장된 sha256 과 현재 파일 해시가 같으면 True. 파일 없음/변조/루트 밖이면 False."""
        art = self.get_artifact(artifact_id, scope)
        if art is None:
            raise NotFoundError(f"artifact 없음: {artifact_id}")
        try:
            resolved, rel = self._resolve_artifact_path(art.path)
            digest, size = _sha256_of(resolved)
        except (ValidationError, OSError):
            return False
        return rel == art.path and digest == art.sha256 and size == art.size_bytes

    # ── event / link ─────────────────────────────────────────────────────
    def append_event(
        self, job_id: str, *, event: str, actor: str, detail: str | None = None, step_seq: int | None = None
    ) -> int:
        """이벤트를 추가한다(수정·삭제 API 없음)."""
        name = validate_event_name(event)
        actor = validate_actor(actor)
        text = check_text(detail, "detail", EVENT_DETAIL_MAX)
        with self._conn() as con, self._tx(con):
            self._live_job(con, job_id)
            if step_seq is not None and (
                con.execute("SELECT 1 FROM wrs_steps WHERE job_id = ? AND seq = ?", (job_id, step_seq)).fetchone()
                is None
            ):
                raise NotFoundError(f"step 없음: {job_id}#{step_seq}")
            return self._event(con, job_id, name, actor, text, step_seq)

    def list_events(self, job_id: str, scope: Scope, *, include_deleted: bool = False) -> list[Event]:
        """타임라인. 소프트 삭제된 job 의 이벤트도 `include_deleted=True` 로 읽을 수 있다(보존)."""
        with self._conn() as con:
            self._visible_job(con, job_id, scope, include_deleted=include_deleted)
            rows = con.execute("SELECT * FROM wrs_events WHERE job_id = ? ORDER BY event_id", (job_id,)).fetchall()
        return [
            Event(r["event_id"], r["job_id"], r["step_seq"], r["at"], r["actor"], r["event"], r["detail"]) for r in rows
        ]

    def add_link(self, job_id: str, *, link_type: str, ref_store: str, ref_id: str, actor: str = "system") -> bool:
        """기존 스토어 기록을 ID 로만 참조한다(복제 없음). 새로 추가했으면 True(멱등)."""
        ltype = validate_link_type(link_type)
        store = validate_ref(ref_store, "ref_store")
        rid = validate_ref(ref_id, "ref_id")
        actor = validate_actor(actor)
        with self._conn() as con, self._tx(con):
            self._live_job(con, job_id)
            inserted = (
                con.execute(
                    "INSERT OR IGNORE INTO wrs_links (job_id, link_type, ref_store, ref_id, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (job_id, ltype, store, rid, self._now()),
                ).rowcount
                == 1
            )
            if inserted:
                self._event(con, job_id, "link_added", actor, f"{ltype} {store}:{rid}")
        return inserted

    def list_links(self, job_id: str, scope: Scope) -> list[Link]:
        with self._conn() as con:
            self._visible_job(con, job_id, scope)
            rows = con.execute(
                "SELECT * FROM wrs_links WHERE job_id = ? ORDER BY created_at, rowid", (job_id,)
            ).fetchall()
        return [Link(r["job_id"], r["link_type"], r["ref_store"], r["ref_id"]) for r in rows]


_default_store: WorkRecordStore | None = None


def default_store() -> WorkRecordStore:
    """기본 위치(ai_orchestrator/storage/work_records.db, 산출물 루트 data/work_records)의 싱글턴."""
    global _default_store
    if _default_store is None:
        _default_store = WorkRecordStore()
    return _default_store
