"""도구 분리(instagram) 이동 시험 — API 평면 파일을 connectors/instagram/ 로 옮겨도 동작·값·라우트가 같은지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts.app_paths import repo_root

MOVED = {
    "instagram_dm_db": "instagram.dm_db",
    "instagram_dm_router": "instagram.dm_router",
    "instagram_dm_rule_engine": "instagram.dm_rule_engine",
    "instagram_dm_service": "instagram.dm_service",
}


@pytest.mark.parametrize(("old", "new"), MOVED.items())
def test_old_path_is_alias_of_new_module(old, new):
    old_mod = importlib.import_module(f"ai_orchestrator.connectors.{old}")
    new_mod = importlib.import_module(f"ai_orchestrator.connectors.{new}")
    assert old_mod is new_mod


def test_db_path_value_is_unchanged():
    """__file__ 깊이 보정: 이동 전과 같은 위치(ai_orchestrator/storage/instagram_dm.db)를 가리켜야 한다(데이터가 엉뚱한 곳에 새로 생기는 사고 방지)."""
    db = importlib.import_module("ai_orchestrator.connectors.instagram.dm_db")
    assert db._DB_PATH == repo_root() / "ai_orchestrator" / "storage" / "instagram_dm.db"


def test_routes_are_unchanged():
    before = json.loads((Path(__file__).parent / "data" / "split_w3_routes_before.json").read_text(encoding="utf-8"))[
        "ig_routes"
    ]
    router = importlib.import_module("ai_orchestrator.connectors.instagram_dm_router").instagram_dm_router
    after = sorted([sorted(r.methods or []), r.path] for r in router.routes)
    assert after == before
    assert len(after) == 17


def test_old_path_shims_are_tiny_aliases():
    root = repo_root() / "ai_orchestrator" / "connectors"
    for old in MOVED:
        text = (root / f"{old}.py").read_text(encoding="utf-8")
        assert "sys.modules[__name__]" in text and len(text.splitlines()) <= 8
