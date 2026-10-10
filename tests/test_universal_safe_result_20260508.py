"""tests/test_universal_safe_result_20260508.py - universal_safe_result 단위 테스트"""

from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PERMISSION_REQUIRED,
    STATUS_WARN,
    STATUS_WARN_AUTH,
    STATUS_WARN_PERMISSION,
    build_universal_result,
    merge_step_results,
    sanitize_universal_result,
    validate_universal_result,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


def _base_result(**kwargs):
    defaults = {
        "task_id": "t-001",
        "site_id": "naver_blog",
        "workflow_id": "blog_publish_with_permission",
        "status": STATUS_COMPLETED,
        "actions_executed": ["readonly_explore"],
        "actions_pending_permission": [],
        "actions_user_direct_required": [],
        "blocked_actions": [],
        "safe_outputs": {"text": "hello"},
        "audit_log_ids": ["log-001"],
    }
    defaults.update(kwargs)
    return build_universal_result(**defaults)


def test_build_result_has_safe_fields():
    result = _base_result()
    for field in _SAFE_FIELDS:
        assert field in result, f"safe field 누락: {field} (전체 키: {list(result.keys())})"
        assert result[field] is False, f"{field}가 False가 아님"


def test_server_browser_used_always_false():
    result = _base_result()
    assert result["server_browser_used"] is False


def test_sanitize_removes_prefix_underscore_sensitive():
    result = _base_result()
    result["_internal_secret"] = "secret"
    sanitized = sanitize_universal_result(result)
    # sanitize는 최소한 결과를 반환해야 함
    assert isinstance(sanitized, dict)
    assert sanitized.get("server_browser_used") is False


def test_validate_passes_clean_result():
    result = _base_result()
    errors = validate_universal_result(result)
    assert errors == []


def test_validate_fails_on_sensitive_true():
    result = _base_result()
    result["cookie_exported"] = True
    errors = validate_universal_result(result)
    assert len(errors) > 0


def test_validate_fails_on_server_browser_true():
    result = _base_result()
    result["server_browser_used"] = True
    errors = validate_universal_result(result)
    assert len(errors) > 0


def test_merge_step_results_adds_step():
    base = _base_result(actions_executed=["step_a"])
    step_result = {"action": "step_b", "ok": True, "status": STATUS_COMPLETED}
    merged = merge_step_results(base, step_result, "s_b")
    assert isinstance(merged, dict)
    # safe fields 유지
    for f in _SAFE_FIELDS:
        assert merged.get(f) is False


def test_merge_step_results_blocked_propagates():
    base = _base_result()
    step_result = {"action": "password_save", "ok": False, "status": STATUS_BLOCKED}
    merged = merge_step_results(base, step_result, "s_blocked")
    assert isinstance(merged, dict)
    for f in _SAFE_FIELDS:
        assert merged.get(f) is False


def test_status_constants_distinct():
    statuses = [
        STATUS_COMPLETED,
        STATUS_PERMISSION_REQUIRED,
        STATUS_BLOCKED,
        STATUS_FAILED,
        STATUS_WARN,
        STATUS_WARN_AUTH,
        STATUS_WARN_PERMISSION,
    ]
    assert len(set(statuses)) == len(statuses)
