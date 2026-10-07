"""로컬 에이전트 risk policy 모듈 테스트.

local_agent_risk_policy 모듈이 ACTION_RISK, _SERVER_AUTO_COMPLETE,
ALLOWED_APPS를 올바르게 정의하고, 기존 registry behavior를 유지함을 검증한다.
"""

import pytest


def test_action_risk_defined():
    """ACTION_RISK가 정의되어 있고 필수 액션들을 포함한다."""
    from ai_orchestrator.agent_hub.policy.risk_policy import ACTION_RISK

    assert isinstance(ACTION_RISK, dict)
    assert len(ACTION_RISK) > 0

    # 필수 액션들 검증
    required_actions = {
        "ping", "system_info", "list_allowed_apps", "open_url",
        "open_url_execute", "list_files_readonly", "capture_screenshot"
    }
    assert required_actions.issubset(set(ACTION_RISK.keys()))


def test_action_risk_levels():
    """ACTION_RISK의 risk_level 값이 예상과 일치한다."""
    from ai_orchestrator.agent_hub.policy.risk_policy import ACTION_RISK

    # low risk
    assert ACTION_RISK["ping"] == "low"
    assert ACTION_RISK["system_info"] == "low"
    assert ACTION_RISK["list_allowed_apps"] == "low"
    assert ACTION_RISK["open_url"] == "low"
    assert ACTION_RISK["web_open_url_readonly"] == "low"

    # medium risk
    assert ACTION_RISK["list_files_readonly"] == "medium"

    # high risk
    assert ACTION_RISK["open_url_execute"] == "high"
    assert ACTION_RISK["capture_screenshot"] == "high"


def test_server_auto_complete_defined():
    """_SERVER_AUTO_COMPLETE가 정의되어 있고 올바른 액션을 포함한다."""
    from ai_orchestrator.agent_hub.policy.risk_policy import _SERVER_AUTO_COMPLETE

    assert isinstance(_SERVER_AUTO_COMPLETE, frozenset)
    assert "ping" in _SERVER_AUTO_COMPLETE
    assert "system_info" in _SERVER_AUTO_COMPLETE
    assert "list_allowed_apps" in _SERVER_AUTO_COMPLETE
    assert len(_SERVER_AUTO_COMPLETE) == 3


def test_allowed_apps_defined():
    """ALLOWED_APPS가 정의되어 있고 올바른 앱을 포함한다."""
    from ai_orchestrator.agent_hub.policy.risk_policy import ALLOWED_APPS

    assert isinstance(ALLOWED_APPS, list)
    assert "browser" in ALLOWED_APPS
    assert "excel" in ALLOWED_APPS
    assert "hwp" in ALLOWED_APPS
    assert "cad" in ALLOWED_APPS
    assert len(ALLOWED_APPS) == 4


def test_registry_uses_action_risk():
    """registry가 ACTION_RISK를 올바르게 사용한다."""
    from ai_orchestrator.agent_hub.registry.facade import (
        UnknownActionError,
        enqueue_task,
    )

    # 알려진 액션은 성공
    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    assert task.action == "ping"
    assert task.risk_level == "low"

    # 미등록 액션은 실패
    with pytest.raises(UnknownActionError):
        enqueue_task(
            agent_id="test-agent",
            action="unknown_action",
            params={},
            requested_by="test-user",
        )


def test_risk_level_high_requires_approval():
    """high risk 액션은 waiting_approval 상태로 생성된다."""
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="capture_screenshot",
        params={},
        requested_by="test-user",
    )
    assert task.action == "capture_screenshot"
    assert task.risk_level == "high"
    assert task.status == "waiting_approval"


def test_server_auto_complete_behavior():
    """_SERVER_AUTO_COMPLETE 액션은 completed 상태로 생성된다."""
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="ping",
        params={},
        requested_by="test-user",
    )
    assert task.action == "ping"
    assert task.status == "completed"


def test_low_risk_non_auto_complete_action():
    """low risk이지만 non-auto-complete 액션은 queued 상태."""
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="open_url",
        params={"url": "http://example.com"},
        requested_by="test-user",
    )
    assert task.action == "open_url"
    assert task.risk_level == "low"
    assert task.status == "queued"


def test_web_open_url_readonly_is_low_risk_queued():
    """read-only browser observation is queued for local agent execution."""
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="web_open_url_readonly",
        params={"url": "https://example.com/"},
        requested_by="test-user",
    )
    assert task.action == "web_open_url_readonly"
    assert task.risk_level == "low"
    assert task.status == "queued"


def test_medium_risk_action():
    """medium risk 액션은 queued 상태."""
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="list_files_readonly",
        params={},
        requested_by="test-user",
    )
    assert task.action == "list_files_readonly"
    assert task.risk_level == "medium"
    assert task.status == "queued"


def test_browser_actions_defined():
    """browser automation 액션들이 정의되어 있다."""
    from ai_orchestrator.agent_hub.policy.risk_policy import ACTION_RISK

    browser_actions = {
        "browser.inspect": "low",
        "browser.plan_click": "low",
        "browser.plan_type": "low",
        "browser.plan_submit": "low",
        "browser.execute_click": "medium",
        "browser.execute_type": "medium",
    }

    for action, expected_risk in browser_actions.items():
        assert action in ACTION_RISK
        assert ACTION_RISK[action] == expected_risk


def test_web_open_url_readonly_auto_execute_registered():
    from ai_orchestrator.contracts.local_agent_actions import AUTO_EXECUTE_VIA_AGENT

    assert "web_open_url_readonly" in AUTO_EXECUTE_VIA_AGENT
