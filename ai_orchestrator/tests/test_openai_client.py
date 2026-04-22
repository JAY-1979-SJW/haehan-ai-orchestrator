import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_mock_mode_when_no_key():
    # config.py가 캐싱하므로 reload 대신 patch로 _MOCK_MODE 직접 제어
    from unittest.mock import patch
    import ai_orchestrator.openai_client as oc
    from ai_orchestrator.models import TaskRequest, RiskAssessment

    req = TaskRequest(
        task_id="T-OAI-001", source="manual", action_type="read_file",
        target="/tmp/x.txt", description="테스트", requested_by="test"
    )
    risk = RiskAssessment(risk_level="low", reasons=[], requires_approval=False)

    with patch.object(oc, "OPENAI_API_KEY", ""), patch.object(oc, "_MOCK_MODE", True):
        summary = oc.generate_task_summary(req, risk)
        assert "[MOCK]" in summary
        assert oc.is_mock_mode()
    print(f"PASS: API 키 없을 때 mock 반환: '{summary[:50]}...'")


def test_fallback_on_exception(monkeypatch=None):
    os.environ.pop("OPENAI_API_KEY", None)

    import importlib
    import ai_orchestrator.openai_client as oc
    importlib.reload(oc)

    from ai_orchestrator.models import TaskRequest, ExecutionPlan
    req = TaskRequest(
        task_id="T-OAI-002", source="manual", action_type="edit_config",
        target="/var/www/cfg.yaml", description="테스트", requested_by="test"
    )
    ep = ExecutionPlan(task_id="T-OAI-002", allowed=True, requires_approval=True)

    reason = oc.generate_approval_reason(req, ep)
    assert isinstance(reason, str) and len(reason) > 0
    print(f"PASS: generate_approval_reason fallback 정상: '{reason[:50]}...'")


if __name__ == "__main__":
    test_mock_mode_when_no_key()
    test_fallback_on_exception()
    print("\n모든 openai_client 테스트 통과")
