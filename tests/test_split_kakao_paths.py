"""도구 분리 1단계(kakao) — 저장소 루트 직접 계산을 ai_orchestrator.paths.repo_root() 로 교체한 값이 그대로인지 고정한다."""

from __future__ import annotations

import importlib

import pytest

from ai_orchestrator.paths import repo_root


@pytest.mark.parametrize(("module", "attr"), [("kakao.setup_router", "ROOT"), ("kakao.skill_router", "_ROOT")])
def test_root_constant_is_the_repo_root(module, attr):
    assert getattr(importlib.import_module(f"ai_orchestrator.connectors.{module}"), attr) == repo_root()


def test_setup_state_path_is_unchanged():
    import ai_orchestrator.connectors.kakao.setup_router as mod
    assert mod.STATE_PATH == repo_root() / "data" / "kakao_setup_state.json"
