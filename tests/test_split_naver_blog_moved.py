"""도구 분리(naver_blog) 이동 시험 — API 파일을 connectors/naver_blog/ 로 옮겨도 동작·값·라우트가 같은지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts.app_paths import repo_root

MOVED = {
    "ai_orchestrator.connectors.naver_blog_router": "ai_orchestrator.connectors.naver_blog.router",
    "ai_orchestrator.routers.blog_automation_router": "ai_orchestrator.connectors.naver_blog.automation_router",
}
BEFORE = json.loads((Path(__file__).parent / "data" / "split_w3_routes_before.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("old", "new"), MOVED.items())
def test_old_path_is_alias_of_new_module(old, new):
    assert importlib.import_module(old) is importlib.import_module(new)


def test_drafts_dir_value_is_unchanged():
    mod = importlib.import_module("ai_orchestrator.connectors.naver_blog.router")
    assert mod.DRAFTS_DIR == repo_root() / "data" / "blog_drafts"


@pytest.mark.parametrize(
    ("module", "attr", "key", "count"),
    [
        ("ai_orchestrator.connectors.naver_blog.router", "naver_blog_router", "blog_routes", 7),
        ("ai_orchestrator.connectors.naver_blog.automation_router", "blog_automation_router", "auto_routes", 11),
    ],
)
def test_routes_are_unchanged(module, attr, key, count):
    router = getattr(importlib.import_module(module), attr)
    after = sorted([sorted(r.methods or []), r.path] for r in router.routes)
    assert after == BEFORE[key]
    assert len(after) == count


def test_publish_gate_survives_the_move():
    """R2: write-to-naver 의 승인 문구 게이트가 이동 뒤에도 그대로다(문구 없이 publish=true 는 403)."""
    from fastapi import HTTPException

    mod = importlib.import_module("ai_orchestrator.connectors.naver_blog.router")
    with pytest.raises(HTTPException) as exc:
        mod.write_to_naver(mod.BlogWriteRequest(title="t", body="b", publish=True), user={})
    assert exc.value.status_code == 403


def test_old_path_shims_are_tiny_aliases():
    for old in MOVED:
        text = (repo_root() / (old.replace(".", "/") + ".py")).read_text(encoding="utf-8")
        assert "sys.modules[__name__]" in text and len(text.splitlines()) <= 8
