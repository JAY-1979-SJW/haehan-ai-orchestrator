from __future__ import annotations

from scripts.ops.audit_site_work_function_baseline import audit
from scripts.router import is_service_cmd


def test_site_work_function_baseline_audit_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_gabia_is_routed_as_site_work_command() -> None:
    assert is_service_cmd("gabia") is True


def test_site_work_service_commands_are_routed() -> None:
    for command in ("google", "gmail", "naver", "smartstore", "hiworks", "gabia", "youtube"):
        assert is_service_cmd(command) is True
