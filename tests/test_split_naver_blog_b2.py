"""도구 분리 B2(naver_blog) 이동 시험 — router_blog·navigator_blog 를 도구 집으로 옮겨도 옛 경로·공개 이름·importer 가 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts.app_paths import repo_root

ROOT = repo_root()
BEFORE = json.loads((Path(__file__).parent / "data" / "split_w3_b2_names_before.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("scripts.naver.router_blog", "scripts.naver.blog.router_blog", "router_blog"),
        ("scripts.navigator_blog", "scripts.naver.blog.navigator_blog", "navigator_blog"),
    ],
)
def test_old_path_is_alias_and_public_names_unchanged(old, new, key):
    assert importlib.import_module(old) is importlib.import_module(new)
    names = sorted(n for n in dir(importlib.import_module(new)) if not n.startswith("__"))
    assert names == BEFORE[key]


def test_importers_still_work_through_the_shims():
    from scripts import navigator
    from scripts.naver import dispatch, router

    nb = importlib.import_module("scripts.naver.blog.navigator_blog")
    rb = importlib.import_module("scripts.naver.blog.router_blog")
    assert navigator.write_blog_post is nb.write_blog_post
    assert dispatch._cmd_blog_assets is rb._cmd_blog_assets
    assert router._cmd_blog_assets is rb._cmd_blog_assets


def test_old_path_shims_are_tiny():
    for rel in ("scripts/naver/router_blog.py", "scripts/navigator_blog.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert text.splitlines()[0].startswith("# haehan-shim: ")  # make_shim 이 만든 shim(식별 마커)
