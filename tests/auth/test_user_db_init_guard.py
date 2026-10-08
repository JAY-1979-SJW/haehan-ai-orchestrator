"""user_db.init_db 경로별 1회 초기화 가드 시험 (tmp 경로 격리)."""

from __future__ import annotations

import sqlite3

from ai_orchestrator.auth import user_db


def _count_creates(monkeypatch) -> list[str]:
    calls: list[str] = []
    orig = user_db._create_schema

    def spy() -> None:
        calls.append(str(user_db._get_db_path()))
        orig()

    monkeypatch.setattr(user_db, "_create_schema", spy)
    return calls


def test_init_db_runs_create_once_per_path(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_INITIALIZED", set())
    monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / "a.db")
    calls = _count_creates(monkeypatch)
    for _ in range(5):
        user_db.init_db()
    user_db.get_user_by_id("x")
    assert len(calls) == 1


def test_init_db_reinitializes_per_path_and_after_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(user_db, "_INITIALIZED", set())
    calls = _count_creates(monkeypatch)
    for name in ("a.db", "b.db"):
        monkeypatch.setattr(user_db, "_DB_PATH", tmp_path / name)
        user_db.init_db()
        user_db.init_db()
    assert len(calls) == 2
    # 파일 삭제 후에는 다시 생성
    (tmp_path / "b.db").unlink()
    user_db.init_db()
    assert len(calls) == 3
    con = sqlite3.connect(str(tmp_path / "b.db"))
    try:
        assert con.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchone()
    finally:
        con.close()
