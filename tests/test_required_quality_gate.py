from pathlib import Path
import subprocess

from scripts import required_quality_gate as gate


ROOT = Path(__file__).resolve().parents[1]
TEST_PYCACHE = ROOT


def test_required_gate_has_no_forbidden_commands():
    offenders = [gate.command_text(command) for command in gate.COMMANDS if gate.command_is_forbidden(command)]

    assert offenders == []


def test_required_gate_includes_browser_runtime_policy_tests():
    rendered = "\n".join(gate.command_text(command) for command in gate.COMMANDS)

    assert "tests/test_local_agent_browser_runtime_operating_rules.py" in rendered
    assert "tests/test_local_agent_cdp_attach.py" in rendered
    assert "tests/test_dry_run_local_agent_cdp_attach.py" in rendered
    assert "tests/test_common_tool_runtime.py" in rendered
    assert "tests/test_common_tool_runtime_baseline_contract.py" in rendered
    assert "tests/test_common_engine_commercialization_baseline.py" in rendered
    assert "tests/test_local_agent_connection_recovery_baseline.py" in rendered
    assert "tests/test_desktop_auth_runtime_baseline_contract.py" in rendered
    assert "tests/test_portable_install_baseline_contract.py" in rendered
    assert "tests/test_release_preflight_baseline_contract.py" in rendered
    assert "tests/test_local_agent_e2e_flow_contract.py" in rendered
    assert "tests/test_app_baseline_contract.py" in rendered
    assert "tests/test_standard_workflow_contract.py" in rendered
    assert "tests/test_module_baseline_contract.py" in rendered
    assert "tests/test_backend_core_baseline_contract.py" in rendered
    assert "tests/test_local_agent_e2e_baseline_contract.py" in rendered
    assert "tests/test_approval_flow_baseline_contract.py" in rendered
    assert "tests/test_playwright_ai_baseline_contract.py" in rendered
    assert "tests/test_required_quality_gate.py" in rendered
    assert "tests/test_module_boundaries.py" in rendered
    assert "tests/test_root_legacy_scripts_audit.py" in rendered
    assert "scripts/ops/dry_run_local_agent_cdp_attach.py" in rendered
    assert "scripts/ops/audit_common_tool_runtime.py" in rendered
    assert "scripts/ops/audit_common_tool_runtime_baseline_contract.py" in rendered
    assert "scripts/ops/audit_common_engine_commercialization_baseline.py" in rendered
    assert "scripts/ops/audit_local_agent_connection_recovery_baseline.py" in rendered
    assert "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py" in rendered
    assert "scripts/ops/audit_portable_install_baseline_contract.py" in rendered
    assert "scripts/ops/audit_release_preflight_baseline_contract.py" in rendered
    assert "scripts/ops/audit_local_agent_e2e_flow_contract.py" in rendered
    assert "scripts/ops/audit_app_baseline_contract.py" in rendered
    assert "scripts/ops/audit_standard_workflow_contract.py" in rendered
    assert "scripts/ops/audit_module_baseline_contract.py" in rendered
    assert "scripts/ops/audit_backend_core_baseline_contract.py" in rendered
    assert "scripts/ops/audit_local_agent_e2e_baseline_contract.py" in rendered
    assert "scripts/ops/audit_approval_flow_baseline_contract.py" in rendered
    assert "scripts/ops/audit_playwright_ai_baseline_contract.py" in rendered
    assert "scripts/ops/audit_module_boundaries.py" in rendered
    assert "scripts/ops/audit_root_legacy_scripts.py" in rendered
    assert "scripts/module_quality_gate.py --module repo_guard" in rendered


def test_git_hooks_delegate_to_required_gate():
    pre_commit = (ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
    pre_push = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")

    assert "python scripts/required_quality_gate.py" in pre_commit
    assert "python scripts/required_quality_gate.py" in pre_push


def test_github_actions_workflow_removed():
    assert not (ROOT / ".github" / "workflows" / "safety-ci.yml").exists()


def test_required_gate_default_timeout_is_short():
    assert gate.DEFAULT_COMMAND_TIMEOUT_SECONDS == 30


def test_required_gate_splits_pytest_commands_into_small_groups():
    pytest_commands = [command for command in gate.COMMANDS if gate.command_is_pytest(command)]

    assert len(pytest_commands) >= 4
    for command in pytest_commands:
        test_files = [part for part in command if part.startswith("tests/")]
        assert 1 <= len(test_files) <= 13


def test_run_command_passes_timeout(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        captured["command"] = tuple(command)
        captured["stdin"] = kwargs["stdin"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_PYCACHE", str(TEST_PYCACHE))
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "--version"))

    assert result.ok is True
    assert captured["timeout"] == 7
    assert captured["command"] == (gate.sys.executable, "--version")
    assert captured["stdin"] == subprocess.DEVNULL


def test_repo_guard_gate_gets_extended_timeout(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["timeout"] = kwargs["timeout"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_TIMEOUT_SECONDS", "30")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "scripts/module_quality_gate.py", "--module", "repo_guard"))

    assert result.ok is True
    assert captured["timeout"] == 120


def test_run_command_fails_fast_on_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial output")

    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_PYCACHE", str(TEST_PYCACHE))
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "--version"))

    assert result.ok is False
    assert result.detail == "timeout_after=3s"


def test_run_command_avoids_pycache_prefix_for_pytest(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "C:/tmp/problematic-pycache")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "-m", "pytest", "tests/test_required_quality_gate.py", "-q"))

    assert result.ok is True
    assert "PYTHONPYCACHEPREFIX" not in captured["env"]
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert captured["stdout"] is None
    assert captured["stderr"] is None
