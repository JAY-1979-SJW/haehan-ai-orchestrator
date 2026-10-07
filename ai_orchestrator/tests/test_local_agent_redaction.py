"""로컬 에이전트 민감정보 제거 정책 테스트.

local_agent_redaction 모듈이 _SENSITIVE_KEYS, _strip_sensitive,
_RESULT_DATA_ALLOWED_KEYS, _sanitize_url_for_storage, _strip_result_data
를 올바르게 정의하고, 기존 registry behavior를 유지함을 검증한다.
"""


def test_sensitive_keys_defined():
    """_SENSITIVE_KEYS가 정의되어 있고 필수 키를 포함한다."""
    from ai_orchestrator.agent_hub.redaction import _SENSITIVE_KEYS

    assert isinstance(_SENSITIVE_KEYS, frozenset)
    assert len(_SENSITIVE_KEYS) > 0

    # 필수 민감 키들
    required_keys = {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "device_token",
        "approval_token",
        "final_approval_token",
        "token_hash",
        "cookie",
        "cookies",
        "session",
        "client_secret",
        "secret",
        "api_secret",
        "api_key",
        "auth",
        "authorization",
    }
    assert required_keys.issubset(_SENSITIVE_KEYS)


def test_strip_sensitive_removes_keys():
    """_strip_sensitive가 민감 키를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_sensitive

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
    from ai_orchestrator.agent_hub.redaction import _strip_sensitive

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
    from ai_orchestrator.agent_hub.redaction import _strip_sensitive

    result = _strip_sensitive({})
    assert result == {}

    result = _strip_sensitive(None)
    assert result == {}


def test_result_data_allowed_keys_defined():
    """_RESULT_DATA_ALLOWED_KEYS가 정의되어 있고 필수 키를 포함한다."""
    from ai_orchestrator.agent_hub.redaction import _RESULT_DATA_ALLOWED_KEYS

    assert isinstance(_RESULT_DATA_ALLOWED_KEYS, frozenset)
    assert len(_RESULT_DATA_ALLOWED_KEYS) > 0

    # 필수 허용 키들
    required_keys = {
        "action",
        "dry_run",
        "normalized_url",
        "url_scheme",
        "url_host",
        "would_open_browser",
        "external_network_call",
        "requires_approval",
        "policy_decision",
        "message",
        "reason",
        "error_code",
    }
    assert required_keys.issubset(_RESULT_DATA_ALLOWED_KEYS)


def test_sanitize_url_removes_query_string():
    """_sanitize_url_for_storage가 쿼리 문자열을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _sanitize_url_for_storage

    url = "https://example.com/path?token=secret&param=value"
    result = _sanitize_url_for_storage(url)

    assert "token" not in result
    assert "secret" not in result
    assert "param" not in result
    assert result == "https://example.com/path"


def test_sanitize_url_keeps_fragment():
    """_sanitize_url_for_storage가 fragment를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _sanitize_url_for_storage

    url = "https://example.com/path#section"
    result = _sanitize_url_for_storage(url)

    assert "section" not in result
    assert result == "https://example.com/path"


def test_sanitize_url_handles_invalid():
    """_sanitize_url_for_storage가 잘못된 URL을 안전하게 처리한다."""
    from ai_orchestrator.agent_hub.redaction import _sanitize_url_for_storage

    # 파일 경로처럼 보이지만 스키마 없는 경우 - path로 해석됨
    result = _sanitize_url_for_storage("not a url")
    # urlparse는 스키마가 없으면 path로 해석하므로 path만 반환
    assert result == "not a url"


def test_strip_result_data_allows_safe_keys():
    """_strip_result_data가 허용된 키만 저장한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

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
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "open_url",
        "normalized_url": "https://example.com/page?session=abc123",
    }
    result = _strip_result_data(data)

    assert "action" in result
    assert result["normalized_url"] == "https://example.com/page"


def test_strip_result_data_none_returns_none():
    """_strip_result_data가 None/empty를 처리한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    assert _strip_result_data(None) is None
    assert _strip_result_data({}) is None
    assert _strip_result_data([]) is None


def test_strip_result_data_long_strings_truncated():
    """_strip_result_data가 긴 문자열을 500자로 제한한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    long_string = "x" * 1000
    data = {
        "message": long_string,
    }
    result = _strip_result_data(data)

    assert len(result["message"]) == 500


def test_strip_result_data_preserves_bool_int_float():
    """_strip_result_data가 bool/int/float를 그대로 저장한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

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
    from ai_orchestrator.agent_hub.registry.facade import enqueue_task

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
    from ai_orchestrator.agent_hub.registry.facade import (
        apply_result,
        enqueue_task,
        mark_approved,
        mark_delivered,
        mark_running,
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
    from ai_orchestrator.agent_hub.registry.facade import get_task

    updated_task = get_task(task.agent_id, task.task_id)
    assert updated_task is not None
    assert updated_task.result_data is not None
    assert "screenshot_taken" in updated_task.result_data
    assert "password" not in updated_task.result_data
    assert "message" in updated_task.result_data


def test_strip_capabilities_allows_bool_values():
    """_strip_capabilities가 bool 값을 유지한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    capabilities = {
        "browser_supported": True,
        "office_supported": False,
        "cad_supported": True,
    }
    result = _strip_capabilities(capabilities)

    assert result is not None
    assert result["browser_supported"] is True
    assert result["office_supported"] is False
    assert result["cad_supported"] is True


def test_strip_capabilities_removes_non_bool():
    """_strip_capabilities가 bool이 아닌 값을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    capabilities = {
        "browser_supported": True,
        "office_supported": "true",  # string, not bool
        "cad_supported": 1,  # int, not bool
        "unknown_key": False,
    }
    result = _strip_capabilities(capabilities)

    assert result is not None
    assert "browser_supported" in result
    assert "office_supported" not in result
    assert "cad_supported" not in result
    assert "unknown_key" not in result


def test_strip_capabilities_removes_unknown_keys():
    """_strip_capabilities가 미승인 key를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    capabilities = {
        "browser_supported": True,
        "path": "/home/user",  # not allowed
        "hostname": "pc-001",  # not allowed
        "office_supported": False,
    }
    result = _strip_capabilities(capabilities)

    assert result is not None
    assert "browser_supported" in result
    assert "office_supported" in result
    assert "path" not in result
    assert "hostname" not in result


def test_strip_capabilities_empty_dict_returns_none():
    """_strip_capabilities가 빈 dict를 None으로 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    result = _strip_capabilities({})
    assert result is None

    result = _strip_capabilities({"unknown": True})
    assert result is None


def test_strip_capabilities_non_dict_returns_none():
    """_strip_capabilities가 dict가 아니면 None을 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    assert _strip_capabilities(None) is None
    assert _strip_capabilities("string") is None
    assert _strip_capabilities([True, False]) is None
    assert _strip_capabilities(True) is None


def test_strip_result_data_preserves_capabilities():
    """_strip_result_data가 capabilities를 nested allowlist로 저장한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "safe_desktop_capability",
        "status": "ok",
        "capabilities": {
            "browser_supported": True,
            "office_supported": False,
            "cad_supported": False,
        },
    }
    result = _strip_result_data(data)

    assert result is not None
    assert result["action"] == "safe_desktop_capability"
    assert result["status"] == "ok"
    assert "capabilities" in result
    assert result["capabilities"]["browser_supported"] is True
    assert result["capabilities"]["office_supported"] is False
    assert result["capabilities"]["cad_supported"] is False


def test_strip_result_data_filters_unsafe_capabilities():
    """_strip_result_data가 capabilities의 민감값/미승인값을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "safe_desktop_capability",
        "capabilities": {
            "browser_supported": True,
            "password": "secret",  # sensitive
            "username": "admin",  # not allowed
            "office_supported": "yes",  # non-bool
            "cad_supported": True,
        },
    }
    result = _strip_result_data(data)

    assert result is not None
    assert "capabilities" in result
    # 허용된 bool values만 유지
    assert result["capabilities"]["browser_supported"] is True
    assert result["capabilities"]["cad_supported"] is True
    # non-bool / sensitive / unknown 제거
    assert "office_supported" not in result["capabilities"]
    assert "password" not in result["capabilities"]
    assert "username" not in result["capabilities"]


def test_strip_result_data_removes_empty_capabilities():
    """_strip_result_data가 빈 capabilities를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "test",
        "capabilities": {},
    }
    result = _strip_result_data(data)

    # action은 있지만 empty capabilities는 없어야 함
    assert result is not None
    assert "action" in result
    assert "capabilities" not in result


def test_strip_result_data_preserves_safe_echo():
    """_strip_result_data가 safe_echo result를 정상 처리한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "safe_echo",
        "status": "ok",
    }
    result = _strip_result_data(data)

    assert result is not None
    assert result["action"] == "safe_echo"
    assert result["status"] == "ok"


def test_strip_capabilities_case_insensitive():
    """_strip_capabilities가 대소문자 구분 없이 allowed keys를 인식한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_capabilities

    # mixed case input
    capabilities = {
        "browser_supported": True,
        "OFFICE_SUPPORTED": False,  # uppercase key - lowercase 비교로 인식
        "CAD_SUPPORTED": True,  # all uppercase - lowercase 비교로 인식
    }
    result = _strip_capabilities(capabilities)

    assert result is not None
    # 실제로는 lowercase 비교(k_low)로 인식하므로 모두 유지됨
    assert result.get("browser_supported") is True
    assert result.get("OFFICE_SUPPORTED") is False
    assert result.get("CAD_SUPPORTED") is True


def test_strip_apps_allows_valid_items():
    """_strip_apps가 valid app items를 유지한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        {"app_id": "browser", "supported": True},
        {"app_id": "office", "supported": False},
        {"app_id": "cad", "supported": True},
    ]
    result = _strip_apps(apps)

    assert result is not None
    assert len(result) == 3
    assert result[0]["app_id"] == "browser"
    assert result[0]["supported"] is True
    assert result[1]["app_id"] == "office"
    assert result[1]["supported"] is False
    assert result[2]["app_id"] == "cad"
    assert result[2]["supported"] is True


def test_strip_apps_removes_non_bool_supported():
    """_strip_apps가 bool이 아닌 supported 값을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        {"app_id": "browser", "supported": True},
        {"app_id": "office", "supported": "false"},  # string, not bool
        {"app_id": "cad", "supported": 1},  # int, not bool
    ]
    result = _strip_apps(apps)

    assert result is not None
    assert len(result) == 1
    assert result[0]["app_id"] == "browser"


def test_strip_apps_removes_non_string_app_id():
    """_strip_apps가 string이 아닌 app_id를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        {"app_id": "browser", "supported": True},
        {"app_id": 123, "supported": False},  # int, not string
        {"app_id": None, "supported": True},  # None, not string
    ]
    result = _strip_apps(apps)

    assert result is not None
    assert len(result) == 1
    assert result[0]["app_id"] == "browser"


def test_strip_apps_removes_unknown_keys():
    """_strip_apps가 app_id/supported 외의 key를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        {
            "app_id": "browser",
            "supported": True,
            "path": "/Program Files/...",  # not allowed
            "version": "120.0",  # not allowed
        }
    ]
    result = _strip_apps(apps)

    assert result is not None
    assert len(result) == 1
    assert result[0] == {"app_id": "browser", "supported": True}
    assert "path" not in result[0]
    assert "version" not in result[0]


def test_strip_apps_skips_non_dict_items():
    """_strip_apps가 dict가 아닌 항목을 skip한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        {"app_id": "browser", "supported": True},
        "not_a_dict",
        None,
        123,
        {"app_id": "office", "supported": False},
    ]
    result = _strip_apps(apps)

    assert result is not None
    assert len(result) == 2
    assert result[0]["app_id"] == "browser"
    assert result[1]["app_id"] == "office"


def test_strip_apps_non_list_returns_none():
    """_strip_apps가 list가 아니면 None을 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    assert _strip_apps(None) is None
    assert _strip_apps("not_a_list") is None
    assert _strip_apps(123) is None
    assert _strip_apps({"key": "value"}) is None


def test_strip_apps_empty_list_returns_none():
    """_strip_apps가 빈 list를 None으로 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    result = _strip_apps([])
    assert result is None


def test_strip_apps_all_invalid_items_returns_none():
    """_strip_apps가 모든 항목이 invalid이면 None을 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_apps

    apps = [
        "not_dict",
        123,
        None,
    ]
    result = _strip_apps(apps)
    assert result is None


def test_strip_result_data_preserves_apps():
    """_strip_result_data가 apps를 nested allowlist로 저장한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "safe_app_presence_known_paths",
        "status": "ok",
        "detection_mode": "known_path_boolean",
        "apps": [
            {"app_id": "browser", "supported": True},
            {"app_id": "office", "supported": False},
            {"app_id": "cad", "supported": False},
        ],
    }
    result = _strip_result_data(data)

    assert result is not None
    assert result["action"] == "safe_app_presence_known_paths"
    assert result["status"] == "ok"
    assert result["detection_mode"] == "known_path_boolean"
    assert "apps" in result
    assert len(result["apps"]) == 3
    assert result["apps"][0]["app_id"] == "browser"
    assert result["apps"][0]["supported"] is True
    assert result["apps"][1]["app_id"] == "office"
    assert result["apps"][1]["supported"] is False


def test_strip_result_data_filters_unsafe_apps():
    """_strip_result_data가 apps의 민감값/미승인값을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "safe_app_presence_known_paths",
        "apps": [
            {
                "app_id": "browser",
                "supported": True,
                "path": "/Program Files/Chrome",  # not allowed
                "version": "120.0",  # not allowed
                "password": "secret",  # sensitive
            }
        ],
    }
    result = _strip_result_data(data)

    assert result is not None
    assert "apps" in result
    assert len(result["apps"]) == 1
    assert result["apps"][0] == {"app_id": "browser", "supported": True}
    assert "path" not in result["apps"][0]
    assert "version" not in result["apps"][0]
    assert "password" not in result["apps"][0]


def test_strip_result_data_removes_empty_apps():
    """_strip_result_data가 빈 apps를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "test",
        "apps": [],
    }
    result = _strip_result_data(data)

    # action은 있지만 empty apps는 없어야 함
    assert result is not None
    assert "action" in result
    assert "apps" not in result


# ── browser.inspect redaction tests ───────────────────────────────────────────


def test_strip_result_data_preserves_browser_inspect():
    """_strip_result_data가 browser.inspect 결과를 보존한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "browser.inspect",
        "status": "ok",
        "inspection_mode": "page_layout",
        "plan": {
            "action_id": "browser.inspect",
            "will_open_browser": False,
            "will_access_dom": False,
            "will_capture_screenshot": False,
            "requires_approval": True,
        },
        "capabilities": {
            "can_plan_inspection": True,
            "actual_inspection_enabled": False,
        },
    }
    result = _strip_result_data(data)

    # 모든 허용 필드 보존
    assert result is not None
    assert result.get("action") == "browser.inspect"
    assert result.get("status") == "ok"
    assert result.get("inspection_mode") == "page_layout"
    # plan 보존
    assert "plan" in result
    plan = result["plan"]
    assert plan.get("action_id") == "browser.inspect"
    assert plan.get("will_open_browser") is False
    assert plan.get("will_access_dom") is False
    assert plan.get("will_capture_screenshot") is False
    assert plan.get("requires_approval") is True
    # capabilities 보존
    assert "capabilities" in result
    caps = result["capabilities"]
    assert caps.get("can_plan_inspection") is True
    assert caps.get("actual_inspection_enabled") is False


def test_strip_result_data_filters_invalid_inspection_mode():
    """_strip_result_data가 잘못된 inspection_mode를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "browser.inspect",
        "inspection_mode": "invalid_mode",  # 허용되지 않는 값
        "plan": {"action_id": "browser.inspect"},
    }
    result = _strip_result_data(data)

    # invalid_mode는 제거되어야 함
    assert result is not None
    assert "inspection_mode" not in result


def test_strip_result_data_allows_safe_fields_for_browser_inspect():
    """_strip_result_data는 browser.inspect의 안전 필드를 허용한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    # selector는 allowlist에 있으므로 허용되지만, browser.inspect 핸들러는 반환하지 않음
    data = {
        "action": "browser.inspect",
        "status": "ok",
        "inspection_mode": "page_layout",
        "plan": {"action_id": "browser.inspect"},
        "capabilities": {"can_plan_inspection": True, "actual_inspection_enabled": False},
        # selector는 allowlist에 있으므로 통과하지만, 핸들러는 생성하지 않음
        "selector": "div.content",
    }
    result = _strip_result_data(data)

    # selector는 allowlist에 있으므로 보존됨 (하지만 핸들러가 생성하지 않으므로 실제로는 나타나지 않음)
    assert result is not None
    assert result.get("action") == "browser.inspect"
    assert result.get("inspection_mode") == "page_layout"
    assert "plan" in result
    assert "capabilities" in result


def test_strip_result_data_blocks_sensitive_fields_not_in_allowlist():
    """_strip_result_data는 allowlist에 없는 민감 필드를 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "browser.inspect",
        "status": "ok",
        "inspection_mode": "page_layout",
        "plan": {"action_id": "browser.inspect"},
        "capabilities": {"can_plan_inspection": True, "actual_inspection_enabled": False},
        # 금지된 필드들 (allowlist에 없음)
        "raw_dom": "<html>...</html>",
        "raw_html": "<body>...</body>",
        "raw_params": {"url": "https://example.com"},
        "private_cookie": "secret=value",
        "browser_profile": "/home/user/.config/browser",
    }
    result = _strip_result_data(data)

    # allowlist에 없는 필드 제거
    assert "raw_dom" not in result
    assert "raw_html" not in result
    assert "raw_params" not in result
    assert "private_cookie" not in result
    assert "browser_profile" not in result
    # 허용 필드는 보존
    assert result.get("action") == "browser.inspect"
    assert "plan" in result
    assert "capabilities" in result


def test_strip_browser_nested_allowlist():
    """_strip_browser가 browser nested allowlist를 올바르게 처리한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_browser

    # valid browser dict
    browser_data = {
        "isolated_context": True,
        "used_existing_profile": False,
        "opened": True,
        "closed": True,
    }
    result = _strip_browser(browser_data)

    assert result is not None
    assert result.get("isolated_context") is True
    assert result.get("used_existing_profile") is False
    assert result.get("opened") is True
    assert result.get("closed") is True


def test_strip_browser_filters_non_bool():
    """_strip_browser가 non-boolean 값을 제거한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_browser

    browser_data = {
        "isolated_context": True,
        "used_existing_profile": False,
        "browser_pid": 12345,  # int, should be removed
        "profile_path": "/home/user/.config",  # str, should be removed
        "opened": True,
    }
    result = _strip_browser(browser_data)

    assert result is not None
    assert "isolated_context" in result
    assert "opened" in result
    assert "browser_pid" not in result
    assert "profile_path" not in result


def test_strip_browser_rejects_non_dict():
    """_strip_browser는 dict가 아니면 None을 반환한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_browser

    assert _strip_browser("not a dict") is None
    assert _strip_browser([1, 2, 3]) is None
    assert _strip_browser(None) is None


def test_strip_result_data_preserves_browser_open_url_controlled():
    """_strip_result_data는 browser.open_url_controlled 데이터를 올바르게 처리한다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "browser.open_url_controlled",
        "status": "ok",
        "execution_mode": "isolated_sample_open",
        "approval_required": True,
        "target": {
            "scheme": "https",
            "host_class": "sample",
            "url_redacted": True,
        },
        "browser": {
            "isolated_context": True,
            "used_existing_profile": False,
            "opened": True,
            "closed": True,
        },
    }
    result = _strip_result_data(data)

    # 모든 허용 필드 보존
    assert result is not None
    assert result.get("action") == "browser.open_url_controlled"
    assert result.get("status") == "ok"
    assert result.get("execution_mode") == "isolated_sample_open"
    assert result.get("approval_required") is True
    # target 보존
    assert "target" in result
    target = result["target"]
    assert target.get("scheme") == "https"
    assert target.get("host_class") == "sample"
    assert target.get("url_redacted") is True
    # browser 보존
    assert "browser" in result
    browser = result["browser"]
    assert browser.get("isolated_context") is True
    assert browser.get("used_existing_profile") is False
    assert browser.get("opened") is True
    assert browser.get("closed") is True


def test_strip_result_data_removes_raw_url_from_browser_open_url_controlled():
    """_strip_result_data는 browser.open_url_controlled에서 금지된 필드를 제거한다.

    allowlist에 없는 필드만 제거된다.
    allowlist에 있지만 handler가 반환하지 않는 필드도 있음 (policy는 allowlist, handler 책임).
    """
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    data = {
        "action": "browser.open_url_controlled",
        "status": "ok",
        "execution_mode": "isolated_sample_open",
        "approval_required": True,
        "target": {
            "scheme": "https",
            "host_class": "sample",
            "url_redacted": True,
        },
        "browser": {
            "isolated_context": True,
            "used_existing_profile": False,
            "opened": True,
            "closed": True,
        },
        # forbidden fields not in allowlist → will be removed
        "raw_url": "https://example.com/",
        "browser_pid": 12345,
        "profile_path": "/home/user/.config",
        "window_handle": "CDwindow-abc123",
    }
    result = _strip_result_data(data)

    # forbidden fields removed (not in allowlist)
    assert "raw_url" not in result
    assert "browser_pid" not in result
    assert "profile_path" not in result
    assert "window_handle" not in result
    # allowed fields preserved
    assert result.get("action") == "browser.open_url_controlled"
    assert "target" in result
    assert "browser" in result


# ── 값 수준 비밀 마스킹 ──
# 실제 키 형식 문자열을 소스에 그대로 쓰면 gitleaks 가 잡으므로 조각을 코드에서 조립한다.
def _fake(prefix: str, n: int) -> str:
    return prefix + ("x9Y8z7W6v5" * (n // 10 + 1))[:n]


def test_strip_result_data_masks_secret_values_in_result_full():
    """result_full 본문에 섞인 sk-/AIza/Bearer/KEY= 값이 저장 전에 가려진다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    sk = _fake("s" + "k-", 30)
    aiza = _fake("AI" + "za", 35)
    bearer = _fake("", 30)
    env_val = _fake("", 16)
    text = f"키 {sk} 와 {aiza}, Authorization: Bearer {bearer}, OPENAI_API_KEY={env_val} 끝"
    out = _strip_result_data({"result_full": text, "result": text})
    for field in ("result_full", "result"):
        masked = out[field]
        for secret in (sk, aiza, bearer, env_val):
            assert secret not in masked
        assert "[REDACTED]" in masked
        assert "OPENAI_API_KEY=[REDACTED]" in masked
        assert "Bearer [REDACTED]" in masked
        assert masked.startswith("키 ") and masked.endswith(" 끝")


def test_strip_result_data_mask_happens_before_truncation():
    """상한 경계에 걸친 비밀도 일부가 남지 않는다(자르기 전에 마스킹)."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    sk = _fake("s" + "k-", 40)
    text = "x" * 489 + " " + sk  # 비밀이 500자 경계에 걸침
    out = _strip_result_data({"result": text})["result"]
    assert len(out) <= 500
    assert "x9Y8z7" not in out  # 비밀 본문 조각이 남지 않는다
    assert "s" + "k-" not in out


def test_strip_result_data_does_not_overmask_plain_text():
    """일반 문장·짧은 값·소문자 변수는 건드리지 않는다."""
    from ai_orchestrator.agent_hub.redaction import _strip_result_data

    text = "task-id sk-short, key=value, token: required, MAX_TOKENS=4096, Bearer short"
    out = _strip_result_data({"result_full": text})["result_full"]
    assert out == text
