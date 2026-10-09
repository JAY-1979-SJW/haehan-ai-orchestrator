"""tests/test_universal_action_verifier_20260508.py"""

from core.agent_runtime.runtime.universal.universal_action_verifier import (
    verify_action_result,
    verify_no_sensitive_data,
    verify_plan_execution,
)
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_COMPLETED,
    build_universal_result,
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


def _clean_result(**kwargs):
    defaults = {
        "task_id": "t1",
        "site_id": "test",
        "workflow_id": "w1",
        "status": STATUS_COMPLETED,
        "actions_executed": ["test_action"],
        "audit_log_ids": ["log1"],
    }
    defaults.update(kwargs)
    return build_universal_result(**defaults)


def test_verify_clean_result_passes():
    result = _clean_result()
    v = verify_action_result("readonly_explore", result)
    assert v["verified"] is True
    assert v["safe_fields_ok"] is True
    assert v["violations"] == []


def test_verify_fails_on_cookie_exported():
    result = _clean_result()
    result["cookie_exported"] = True
    v = verify_action_result("readonly_explore", result)
    assert v["verified"] is False
    assert len(v["violations"]) > 0


def test_verify_fails_on_session_exported():
    result = _clean_result()
    result["session_exported"] = True
    v = verify_action_result("readonly_explore", result)
    assert v["verified"] is False


def test_verify_fails_on_password_collected():
    result = _clean_result()
    result["password_collected"] = True
    v = verify_action_result("any_action", result)
    assert v["verified"] is False


def test_verify_fails_on_server_browser_used():
    result = _clean_result()
    result["server_browser_used"] = True
    v = verify_action_result("any_action", result)
    assert v["verified"] is False


def test_verify_blocked_action_not_executed():
    result = _clean_result(actions_executed=["password_save"])
    result["ok"] = True
    v = verify_action_result("password_save", result)
    assert v["checks"]["blocked_action_not_executed"] is False


def test_audit_log_check():
    result = _clean_result(audit_log_ids=[])
    v = verify_action_result("readonly_explore", result)
    assert v["checks"]["audit_log_exists"] is False


def test_verify_no_sensitive_data_clean():
    result = _clean_result()
    violations = verify_no_sensitive_data(result)
    assert violations == []


def test_verify_no_sensitive_data_with_violation():
    result = _clean_result()
    result["otp_collected"] = True
    violations = verify_no_sensitive_data(result)
    assert len(violations) > 0


def test_verify_plan_execution():
    from core.agent_runtime.runtime.universal.universal_task_planner import create_plan
    from core.agent_runtime.runtime.universal.user_intent_parser import parse_intent

    intent_result = parse_intent("공지사항 찾아줘")
    plan = create_plan(
        intent_result,
        {
            "host": "test.com",
            "risk_signals": [],
            "page_type_candidates": [],
            "visible_actions": [],
            "buttons_observed": [],
            "auth_signals": [],
            "forms_detected": False,
            "download_candidates": [],
        },
        {"site_type": "unknown", "confidence": "low", "matched_profile_id": None, "is_known_site": False},
    )

    executed = ["open_url", "find_notice", "extract_text"]
    results = [_clean_result() for _ in executed]
    v = verify_plan_execution(plan, executed, results)
    assert v["verified"] is True


def test_verify_plan_blocked_action_detected():
    from core.agent_runtime.runtime.universal.universal_task_planner import create_plan
    from core.agent_runtime.runtime.universal.user_intent_parser import parse_intent

    intent_result = parse_intent("공지사항 찾아줘")
    plan = create_plan(
        intent_result,
        {
            "host": "test.com",
            "risk_signals": [],
            "page_type_candidates": [],
            "visible_actions": [],
            "buttons_observed": [],
            "auth_signals": [],
            "forms_detected": False,
            "download_candidates": [],
        },
        {"site_type": "unknown", "confidence": "low", "matched_profile_id": None, "is_known_site": False},
    )

    executed = ["open_url", "password_save"]  # BLOCKED action 실행됨
    results = [_clean_result(), _clean_result()]
    v = verify_plan_execution(plan, executed, results)
    assert v["verified"] is False
