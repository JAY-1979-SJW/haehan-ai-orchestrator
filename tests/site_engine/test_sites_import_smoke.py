"""사이트 자동화 프레임워크 — import smoke 테스트.

외부 접속 없이 모듈 import 만 검증한다.
"""
import importlib

import pytest


MODULES = [
    "ai_orchestrator.sites.site_adapter",
    "ai_orchestrator.sites.job_state",
    "ai_orchestrator.sites.runner",
    "ai_orchestrator.sites.session_manager",
    "ai_orchestrator.sites.adapters.example_portal_adapter",
    "ai_orchestrator.sites.adapters.naver_cafe_adapter",
    "ai_orchestrator.sites.adapters.naver_cafe_collection",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_import(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None
