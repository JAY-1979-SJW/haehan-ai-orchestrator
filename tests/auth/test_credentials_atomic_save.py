"""credentials.json 저장 안전성 — 비원자적 쓰기(licenses.json 손상 사고와 같은 패턴)와
불필요한 재저장(변화 없어도 매번 _load() 가 다시 쓰는 결함) 재발 방지.
"""

from __future__ import annotations

import json

import pytest

from scripts.auth import credentials as c


@pytest.fixture
def env(monkeypatch, tmp_path):
    cred_file = tmp_path / "credentials.json"
    monkeypatch.setattr(c, "CRED_FILE", cred_file)
    monkeypatch.setattr(c, "_LEGACY_ENV_FILES", {})
    return cred_file


def test_save_raw_failure_leaves_original_file_untouched(env, monkeypatch):
    env.write_text('{"site": {"id": "x"}}', encoding="utf-8")
    original = env.read_text(encoding="utf-8")

    def boom(fd):
        raise OSError("disk full")

    monkeypatch.setattr(c.os, "fsync", boom)
    with pytest.raises(OSError):
        c._save_raw({"site": {"id": "changed"}})

    assert env.read_text(encoding="utf-8") == original  # 원본 무손상
    assert list(env.parent.glob("*.tmp-*")) == []  # tmp 흔적도 안 남음


def test_save_raw_success_leaves_no_tmp_leftover(env):
    c._save_raw({"site": {"id": "y"}})
    assert json.loads(env.read_text(encoding="utf-8")) == {"site": {"id": "y"}}
    assert list(env.parent.glob("*.tmp-*")) == []  # 성공해도 tmp 가 안 남아야 한다


def test_load_does_not_rewrite_when_nothing_changed(env):
    """평문 pw·레거시 파일이 없으면 _load() 가 조회만 하고 파일을 다시 쓰면 안 된다
    (2026-10-10, research_blog_topics 실행 중 읽기만 하는 호출에서도 재저장이 일어난
    문제의 재발 방지 — 변화가 없으면 mtime 도 그대로여야 한다)."""
    env.write_text(json.dumps({"site": {"id": "a", "pw_enc": "enc-token"}}), encoding="utf-8")
    before_mtime = env.stat().st_mtime_ns

    data = c._load()

    assert data == {"site": {"id": "a", "pw_enc": "enc-token"}}
    assert env.stat().st_mtime_ns == before_mtime  # 다시 쓰지 않았다


def test_load_still_migrates_plaintext_pw_and_saves_once(env):
    """평문 pw 는 여전히 자동 암호화 마이그레이션돼야 한다(기존 동작 유지) — 이번엔
    딱 한 번만 저장되는지 확인."""
    env.write_text(json.dumps({"site": {"id": "a", "pw": "plain"}}), encoding="utf-8")

    data = c._load()

    assert "pw" not in data["site"]
    assert "pw_enc" in data["site"]
    on_disk = json.loads(env.read_text(encoding="utf-8"))
    assert "pw_enc" in on_disk["site"]
