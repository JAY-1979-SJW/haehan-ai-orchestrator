"""naver_openapi_setup_router.py 의 ROOT 가 저장소 루트를 가리키는지 (결함: parents[2] 깊이 오류, 2026-10-10)."""

from __future__ import annotations

from ai_orchestrator.connectors.naver_search import naver_openapi_setup_router as router_module
from ai_orchestrator.paths import repo_root


def test_root_points_to_repo_root():
    assert router_module.ROOT == repo_root()
