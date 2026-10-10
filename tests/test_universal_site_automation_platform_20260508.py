"""tests/test_universal_site_automation_platform_20260508.py - 플랫폼 통합 테스트"""

from core.agent_runtime.runtime.site_profile.selector_pack_registry import (
    _FORBIDDEN_SELECTOR_KEYS,
    _PACKS,
)
from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    _CAPABILITY_GRADE,
    GRADE_BLOCKED,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import (
    _COMMON_BLOCKED,
    _REGISTRY,
)
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_COMPLETED,
    build_universal_result,
    validate_universal_result,
)
from core.agent_runtime.runtime.universal.universal_workflow_runner import (
    run_single_action,
    run_workflow,
)
from core.agent_runtime.runtime.universal.workflow_template_engine import _TEMPLATES

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

_FORBIDDEN_ACTIONS = frozenset(
    [
        "password_save",
        "otp_save",
        "cert_password_save",
        "cookie_export",
        "session_export",
        "token_export",
        "storage_state_export",
        "cert_file_access",
        "npki_access",
        "captcha_bypass",
        "auto_payment",
        "auto_transfer",
        "auto_bid_submit",
        "auto_esign",
    ]
)


def _dummy_runner(action, domain, **kwargs):
    return {"ok": True, "action": action, "domain": domain}


# === 1. 정책 일관성 ===


class TestPolicyConsistency:
    def test_all_profiles_have_common_blocked(self):
        common = set(_COMMON_BLOCKED)
        for site_id, profile in _REGISTRY.items():
            blocked = set(profile.get("blocked_actions", []))
            missing = common - blocked
            assert not missing, f"{site_id}: 공통 blocked 누락 {missing}"

    def test_no_forbidden_action_delegated(self):
        for site_id, profile in _REGISTRY.items():
            delegated = set(profile.get("delegated_actions", []))
            found = delegated & _FORBIDDEN_ACTIONS
            assert not found, f"{site_id}: delegated에 금지 action {found}"

    def test_all_profiles_require_audit_log(self):
        for site_id, profile in _REGISTRY.items():
            assert profile.get("requires_audit_log") is True

    def test_no_server_browser_in_profiles(self):
        for site_id, profile in _REGISTRY.items():
            assert profile.get("server_browser_used") is not True

    def test_no_blocked_step_in_templates(self):
        for tid, tmpl in _TEMPLATES.items():
            steps = tmpl.get("steps", []) if isinstance(tmpl, dict) else []
            for step in steps:
                assert step["risk_level"] != GRADE_BLOCKED

    def test_no_forbidden_selector_in_packs(self):
        for site_id, pack in _PACKS.items():
            for key in _FORBIDDEN_SELECTOR_KEYS:
                assert key not in pack, f"{site_id}: 금지 selector {key}"

    def test_max_executions_limit(self):
        for site_id, profile in _REGISTRY.items():
            assert profile.get("max_default_executions", 1) <= 50


# === 2. safe result 불변 ===


class TestSafeResultInvariant:
    def _make_result(self, **kwargs):
        defaults = {
            "task_id": "t-inv",
            "site_id": "naver",
            "workflow_id": "readonly_site_explore",
            "status": STATUS_COMPLETED,
            "execution_used": 1,
            "actions_executed": [],
            "actions_pending_permission": [],
            "actions_user_direct_required": [],
            "blocked_actions": [],
            "safe_outputs": {},
            "audit_log_ids": [],
        }
        defaults.update(kwargs)
        return build_universal_result(**defaults)

    def test_safe_fields_always_false(self):
        result = self._make_result()
        for f in _SAFE_FIELDS:
            assert result[f] is False

    def test_validate_catches_true_sensitive(self):
        result = self._make_result()
        result["password_collected"] = True
        errors = validate_universal_result(result)
        assert errors


# === 3. 워크플로우 실행 ===


class TestWorkflowExecution:
    def test_government_readonly_safe(self):
        r = run_workflow("g2b_public", "government_readonly_status_check", runner_fn=_dummy_runner)
        for f in _SAFE_FIELDS:
            assert r.get(f) is False

    def test_financial_readonly_safe(self):
        r = run_workflow("generic_financial_site", "financial_readonly_statement_download", runner_fn=_dummy_runner)
        for f in _SAFE_FIELDS:
            assert r.get(f) is False

    def test_ecommerce_readonly_safe(self):
        r = run_workflow("generic_ecommerce_site", "ecommerce_order_status_readonly", runner_fn=_dummy_runner)
        for f in _SAFE_FIELDS:
            assert r.get(f) is False

    def test_blocked_action_returns_blocked_status(self):
        r = run_single_action("naver", "auto_bid_submit", domain="naver.com", runner_fn=_dummy_runner)
        assert r["status"] in ("BLOCKED", "STATUS_BLOCKED")

    def test_dry_run_no_sensitive_data(self):
        r = run_workflow("naver_blog", "blog_publish_with_permission", runner_fn=_dummy_runner, dry_run=True)
        for f in _SAFE_FIELDS:
            assert r.get(f) is False


# === 4. 플랫폼 규모 ===


class TestPlatformScale:
    def test_minimum_site_profiles(self):
        assert len(_REGISTRY) >= 13

    def test_minimum_templates(self):
        assert len(_TEMPLATES) >= 10

    def test_minimum_selector_packs(self):
        assert len(_PACKS) >= 4

    def test_minimum_capabilities(self):
        assert len(_CAPABILITY_GRADE) >= 17
