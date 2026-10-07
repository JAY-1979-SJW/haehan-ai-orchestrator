"""scripts.common.app_paths_migrate — 윈도우 표준 저장소 복사 이전 엔진 (결함 #17). 실제 데이터는 건드리지 않고 임시 폴더만 쓴다."""

from __future__ import annotations

import json
import sqlite3

from scripts.common import app_paths_migrate as m


def _make_source(tmp_path):
    root = tmp_path / "src"
    (root / "cdp_profile" / "Default").mkdir(parents=True)
    (root / "cdp_profile" / "Default" / "Cookies").write_text("cookie")
    (root / "cdp_profile" / "Default" / "Cache").mkdir()
    (root / "cdp_profile" / "Default" / "Cache" / "x").write_text("cache")
    (root / "sessions").mkdir()
    (root / "sessions" / "naver.json").write_text('{"k": 1}')
    (root / "cache_tmp").mkdir()
    (root / "cdp_chrome_tmp").mkdir()
    (root / "cdp_chrome_tmp" / "t").write_text("tmp")
    (root / "report.json").write_text('{"a": 1}')
    (root / "images").mkdir()
    (root / "images" / "a.png").write_bytes(b"png")
    con = sqlite3.connect(str(root / "app.db"))
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.execute("INSERT INTO t (v) VALUES ('hello')")
    con.commit()
    con.close()
    return root


def _sources(root):
    return [
        m.MigrationSource(
            "repo_data", root, "data", remap={"cdp_profile": "browser_profile/ai_chrome", "sessions": "sessions"}
        )
    ]


def test_classify_rules():
    assert m.classify("app.db") == m.REQUIRED
    assert m.classify("sessions/naver.json") == m.REQUIRED
    assert m.classify("secrets/token") == m.REQUIRED
    assert m.classify("report.json") == m.REQUIRED
    assert m.classify("cdp_profile/Default/Cookies") == m.OPTIONAL
    assert m.classify("images/a.png") == m.OPTIONAL
    assert m.classify("cdp_chrome_tmp/t") == m.EXCLUDED
    assert m.classify("cdp_profile/Default/Cache/x") == m.EXCLUDED
    assert m.classify("a/__pycache__/m.pyc") == m.EXCLUDED


def test_plan_is_dry_run_and_writes_nothing(tmp_path):
    root = _make_source(tmp_path)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    result = m.plan(_sources(root))
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
    cats = result.totals()
    assert cats[m.REQUIRED]["files"] >= 3
    assert m.EXCLUDED in cats


def test_plan_reports_missing_source(tmp_path):
    result = m.plan([m.MigrationSource("gone", tmp_path / "nope", "data")])
    assert result.missing_sources == ["gone"]


def test_plan_maps_destinations_with_remap(tmp_path):
    root = _make_source(tmp_path)
    dests = {i.rel.split(":", 1)[1]: i.dest_rel for i in m.plan(_sources(root)).items}
    assert dests["cdp_profile/Default/Cookies"] == "browser_profile/ai_chrome/Default/Cookies"
    assert dests["sessions/naver.json"] == "sessions/naver.json"
    assert dests["report.json"] == "data/report.json"


def test_execute_copies_required_only_by_default_and_keeps_source(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    summary = m.execute(_sources(root), dest)
    assert summary["failed"] == 0
    assert (dest / "data" / "report.json").read_text() == '{"a": 1}'
    assert (dest / "sessions" / "naver.json").exists()
    assert not (dest / "browser_profile").exists()  # 선택 항목은 기본 제외
    assert not (dest / "data" / "cdp_chrome_tmp").exists()  # 제외 항목
    assert (root / "report.json").exists() and (root / "app.db").exists()  # 원본 보존


def test_execute_sqlite_uses_consistent_backup(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    m.execute(_sources(root), dest)
    con = sqlite3.connect(str(dest / "data" / "app.db"))
    try:
        assert con.execute("SELECT v FROM t").fetchone()[0] == "hello"
    finally:
        con.close()


def test_execute_is_idempotent(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    first = m.execute(_sources(root), dest)
    second = m.execute(_sources(root), dest)
    assert first["copied"] >= 1
    assert second["copied"] >= 0 and second["failed"] == 0
    assert second["skipped_same"] >= 1


def test_execute_with_optional_copies_browser_profile(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    m.execute(_sources(root), dest, categories=(m.REQUIRED, m.OPTIONAL))
    assert (dest / "browser_profile" / "ai_chrome" / "Default" / "Cookies").read_text() == "cookie"
    assert not (dest / "browser_profile" / "ai_chrome" / "Default" / "Cache").exists()  # 캐시는 계속 제외


def test_browser_running_skips_profile_and_sessions(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    summary = m.execute(_sources(root), dest, categories=(m.REQUIRED, m.OPTIONAL), browser_running=True)
    assert summary["skipped_browser_running"] >= 1
    assert not (dest / "browser_profile").exists()
    assert not (dest / "sessions" / "naver.json").exists()
    assert (dest / "data" / "report.json").exists()  # 브라우저와 무관한 파일은 복사


def test_migration_record_has_no_absolute_paths(tmp_path):
    root = _make_source(tmp_path)
    dest = tmp_path / "dest"
    m.execute(_sources(root), dest)
    text = (dest / "migration" / "migration.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in text  # 사용자명이 든 절대경로를 기록하지 않는다
    assert json.loads(text)["summary"]["failed"] == 0
