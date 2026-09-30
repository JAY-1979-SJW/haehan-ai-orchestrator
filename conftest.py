"""Pytest runtime defaults for local and deployment gates."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.runtime_temp import usable_temp_base


def _pytest_base(kind: str = "pytest_runtime") -> Path:
    return usable_temp_base(kind, "HAEHAN_PYTEST_TEMP")


def pytest_configure(config):
    """Force Python tempfile users under a verified runtime temp base."""
    base = _pytest_base()
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = str(base)
    tempfile.tempdir = str(base)


@pytest.fixture
def tmp_path(request) -> Path:
    """Replacement tmp_path that avoids pytest basetemp cleanup on Windows."""
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in request.node.name)[:80]
    path = _pytest_base("pytest_tmp_path") / f"{safe_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch, tmp_path):
    """테스트가 실제 사용자 상태 파일을 지우거나 덮어쓰지 못하게 임시 경로로 돌린다.

    local_agent_registry_common.clear() 는 data/local_agent_registry_state.json(실제로 등록된
    로컬 에이전트)을 unlink 하는데, test_local_agent*.py 등 일부 테스트가 경로를 돌리지 않고
    clear() 를 불러 개발 PC 의 에이전트 등록이 테스트를 돌릴 때마다 사라졌다(2026-09-30 실측:
    서버 재기동 후 에이전트가 4401 BAD_CREDENTIALS 로 거부). 개별 테스트가 같은 값을 다시
    monkeypatch 하면 그쪽이 우선한다.
    """
    targets = (
        ("ai_orchestrator.local_agent_registry_common", "_REGISTRY_STATE_PATH", "local_agent_registry_state.json"),
        ("ai_orchestrator.chat_sessions", "_STORE_PATH", "chat_sessions.json"),
    )
    for module_name, attr, filename in targets:
        try:
            module = __import__(module_name, fromlist=[attr])
        except Exception:  # noqa: BLE001, S112 - 해당 모듈을 import 못 하는 환경(일부 CI/스크립트 테스트)은 격리 대상 아님
            continue
        monkeypatch.setattr(module, attr, tmp_path / filename)
