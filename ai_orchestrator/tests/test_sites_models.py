"""SiteTask / SiteExecutionResult / SiteHealthStatus 스키마 기본 테스트."""
from __future__ import annotations

from ai_orchestrator.sites.models import (
    SiteExecutionResult,
    SiteHealthStatus,
    SiteTask,
)


def test_site_task_defaults_and_dict():
    t = SiteTask(task_id="T1", target_site="dummy", action="ping")
    d = t.to_dict()
    assert d["task_id"] == "T1"
    assert d["target_site"] == "dummy"
    assert d["action"] == "ping"
    assert d["execution_mode"] == "dry_run"
    assert d["requires_approval"] is False
    assert d["risk_level"] == "low"
    assert isinstance(d["params"], dict) and d["params"] == {}
    assert d["created_at"]  # 비어있지 않아야


def test_site_execution_result_schema():
    r = SiteExecutionResult(
        task_id="T1",
        target_site="dummy",
        action="ping",
        status="dry_run",
        summary="ok",
    )
    d = r.to_dict()
    for key in (
        "task_id", "target_site", "action", "status",
        "started_at", "finished_at", "summary",
        "artifacts", "screenshots", "error_code", "error_message",
        "health_snapshot", "duration_ms",
    ):
        assert key in d


def test_site_health_status_defaults():
    h = SiteHealthStatus(site_name="dummy", connector_name="DummyConnector")
    d = h.to_dict()
    assert d["state"] == "unconfigured"
    assert d["credentials_present"] is False
    assert d["session_state_present"] is False
    assert d["login_check_status"] == "not_checked"
