"""에이전트 결과 전문 길이 상한이 한 정본에서 나오고, 대화 기록 한도가 그보다 작지 않은지 지킨다."""


def test_result_full_limit_single_source():
    from ai_orchestrator.agent_dispatch import agent_dispatch_service as svc
    from ai_orchestrator.agent_dispatch import agent_dispatch_store as store
    from ai_orchestrator.agent_hub.redaction import _RESULT_DATA_LONG_KEYS
    from ai_orchestrator.contracts import agent_result_limits as lim
    from ai_orchestrator.site_work import ai_agent_router as router
    from core.agent_runtime.connection import actions

    assert lim.RESULT_FULL_MAX_CHARS == 20000  # 값은 바꾸지 않는다(통합만)
    assert actions._RESULT_FULL_MAX_CHARS == lim.RESULT_FULL_MAX_CHARS
    assert _RESULT_DATA_LONG_KEYS["result_full"] == lim.RESULT_FULL_MAX_CHARS
    assert router.CHAT_RESULT_MAX_CHARS == lim.RESULT_FULL_MAX_CHARS
    assert svc.RESULT_MAX_CHARS == lim.RESULT_FULL_MAX_CHARS
    assert store.RESULT_MAX_CHARS == lim.RESULT_FULL_MAX_CHARS


def test_chat_message_limit_can_hold_full_result():
    """대화 기록 한도는 의미가 달라 합치지 않지만, 결과 전문보다 작으면 저장 시 잘린다."""
    from ai_orchestrator.contracts import agent_result_limits as lim
    from ai_orchestrator.tasks import chat_sessions

    assert chat_sessions._MAX_MESSAGE_TEXT_LEN >= lim.RESULT_FULL_MAX_CHARS
