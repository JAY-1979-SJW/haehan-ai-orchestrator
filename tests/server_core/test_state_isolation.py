"""테스트가 실제 사용자 상태 파일 경로를 쓰지 않는지(conftest 자동 격리 픽스처) 검사."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_registry_state_path_is_isolated():
    from ai_orchestrator.agent_hub.registry import common as reg

    assert ROOT / "data" not in Path(reg._REGISTRY_STATE_PATH).parents


def test_chat_store_path_is_isolated():
    from ai_orchestrator.tasks import chat_sessions as store

    assert ROOT / "data" not in Path(store._STORE_PATH).parents


def test_clear_does_not_delete_real_registry_file():
    from ai_orchestrator.agent_hub.registry import common as reg

    real = ROOT / "data" / "local_agent_registry_state.json"
    existed = real.exists()
    before = real.read_bytes() if existed else b""
    reg.clear()
    assert real.exists() == existed
    if existed:
        assert real.read_bytes() == before
