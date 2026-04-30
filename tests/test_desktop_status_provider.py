"""DESK-3 status provider + Task Scheduler script tests.

Covers:
- LocalStatusProvider module readiness checks
- Token non-disclosure in status output
- Task Scheduler script: logon trigger, no secrets
- Local logs path (never remote)
- Admin mock UI URL (localhost only)
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from desktop.status_provider import (
    LocalStatusProvider,
    ServiceStatus,
    ApprovalStoreStatus,
    _FORBIDDEN_STATUS_KEYS,
    ADMIN_MOCK_UI_URL,
)

TASK_SCHEDULER_SCRIPT = (
    Path(__file__).parent.parent / "scripts" / "setup_task_scheduler.ps1"
)


# ---------------------------------------------------------------------------
# Status Provider — module readiness
# ---------------------------------------------------------------------------

class TestStatusProviderModuleReadiness(unittest.TestCase):
    def setUp(self):
        self.provider = LocalStatusProvider(log_dir=Path("logs"))

    def test_status_provider_reports_approval_store_ready(self):
        """Approval store module should be importable (was created in BROWSER-4F)."""
        ready = self.provider.is_approval_store_ready()
        # Module exists in repo — should be True
        self.assertTrue(ready, "browser_approval_persistent_store should be importable")

    def test_status_provider_reports_websocket_schema_ready(self):
        """WebSocket schema module should be importable (was created in BROWSER-4G)."""
        ready = self.provider.is_websocket_schema_ready()
        self.assertTrue(ready, "browser_websocket_schema should be importable")

    def test_status_provider_reports_browser_task_handler_ready(self):
        """Browser task handler module should be importable (was created in BROWSER-4C)."""
        ready = self.provider.is_browser_task_handler_ready()
        self.assertTrue(ready, "browser_task_handler should be importable")

    def test_status_provider_missing_module_returns_false(self):
        """Non-existent module correctly returns False."""
        result = importlib.util.find_spec("nonexistent_module_xyz_desk3")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Status Provider — token non-disclosure
# ---------------------------------------------------------------------------

class TestStatusProviderTokenSafety(unittest.TestCase):
    def setUp(self):
        self.provider = LocalStatusProvider(log_dir=Path("logs"))

    def test_status_provider_does_not_expose_tokens(self):
        """ServiceStatus must never contain approval_token values."""
        status = self.provider.get_service_status(runner_state="stopped")
        status_dict = status.__dict__
        for key, value in status_dict.items():
            key_lower = key.lower()
            self.assertNotIn(key_lower, _FORBIDDEN_STATUS_KEYS,
                             f"ServiceStatus field '{key}' is a forbidden token field")
            if isinstance(value, str):
                for forbidden in _FORBIDDEN_STATUS_KEYS:
                    self.assertNotIn(forbidden, value.lower(),
                                     f"ServiceStatus.{key} contains forbidden key '{forbidden}'")

    def test_approval_store_status_does_not_expose_tokens(self):
        """ApprovalStoreStatus must never have token fields."""
        store_status = ApprovalStoreStatus(ready=True, pending_count=3)
        for attr in vars(store_status):
            self.assertNotIn(attr.lower(), _FORBIDDEN_STATUS_KEYS,
                             f"ApprovalStoreStatus field '{attr}' is forbidden")

    def test_service_status_fields_are_all_safe(self):
        """All fields in ServiceStatus are safe (no token/secret names)."""
        status = ServiceStatus(state="running")
        for field_name in vars(status):
            self.assertNotIn(field_name.lower(), _FORBIDDEN_STATUS_KEYS,
                             f"ServiceStatus has forbidden field: {field_name}")

    def test_error_summary_strips_sensitive_lines(self):
        """Last error summary must strip lines containing forbidden keys."""
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "orchestrator.log"
            log_path.write_text(
                "INFO normal log line\n"
                "ERROR something failed with approval_token=abc123\n"
                "ERROR normal error message\n",
                encoding="utf-8"
            )
            provider = LocalStatusProvider(log_dir=Path(tmpdir))
            summary = provider.get_last_error_summary()
            if summary:
                self.assertNotIn("approval_token", summary.lower())
                self.assertNotIn("abc123", summary)


# ---------------------------------------------------------------------------
# Status Provider — admin UI and logs
# ---------------------------------------------------------------------------

class TestStatusProviderURLs(unittest.TestCase):
    def test_admin_mock_ui_url_is_localhost(self):
        """Admin mock UI URL must always be localhost — never production."""
        provider = LocalStatusProvider()
        url = provider.get_admin_mock_ui_url()
        self.assertIn("localhost", url)
        self.assertNotIn("haehan.ai", url)
        self.assertNotIn("production", url.lower())

    def test_admin_mock_ui_url_points_to_browser_approvals(self):
        """Admin mock UI URL must include the browser-approvals route."""
        provider = LocalStatusProvider()
        url = provider.get_admin_mock_ui_url()
        self.assertIn("browser-approvals", url)

    def test_local_logs_path_is_not_remote(self):
        """Local logs path must be a filesystem path, not a URL."""
        provider = LocalStatusProvider(log_dir=Path("logs"))
        logs_path = provider.get_local_logs_path()
        path_str = str(logs_path)
        self.assertNotIn("http", path_str.lower())
        self.assertNotIn("://", path_str)

    def test_default_admin_ui_url_constant(self):
        """ADMIN_MOCK_UI_URL constant must be local."""
        self.assertIn("localhost", ADMIN_MOCK_UI_URL)
        self.assertIn("browser-approvals", ADMIN_MOCK_UI_URL)


# ---------------------------------------------------------------------------
# Status Provider — get_service_status aggregation
# ---------------------------------------------------------------------------

class TestServiceStatusAggregation(unittest.TestCase):
    def test_running_state_with_ready_handler(self):
        provider = LocalStatusProvider(log_dir=Path("logs"))
        with patch.object(provider, "is_browser_task_handler_ready", return_value=True):
            with patch.object(provider, "get_approval_store_status",
                              return_value=ApprovalStoreStatus(ready=True, pending_count=5)):
                status = provider.get_service_status(runner_state="running")
        self.assertEqual(status.state, "running")
        self.assertEqual(status.pending_task_count, 5)

    def test_running_state_without_handler_is_degraded(self):
        provider = LocalStatusProvider(log_dir=Path("logs"))
        with patch.object(provider, "is_browser_task_handler_ready", return_value=False):
            with patch.object(provider, "get_approval_store_status",
                              return_value=ApprovalStoreStatus()):
                status = provider.get_service_status(runner_state="running")
        self.assertEqual(status.state, "degraded")

    def test_stopped_state(self):
        provider = LocalStatusProvider(log_dir=Path("logs"))
        with patch.object(provider, "get_approval_store_status",
                          return_value=ApprovalStoreStatus()):
            status = provider.get_service_status(runner_state="stopped")
        self.assertEqual(status.state, "stopped")

    def test_error_state(self):
        provider = LocalStatusProvider(log_dir=Path("logs"))
        with patch.object(provider, "get_approval_store_status",
                          return_value=ApprovalStoreStatus()):
            status = provider.get_service_status(runner_state="error")
        self.assertEqual(status.state, "error")


# ---------------------------------------------------------------------------
# Task Scheduler script validation
# ---------------------------------------------------------------------------

class TestTaskSchedulerScript(unittest.TestCase):
    def setUp(self):
        self.script_path = TASK_SCHEDULER_SCRIPT
        if not self.script_path.exists():
            self.skipTest(f"Script not found: {self.script_path}")
        self.content = self.script_path.read_text(encoding="utf-8")
        self.content_lower = self.content.lower()

    def test_task_scheduler_setup_script_exists(self):
        self.assertTrue(self.script_path.exists())

    def test_task_scheduler_setup_script_contains_logon_trigger(self):
        """Script must register an AtLogon trigger."""
        self.assertIn("atlogon", self.content_lower,
                      "Script must include AtLogon trigger")

    def test_task_scheduler_setup_script_contains_restart_policy(self):
        """Script must include failure restart policy."""
        has_restart = (
            "restartcount" in self.content_lower or
            "restartinterval" in self.content_lower or
            "restart" in self.content_lower
        )
        self.assertTrue(has_restart, "Script must specify restart-on-failure policy")

    def test_task_scheduler_setup_script_does_not_contain_secrets(self):
        """Script must not include any secret or token values."""
        forbidden_patterns = [
            "approval_token", "final_approval_token", "token_hash",
            "device_token", "authorization", "password", "otp",
            "cookie", "session_token", "secret",
        ]
        for pattern in forbidden_patterns:
            self.assertNotIn(pattern, self.content_lower,
                             f"Script contains forbidden secret pattern: '{pattern}'")

    def test_task_scheduler_setup_script_does_not_contain_production_urls(self):
        """Script must not include production server URLs."""
        for production_indicator in ["haehan.ai", "amazonaws", "heroku", "vercel"]:
            self.assertNotIn(production_indicator, self.content_lower,
                             f"Script contains production URL: '{production_indicator}'")

    def test_task_scheduler_setup_script_has_uninstall_option(self):
        """Script should support uninstall/removal of the task."""
        self.assertIn("uninstall", self.content_lower)

    def test_task_scheduler_setup_script_uses_register_scheduled_task(self):
        """Script must use PowerShell Task Scheduler cmdlets."""
        self.assertIn("register-scheduledtask", self.content_lower)

    def test_task_scheduler_setup_script_limited_run_level(self):
        """Task must run with limited (non-elevated) permissions."""
        self.assertIn("limited", self.content_lower)


# ---------------------------------------------------------------------------
# Forbidden keys coverage
# ---------------------------------------------------------------------------

class TestForbiddenKeysCoverage(unittest.TestCase):
    def test_forbidden_keys_covers_token_fields(self):
        required = {
            "approval_token", "final_approval_token", "token_hash",
        }
        missing = required - _FORBIDDEN_STATUS_KEYS
        self.assertEqual(missing, set(), f"Token fields missing from forbidden set: {missing}")

    def test_forbidden_keys_covers_credential_fields(self):
        required = {"password", "otp", "cookie", "session", "authorization"}
        missing = required - _FORBIDDEN_STATUS_KEYS
        self.assertEqual(missing, set(), f"Credential fields missing: {missing}")

    def test_forbidden_keys_covers_storage_fields(self):
        required = {"localstorage", "sessionstorage"}
        missing = required - _FORBIDDEN_STATUS_KEYS
        self.assertEqual(missing, set(), f"Storage fields missing: {missing}")


if __name__ == "__main__":
    unittest.main()
