"""로컬 에이전트 민감정보 제거 정책 테스트.

local_agent_redaction 모듈이 _SENSITIVE_KEYS, _strip_sensitive,
_RESULT_DATA_ALLOWED_KEYS, _sanitize_url_for_storage, _strip_result_data
를 올바르게 정의하고, 기존 registry behavior를 유지함을 검증한다.
"""

import pytest


def test_sensitive_keys_defined():
    """_SENSITIVE_KEYS가 정의되어 있고 필수 키를 포함한다."""
    from ai_orchestrator.local_agent_redaction import _SENSITIVE_KEYS

    assert isinstance(_SENSITIVE_KEYS, frozenset)
    assert len(_SENSITIVE_KEYS) > 0

    # 필수 민감 키들
    required_keys = {
        "password", "passwd", "pwd",
        "token", "access_token", "refresh_token", "session_token",
        "device_token", "approval_token", "final_approval_token", "token_hash",
        "cookie", "cookies", "session",
        "client_secret", "secret", "api_secret", "api_key",
        "auth", "authorization",
    }
    assert required_keys.issubset(_SENSITIVE_KEYS)


def test_strip_sensitive_removes_keys():
    """_strip_sensitive가 민감 키를 제거한다."""
    from ai_orchestrator.local_agent_redaction import _strip_sensitive

    params = {
        "url": "http://example.com",
        "password": "secret123",
        "token": "abc123",
        "safe_param": "value",
    }
    result = _strip_sensitive(params)

    assert "url" in result
    assert "safe_param" in result
    assert "password" not in result
    assert "token" not in result


def test_strip_sensitive_case_insensitive():
    """_strip_sensitive는 대소문자 구분 없이 민감 키를 제거한다."""
    from ai_orchestrator.local_agent_redaction import _strip_sensitive

    params = {
        "PASSWORD": "secret",
        "Token": "abc",
        "API_KEY": "key123",
        "normal": "ok",
    }
    result = _strip_sensitive(params)

    assert "PASSWORD" not in result
    assert "Token" not in result
    assert "API_KEY" not in result
    assert "normal" in result


def test_strip_sensitive_empty_dict():
    """_strip_sensitive가 빈 dict를 처리한다."""
    from ai_orchestrator.local_agent_redaction import _strip_sensitive

    result = _strip_sensitive({})
    assert result == {}

    result = _strip_sensitive(None)
    assert result == {}


def test_result_data_allowed_keys_defined():
    """_RESULT_DATA_ALLOWED_KEYS가 정의되어 있고 필수 키를 포함한다."""
    from ai_orchestrator.local_agent_redaction import _RESULT_DATA_ALLOWED_KEYS

    assert isinstance(_RESULT_DATA_ALLOWED_KEYS, frozenset)
    assert len(_RESULT_DATA_ALLOWED_KEYS) > 0

    # 필수 허용 키들
    required_keys = {
        "action", "dry_run", "normalized_url", "url_scheme", "url_host",
        "would_open_browser", "external_network_call", "requires_approval",
        "policy_decision", "message", "reason", "error_code",
    }
    assert required_keys.issubset(_RESULT_DATA_ALLOWED_KEYS)


def test_sanitize_url_removes_query_string():
    """_sanitize_url_for_storage가 쿼리 문자열을 제거한다."""
    from ai_orchestrator.local_agent_redaction import _sanitize_url_for_storage

    url = "https://example.com/path?token=secret&param=value"
    result = _sanitize_url_for_storage(url)

    assert "token" not in result
    assert "secret" not in result
    assert "param" not in result
    assert result == "https://example.com/path"


def test_sanitize_url_keeps_fragment():
    """_sanitize_url_for_storage가 fragment를 제거한다."""
    from ai_orchestrator.local_agent_redaction import _sanitize_url_for_storage

    url = "https://example.com/path#section"
    result = _sanitize_url_for_storage(url)

    assert "section" not in result
    assert result == "https://example.com/path"


def test_sanitize_url_handles_invalid():
    """_sanitize_url_for_storage가 잘못된 URL을 안전하게 처리한다."""
    from ai_orchestrator.local_agent_redaction import _sanitize_url_for_storage

    # 파일 경로처럼 보이지만 스키마 없는 경우 - path로 해석됨
    result = _sanitize_url_for_storage("not a url")
    # urlparse는 스키마가 없으면 path로 해석하므로 path만 반환
    assert result == "not a url"


def test_strip_result_data_allows_safe_keys():
    """_strip_result_data가 허용된 키만 저장한다."""
    from ai_orchestrator.local_agent_redaction import _strip_result_data

    data = {
        "action": "ping",
        "message": "success",
        "password": "secret",  # 민감키
        "unknown_field": "value",  # 미승인
    }
    result = _strip_result_data(data)

    assert "action" in result
    assert "message" in result
    assert "password" not in result
    assert "unknown_field" not in result


def test_strip_result_data_sanitizes_url():
    """_strip_result_data가 normalized_url의 쿼리를 제거한다."""
    from ai_orchestrator.local_agent_redaction import _strip_result_data

    data = {
        "action": "open_url",
        "normalized_url": "https://example.com/page?session=abc123",
    }
    result = _strip_result_data(data)

    assert "action" in result
    assert result["normalized_url"] == "https://example.com/page"


def test_strip_result_data_none_returns_none():
    """_strip_result_data가 None/empty를 처리한다."""
    from ai_orchestrator.local_agent_redaction import _strip_result_data

    assert _strip_result_data(None) is None
    assert _strip_result_data({}) is None
    assert _strip_result_data([]) is None


def test_strip_result_data_long_strings_truncated():
    """_strip_result_data가 긴 문자열을 500자로 제한한다."""
    from ai_orchestrator.local_agent_redaction import _strip_result_data

    long_string = "x" * 1000
    data = {
        "message": long_string,
    }
    result = _strip_result_data(data)

    assert len(result["message"]) == 500


def test_strip_result_data_preserves_bool_int_float():
    """_strip_result_data가 bool/int/float를 그대로 저장한다."""
    from ai_orchestrator.local_agent_redaction import _strip_result_data

    data = {
        "executed": True,
        "status": 200,
        "message": None,
    }
    result = _strip_result_data(data)

    assert result["executed"] is True
    assert result["status"] == 200
    assert result["message"] is None
    assert isinstance(result["executed"], bool)
    assert isinstance(result["status"], int)
    assert isinstance(result["message"], type(None))


def test_registry_uses_strip_sensitive():
    """registry의 enqueue_task가 _strip_sensitive를 사용한다."""
    from ai_orchestrator.local_agent_registry import enqueue_task

    task = enqueue_task(
        agent_id="test-agent",
        action="open_url",
        params={"url": "http://example.com", "password": "secret"},
        requested_by="test-user",
    )

    # task.params에는 password가 없어야 함
    assert "url" in task.params
    assert "password" not in task.params


def test_registry_uses_strip_result_data():
    """registry의 apply_result가 _strip_result_data를 사용한다."""
    from ai_orchestrator.local_agent_registry import (
        enqueue_task, mark_delivered, mark_running, apply_result, mark_approved
    )

    task = enqueue_task(
        agent_id="test-agent",
        action="capture_screenshot",
        params={},
        requested_by="test-user",
    )

    # high-risk이므로 먼저 approve (actor 매개변수 사용)
    mark_approved(task_id=task.task_id, actor="approver-user")

    # 상태 전이
    mark_delivered(task_id=task.task_id, agent_id=task.agent_id)
    mark_running(task_id=task.task_id, agent_id=task.agent_id)

    # result_data에 민감 정보 포함
    result_data = {
        "screenshot_taken": True,
        "password": "should_be_filtered",
        "message": "success",
    }
    apply_result(
        task_id=task.task_id,
        agent_id=task.agent_id,
        success=True,
        data=result_data,
    )

    # task.result_data에 password가 없어야 함
    from ai_orchestrator.local_agent_registry import get_task
    updated_task = get_task(task.agent_id, task.task_id)
    assert updated_task is not None
    assert updated_task.result_data is not None
    assert "screenshot_taken" in updated_task.result_data
    assert "password" not in updated_task.result_data
    assert "message" in updated_task.result_data
