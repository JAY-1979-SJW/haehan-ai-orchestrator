"""conftest 의 상태 파일 격리(_isolate_runtime_state)가 실제로 걸리는지 고정한다(T4 R1).

격리 대상은 모듈 경로 *문자열*이고 import 실패는 조용히 넘어간다 — 모듈을 옮기고 문자열을 안 고치면 격리 없이 시험이
실제 에이전트 등록 상태 파일을 지운다(2026-09-30 사고). 이 시험은 대상 모듈이 import 되고 경로가 임시 폴더로 바뀌는지 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_orchestrator.agent_hub.registry import common as registry_common
from ai_orchestrator.tasks import chat_sessions


def test_registry_state_path_is_isolated_into_tmp(tmp_path: Path):
    assert registry_common._REGISTRY_STATE_PATH == tmp_path / "local_agent_registry_state.json"


def test_chat_sessions_store_is_isolated_into_tmp(tmp_path: Path):
    assert chat_sessions._STORE_PATH == tmp_path / "chat_sessions.json"


def test_conftest_isolation_targets_all_import():
    """대상 문자열이 낡으면 conftest 는 조용히 건너뛴다 — 여기서는 건너뛰지 못하게 직접 import 한다."""
    source = (Path(__file__).resolve().parents[2] / "conftest.py").read_text(encoding="utf-8")
    start = source.index("targets = (")
    block = source[start : source.index(")\n    # ", start)]
    names = [line.split('"')[1] for line in block.splitlines() if line.strip().startswith('("')]
    assert names, "conftest 격리 대상을 찾지 못함"
    for name in names:
        try:
            __import__(name, fromlist=["x"])
        except ImportError as exc:  # pragma: no cover - 실패 시 어떤 대상이 낡았는지 보여 준다
            pytest.fail(f"conftest 격리 대상 모듈을 import 할 수 없다(옮기고 문자열을 안 고쳤나?): {name}: {exc}")
