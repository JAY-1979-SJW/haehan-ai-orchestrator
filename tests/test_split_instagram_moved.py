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
    "instagram_dm_token_store": "instagram.dm_token_store",
    "instagram_graph_client": "instagram.graph_client",
    "instagram_webhook_parser": "instagram.webhook_parser",
}
BEFORE2 = json.loads((Path(__file__).parent / "data" / "split_w3_before2.json").read_text(encoding="utf-8"))


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
        assert text.splitlines()[0].startswith("# haehan-shim: ")  # make_shim 이 만든 shim(식별 마커)


@pytest.mark.parametrize(
    ("new", "key"),
    [
        ("instagram.dm_token_store", "ts_names"),
        ("instagram.graph_client", "gr_names"),
        ("instagram.webhook_parser", "wp_names"),
    ],
)
def test_public_names_unchanged(new, key):
    mod = importlib.import_module(f"ai_orchestrator.connectors.{new}")
    assert sorted(n for n in dir(mod) if not n.startswith("__")) == BEFORE2[key]


def test_token_store_file_path_value_is_unchanged(monkeypatch):
    """토큰 저장 파일 경로(비윈도우 폴백)가 이동 전과 같은 ai_orchestrator/storage 아래인지 — 데이터가 엉뚱한 위치에 새로 생기지 않게 고정한다.

    실제 모듈을 reload 하면 속성이 남아 다른 시험에 영향을 주므로, 같은 파일을 별도 모듈 객체로 읽는다."""
    import importlib.util
    import sys

    real = importlib.import_module("ai_orchestrator.connectors.instagram.dm_token_store")
    spec = importlib.util.spec_from_file_location("_dm_token_store_probe", real.__file__)
    probe = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(sys, "platform", "linux")
    spec.loader.exec_module(probe)
    assert probe._STORE_PATH == repo_root() / "ai_orchestrator" / "storage" / "instagram_dm_tokens.enc.json"
