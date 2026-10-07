"""도구 분리 1단계(gabia) — gabia_router 의 저장소 루트 직접 계산을 ai_orchestrator.paths.repo_root() 로 교체한 값이 그대로인지 고정한다."""

from __future__ import annotations

from ai_orchestrator.connectors.gabia import router as gabia_router
from ai_orchestrator.paths import repo_root


def test_root_constant_is_the_repo_root():
    assert gabia_router.ROOT == repo_root()
