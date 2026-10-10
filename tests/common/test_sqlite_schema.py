"""ai_orchestrator.persistence.sqlite_schema — user_version 기반 순차 마이그레이션 (결함 #14)."""

from __future__ import annotations

import sqlite3

import pytest

from ai_orchestrator.persistence.sqlite_schema import (
    SchemaTooNewError,
    add_column_if_missing,
    apply_schema,
    column_names,
    current_version,
)


def _v1(con: sqlite3.Connection) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT)")


def _v2(con: sqlite3.Connection) -> None:
    add_column_if_missing(con, "t", "extra", "TEXT NOT NULL DEFAULT 'x'")


@pytest.fixture(params=["legacy", "autocommit"])
def con(request, tmp_path):
    # 저장소의 두 가지 연결 방식(기본 / isolation_level=None)에서 모두 동작해야 한다
    kwargs = {"isolation_level": None} if request.param == "autocommit" else {}
    c = sqlite3.connect(str(tmp_path / "t.db"), **kwargs)
    yield c
    c.close()


def test_fresh_db_runs_all_steps_and_sets_version(con):
    assert current_version(con) == 0
    assert apply_schema(con, [_v1, _v2]) == 2
    assert current_version(con) == 2
    assert column_names(con, "t") == {"id", "name", "extra"}


def test_latest_version_does_not_rerun_steps(con):
    calls = []

    def v1(c):
        calls.append(1)
        _v1(c)

    apply_schema(con, [v1])
    apply_schema(con, [v1])
    assert calls == [1]


def test_legacy_db_without_version_is_migrated_and_keeps_data(con):
    # 버전 장치가 없던 옛 DB: 테이블은 있고 새 컬럼은 없고 user_version=0
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO t (name) VALUES ('a'), ('b')")
    con.commit()
    assert current_version(con) == 0
    apply_schema(con, [_v1, _v2])
    assert current_version(con) == 2
    rows = con.execute("SELECT name, extra FROM t ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("a", "x"), ("b", "x")]


def test_legacy_db_that_already_has_new_column_is_idempotent(con):
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, extra TEXT NOT NULL DEFAULT 'x')")
    con.commit()
    apply_schema(con, [_v1, _v2])
    assert current_version(con) == 2
    assert column_names(con, "t") == {"id", "name", "extra"}


def test_new_step_is_applied_after_old_ones(con):
    apply_schema(con, [_v1])

    def v2(c):
        add_column_if_missing(c, "t", "extra", "TEXT")

    apply_schema(con, [_v1, v2])
    assert current_version(con) == 2
    assert "extra" in column_names(con, "t")


def test_failing_step_rolls_back_everything_and_keeps_version(con):
    def bad(c):
        c.execute("CREATE TABLE only_in_bad (x INTEGER)")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        apply_schema(con, [_v1, bad])
    assert current_version(con) == 0
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "t" not in tables and "only_in_bad" not in tables
    # 다음 시도는 정상 단계로 이어서 성공한다
    assert apply_schema(con, [_v1, _v2]) == 2


def test_db_newer_than_code_is_rejected(con):
    apply_schema(con, [_v1, _v2])
    with pytest.raises(SchemaTooNewError):
        apply_schema(con, [_v1])
    assert current_version(con) == 2  # 건드리지 않음


def test_add_column_if_missing_returns_whether_it_added(con):
    _v1(con)
    assert add_column_if_missing(con, "t", "c1", "TEXT") is True
    assert add_column_if_missing(con, "t", "c1", "TEXT") is False


@pytest.mark.parametrize("bad", ["t; DROP TABLE t", "1abc", "a b", ""])
def test_identifiers_are_validated(con, bad):
    _v1(con)
    with pytest.raises(ValueError):
        column_names(con, bad)
    with pytest.raises(ValueError):
        add_column_if_missing(con, "t", bad, "TEXT")


def test_second_connection_does_not_rerun_applied_step(tmp_path):
    path = str(tmp_path / "c.db")
    calls = []

    def v1(c):
        calls.append(1)
        _v1(c)

    a = sqlite3.connect(path, isolation_level=None)
    b = sqlite3.connect(path, isolation_level=None)
    try:
        apply_schema(a, [v1])
        apply_schema(b, [v1])  # b 는 이미 올라간 버전을 보고 건너뛴다
    finally:
        a.close()
        b.close()
    assert calls == [1]


def test_stores_apply_busy_timeout_and_gongmu_seeds_once(tmp_path, monkeypatch):
    """스토어 연결에 busy_timeout 이 적용되고, gongmu 시드는 DB 파일당 한 번만 돈다."""
    from ai_orchestrator.agent_dispatch import agent_dispatch_store
    from ai_orchestrator.connectors.hanafax import authorization_store as fax_authorization_store
    from ai_orchestrator.connectors.instagram import instagram_dm_db
    from ai_orchestrator.connectors.naver_mail import bulk_store as mail_bulk_store
    from ai_orchestrator.connectors.naver_mail import draft_store as naver_mail_draft_store
    from ai_orchestrator.gongmu import gongmu_store
    from ai_orchestrator.scheduler import scheduled_job_store

    for mod in (
        scheduled_job_store,
        mail_bulk_store,
        gongmu_store,
        fax_authorization_store,
        agent_dispatch_store,
        naver_mail_draft_store,
        instagram_dm_db,
    ):
        monkeypatch.setattr(mod, "_DB_PATH", tmp_path / f"{mod.__name__.rsplit('.', 1)[-1]}.db")
        with mod._conn() as con:
            assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 30000, mod.__name__

    calls = []
    real = gongmu_store._seed_catalog
    monkeypatch.setattr(gongmu_store, "_seed_catalog", lambda con: (calls.append(1), real(con)))
    monkeypatch.setattr(gongmu_store, "_SEEDED", set())
    for _ in range(3):
        with gongmu_store._conn():
            pass
    assert len(calls) == 1
