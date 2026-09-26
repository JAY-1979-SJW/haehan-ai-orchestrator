"""C2: LocalAgent.to_safe 는 registry 를 역방향 import 하지 않고 bind_registry 로 주입받는다."""

import pytest

from ai_orchestrator import local_agent_models as models


def _agent():
    return models.LocalAgent(
        agent_id="a1", host="h", os_name="o", version="v", registered_at="t", requested_by="u", token_hash="x"
    )


def test_to_safe_uses_bound_registry(monkeypatch):
    class Fake:
        get_agent_status = staticmethod(lambda i: "online")
        get_active_task_count = staticmethod(lambda i: 2)
        get_current_task_id = staticmethod(lambda i: "t1")
        get_task_count = staticmethod(lambda i: 3)
        get_completed_task_count = staticmethod(lambda i: 1)
        get_failed_task_count = staticmethod(lambda i: 0)

    monkeypatch.setattr(models, "_registry", Fake)
    d = _agent().to_safe()
    assert d["agent_status"] == "online" and d["active_task_count"] == 2 and "token_hash" not in d


def test_to_safe_unbound_raises(monkeypatch):
    monkeypatch.setattr(models, "_registry", None)
    with pytest.raises(RuntimeError):
        _agent().to_safe()


def test_registry_agent_import_binds():
    import ai_orchestrator.local_agent_registry_agent as ra

    assert models._registry is ra
