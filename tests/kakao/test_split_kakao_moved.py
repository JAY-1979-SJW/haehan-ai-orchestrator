"""도구 분리(kakao) 이동 시험 — API 평면 파일을 connectors/kakao/ 로 옮겨도 옛 경로·라우트·루트 값이 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from ai_orchestrator.paths import repo_root

BEFORE = json.loads((Path(__file__).parent.parent / "data" / "split_w3c_before.json").read_text(encoding="utf-8"))
# kakao_setup_router·kakao_skill_router 옛 경로 shim 은 정리됨(SHIM_CLEANUP_2) — 새 경로만 확인한다


@pytest.mark.parametrize(
    ("module", "attr", "key"),
    [
        ("kakao.setup_router", "kakao_setup_router", "kk_setup"),
        ("kakao.skill_router", "kakao_skill_router", "kk_skill"),
    ],
)
def test_routes_unchanged(module, attr, key):
    router = getattr(importlib.import_module(f"ai_orchestrator.connectors.{module}"), attr)
    assert sorted([sorted(r.methods or []), r.path] for r in router.routes) == BEFORE[key]


def test_root_constants_still_the_repo_root_after_the_move():
    assert importlib.import_module("ai_orchestrator.connectors.kakao.setup_router").ROOT == repo_root()
    assert importlib.import_module("ai_orchestrator.connectors.kakao.skill_router")._ROOT == repo_root()
