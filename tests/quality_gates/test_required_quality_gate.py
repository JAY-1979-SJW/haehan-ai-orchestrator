import subprocess
from pathlib import Path

from tools.quality import required_quality_gate as gate

ROOT = Path(__file__).resolve().parents[2]
TEST_PYCACHE = ROOT


def test_required_gate_has_no_forbidden_commands():
    offenders = [gate.command_text(command) for command in gate.COMMANDS if gate.command_is_forbidden(command)]

    assert gate.COMMANDS, "gate.COMMANDS 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert offenders == []


def test_required_gate_includes_browser_runtime_policy_tests():
    rendered = "\n".join(gate.command_text(command) for command in gate.COMMANDS)

    assert "tests/test_local_agent_browser_runtime_operating_rules.py" in rendered
    assert "tests/test_local_agent_cdp_attach.py" in rendered
    assert "tests/test_dry_run_local_agent_cdp_attach.py" in rendered
    assert "tests/test_common_tool_runtime.py" in rendered
    assert "tests/app_contracts/test_common_tool_runtime_baseline_contract.py" in rendered
    assert "tests/app_contracts/test_common_engine_commercialization_baseline.py" in rendered
    assert "tests/test_local_agent_connection_recovery_baseline.py" in rendered
    assert "tests/desktop/test_desktop_auth_runtime_baseline_contract.py" in rendered
    assert "tests/test_local_agent_e2e_flow_contract.py" in rendered
    assert "tests/app_contracts/test_app_baseline_contract.py" in rendered
    assert "tests/app_contracts/test_standard_workflow_contract.py" in rendered
    assert "tests/app_contracts/test_module_baseline_contract.py" in rendered
    assert "tests/app_contracts/test_backend_core_baseline_contract.py" in rendered
    assert "tests/test_local_agent_e2e_baseline_contract.py" in rendered
    assert "tests/approval/test_approval_flow_baseline_contract.py" in rendered
    assert "tests/app_contracts/test_playwright_ai_baseline_contract.py" in rendered
    assert "tests/quality_gates/test_required_quality_gate.py" in rendered
    assert "tests/quality_gates/test_module_boundaries.py" in rendered
    assert "tests/quality_gates/test_root_legacy_scripts_audit.py" in rendered
    assert "tests/google/test_google_subdomain_logic.py" in rendered
    assert "tests/google/test_google_tab_logic.py" in rendered
    assert "tests/google/test_google_ads_signup.py" in rendered
    assert "tests/google/test_google_live_surface_explorer.py" in rendered
    assert "tests/google/test_google_cloud_live_console_explorer.py" in rendered
    assert "tests/google/test_google_ai_usage_labels.py" in rendered
    assert "tests/google/test_google_android_app_dev.py" in rendered
    assert "tests/google/test_google_domain_taxonomy.py" in rendered
    assert "tests/google/test_google_managed_console.py" in rendered
    assert "tests/google/test_google_work_mode_gate.py" in rendered
    assert "tests/google/test_google_workspace_basic.py" in rendered
    assert "tests/google/test_google_home_login_gate.py" in rendered
    assert "tests/google/test_google_youtube_upload.py" in rendered
    assert "tests/google/test_google_youtube_search.py" in rendered
    assert "tests/google/test_google_precision_report.py" in rendered
    assert "tests/site_engine/test_site_sso_subdomain_runtime.py" in rendered
    assert "tests/youtube/test_youtube_oauth.py" in rendered
    assert "tests/youtube/test_youtube_research.py" in rendered
    assert "tests/quality_gates/test_ai_agent_app_structure_design_baseline.py" in rendered
    assert "tests/quality_gates/test_ai_agent_ui_structure_blueprint.py" in rendered
    assert "tests/server_core/test_mcp_gateway_baseline.py" in rendered
    assert "tests/quality_gates/test_ai_work_session_gate.py" in rendered
    assert "tools/verify/dry_run_local_agent_cdp_attach.py" in rendered
    assert "tools/audits/agent/audit_common_tool_runtime.py" in rendered
    assert "tools/audits/agent/audit_common_tool_runtime_baseline_contract.py" in rendered
    assert "tools/audits/app/audit_common_engine_commercialization_baseline.py" in rendered
    assert "tools/audits/agent/audit_local_agent_connection_recovery_baseline.py" in rendered
    assert "tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py" in rendered
    assert "tools/audits/agent/audit_local_agent_e2e_flow_contract.py" in rendered
    assert "tools/audits/app/audit_app_baseline_contract.py" in rendered
    assert "tools/audits/app/audit_standard_workflow_contract.py" in rendered
    assert "tools/audits/app/audit_module_baseline_contract.py" in rendered
    assert "tools/audits/backend/audit_backend_core_baseline_contract.py" in rendered
    assert "tools/audits/agent/audit_local_agent_e2e_baseline_contract.py" in rendered
    assert "tools/audits/app/audit_approval_flow_baseline_contract.py" in rendered
    assert "tools/audits/agent/audit_playwright_ai_baseline_contract.py" in rendered
    assert "tools/audits/app/audit_module_boundaries.py" in rendered
    assert "tools/repo_gates/audit_root_legacy_scripts.py" in rendered
    assert "tools/audits/google/audit_google_home_login_gate.py" in rendered
    assert "tools/audits/google/audit_google_automation_baseline_contract.py" in rendered
    assert "tools/audits/app/audit_site_sso_subdomain_runtime_baseline.py" in rendered
    assert "tools/audits/app/audit_ai_agent_app_structure_design_baseline.py" in rendered
    assert "tools/audits/app/audit_ai_agent_ui_structure_blueprint.py" in rendered
    assert "tools/audits/agent/audit_mcp_gateway_baseline.py" in rendered
    assert "scripts/common/ai_work_session.py" in rendered
    assert "tools/audits/app/audit_ai_work_session_gate.py" in rendered
    assert "scripts/google/ads_signup.py" in rendered
    assert "scripts/google/live_surface_explorer.py" in rendered
    assert "scripts/google/cloud/live_console_explorer.py" in rendered
    assert "scripts/google/ai_usage_labels.py" in rendered
    assert "scripts/google/android_app_dev_labels.py" in rendered
    assert "scripts/google/android_app_dev_report.py" in rendered
    assert "scripts/google/common/domain_taxonomy.py" in rendered
    assert "scripts/google/managed_console.py" in rendered
    assert "scripts/google/precision_report.py" in rendered
    assert "scripts/google/common/subdomain_logic.py" in rendered
    assert "scripts/google/common/tab_logic.py" in rendered
    assert "scripts/common/gates/work_mode_gate.py" in rendered
    assert "scripts/google/workspace_basic.py" in rendered
    assert "scripts/google/youtube/search.py" in rendered
    assert "scripts/google/common/youtube_upload.py" in rendered
    assert "scripts/youtube/oauth.py" in rendered
    assert "scripts/youtube/research.py" in rendered
    assert "scripts/youtube/router.py" in rendered
    assert "tools/quality/module_quality_gate.py --module repo_guard" in rendered


def test_git_hooks_delegate_to_required_gate():
    # 현행 위임 구조(2026-05-31 f6a169ae 이후 훅 재작성, 설치기 tools/hooks/install_git_hooks.py):
    #   pre-commit(체크리스트 래퍼) -> pre-commit.orig(ruff + ruff_new_only_gate)
    #   pre-push -> tools/hooks/ai_code_review_gate.py
    # required_quality_gate.py 를 직접 호출하던 구 구조는 더 이상 훅에 없다.
    pre_commit = (ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
    pre_commit_orig = (ROOT / ".githooks" / "pre-commit.orig").read_text(encoding="utf-8")
    pre_push = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")

    assert "pre-commit.orig" in pre_commit
    assert "ruff_new_only_gate.py" in pre_commit_orig
    assert "ai_code_review_gate.py" in pre_push


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

    result = gate.run_command((gate.sys.executable, "tools/quality/module_quality_gate.py", "--module", "repo_guard"))

    assert result.ok is True
    assert captured["timeout"] == 240


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
        captured["command"] = tuple(command)
        captured["env"] = kwargs["env"]
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "C:/tmp/problematic-pycache")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "-m", "pytest", "tests/quality_gates/test_required_quality_gate.py", "-q"))

    assert result.ok is True
    assert captured["command"][:4] == (
        gate.sys.executable,
        "-m",
        "pytest",
        "tests/quality_gates/test_required_quality_gate.py",
    )
    assert captured["command"][4] == "-q"
    assert len(captured["command"]) == 5
    assert "PYTHONPYCACHEPREFIX" not in captured["env"]
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "required_gate_temp" in captured["env"]["TEMP"]
    assert captured["env"]["TEMP"] == captured["env"]["TMP"]
    assert captured["env"]["TEMP"] == captured["env"]["TMPDIR"]
    assert captured["stdout"] is None
    assert captured["stderr"] is None


def test_youtube_research_pytest_uses_workspace_temp(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = tuple(command)
        captured["env"] = kwargs["env"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate.run_command((gate.sys.executable, "-m", "pytest", "tests/youtube/test_youtube_research.py", "-q"))

    assert result.ok is True
    assert not any(part.startswith("--basetemp=") for part in captured["command"])
    assert "required_gate_temp" in captured["env"]["TEMP"]


def test_google_youtube_search_pytest_uses_workspace_temp(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = tuple(command)
        captured["env"] = kwargs["env"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    command = next(
        command
        for command in gate.COMMANDS
        if "tests/google/test_google_youtube_search.py" in command and gate.command_is_pytest(command)
    )

    assert gate.command_needs_isolated_pytest_temp(command) is True
    result = gate.run_command(command)

    assert result.ok is True
    assert not any(part.startswith("--basetemp=") for part in captured["command"])
    assert "required_gate_temp" in captured["env"]["TEMP"]
    assert "PYTHONPYCACHEPREFIX" not in captured["env"]


def test_ai_work_session_gate_pytest_uses_workspace_temp(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = tuple(command)
        captured["env"] = kwargs["env"]

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    command = next(
        command
        for command in gate.COMMANDS
        if "tests/quality_gates/test_ai_work_session_gate.py" in command and gate.command_is_pytest(command)
    )

    assert gate.command_needs_isolated_pytest_temp(command) is True
    result = gate.run_command(command)

    assert result.ok is True
    assert not any(part.startswith("--basetemp=") for part in captured["command"])
    assert "required_gate_temp" in captured["env"]["TEMP"]
    assert "PYTHONPYCACHEPREFIX" not in captured["env"]


def test_pytest_temp_gets_isolated_runtime_dir(monkeypatch):
    base = gate.ROOT / ".pytest-tmp" / "required_gate_test_temp"
    monkeypatch.setenv("HAEHAN_REQUIRED_GATE_TEMP", str(base))
    env = {}

    temp_root = gate.isolated_pytest_temp(env)

    assert not temp_root.exists()
    assert temp_root.parent == gate.usable_temp_base("required_gate_temp", "HAEHAN_REQUIRED_GATE_TEMP")
    assert base.exists()
