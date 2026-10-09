"""tests/test_universal_workflow_runner_20260508.py - universal_workflow_runner 단위 테스트"""

from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_BLOCKED,
)
from core.agent_runtime.runtime.universal.universal_workflow_runner import (
    run_single_action,
    run_workflow,
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


def _dummy_runner(action, domain, **kwargs):
    return {"ok": True, "action": action, "domain": domain}


def test_run_workflow_readonly_returns_result():
    result = run_workflow("g2b_public", "government_readonly_status_check", runner_fn=_dummy_runner)
    assert "status" in result
    assert "site_id" in result
    assert result["site_id"] == "g2b_public"


def test_run_workflow_safe_fields_always_false():
    result = run_workflow("generic_content_site", "readonly_site_explore", runner_fn=_dummy_runner)
    for f in _SAFE_FIELDS:
        assert result.get(f) is False, f"{f} != False"


def test_run_workflow_server_browser_used_false():
    result = run_workflow("naver_blog", "blog_publish_with_permission", runner_fn=_dummy_runner)
    assert result.get("server_browser_used") is False


def test_run_workflow_unknown_site_returns_failed():
    result = run_workflow("totally_unknown_site_xyz", "readonly_site_explore")
    assert result["status"] == "FAILED"


def test_run_workflow_unknown_template_returns_failed():
    result = run_workflow("naver", "nonexistent_template_xyz")
    assert result["status"] == "FAILED"


def test_run_workflow_dry_run_skips_delegated():
    result = run_workflow("naver_blog", "blog_publish_with_permission", runner_fn=_dummy_runner, dry_run=True)
    assert result is not None
    for f in _SAFE_FIELDS:
        assert result.get(f) is False


def test_run_single_action_auto_allowed():
    result = run_single_action("naver", "readonly_explore", domain="naver.com", runner_fn=_dummy_runner)
    assert "status" in result
    assert result.get("server_browser_used") is False


def test_run_single_action_blocked():
    result = run_single_action("naver", "password_save", domain="naver.com", runner_fn=_dummy_runner)
    assert result["status"] in (STATUS_BLOCKED, "BLOCKED")


def test_run_single_action_safe_fields():
    result = run_single_action("naver_cafe", "readonly_explore", domain="cafe.naver.com", runner_fn=_dummy_runner)
    for f in _SAFE_FIELDS:
        assert result.get(f) is False
