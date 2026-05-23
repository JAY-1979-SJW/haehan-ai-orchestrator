from pathlib import Path

from scripts import required_quality_gate as gate


ROOT = Path(__file__).resolve().parents[1]


def test_required_gate_has_no_forbidden_commands():
    offenders = [gate.command_text(command) for command in gate.COMMANDS if gate.command_is_forbidden(command)]

    assert offenders == []


def test_required_gate_includes_browser_runtime_policy_tests():
    rendered = "\n".join(gate.command_text(command) for command in gate.COMMANDS)

    assert "tests/test_local_agent_browser_runtime_operating_rules.py" in rendered
    assert "tests/test_local_agent_cdp_attach.py" in rendered
    assert "tests/test_dry_run_local_agent_cdp_attach.py" in rendered
    assert "tests/test_common_tool_runtime.py" in rendered
    assert "tests/test_required_quality_gate.py" in rendered
    assert "tests/test_module_boundaries.py" in rendered
    assert "tests/test_root_legacy_scripts_audit.py" in rendered
    assert "scripts/ops/dry_run_local_agent_cdp_attach.py" in rendered
    assert "scripts/ops/audit_common_tool_runtime.py" in rendered
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
