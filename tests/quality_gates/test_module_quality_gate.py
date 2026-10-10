from tools.quality import module_quality_gate as gate


def test_module_matrix_has_expected_modules():
    assert {
        "repo_guard",
        "desktop_auth_runtime",
        "backend_core",
        "common_engine_commercialization",
        "local_agent_connection_recovery",
        "local_agent_e2e",
        "live_agent",
        "playwright_ai",
        "release_preflight",
        "release_runtime",
    }.issubset(set(gate.module_names()))


def test_default_selection_excludes_live_steps():
    modules = gate.selected_modules(["all"])
    selected = list(gate.iter_selected_steps(modules, include_live=False))

    assert selected
    assert all(not step.live for _, step in selected)


def test_include_live_selects_live_steps():
    modules = gate.selected_modules(["desktop_auth_runtime", "live_agent"])
    selected = list(gate.iter_selected_steps(modules, include_live=True))

    assert any(step.live for _, step in selected)


def test_desktop_auth_runtime_includes_baseline_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "desktop_auth_runtime")

    assert any(step.check == "desktop_auth_runtime_baseline_contract" for step in module.steps)


def test_command_matrix_blocks_build_deploy_and_push_commands():
    assert len(list(gate.all_steps())) > 0, "all_steps() 가 비어 있음 — 아래 assert 가 공허하게 통과한다"
    offenders = [step.name for step in gate.all_steps() if step.command and gate.command_is_forbidden(step.command)]

    assert offenders == []


def test_repo_guard_includes_desktop_security_boundary():
    repo_guard = next(module for module in gate.MODULES if module.name == "repo_guard")

    assert any(step.check == "local_agent_browser_runtime_rules" for step in repo_guard.steps)
    assert any(step.check == "common_tool_runtime_baseline_contract" for step in repo_guard.steps)
    assert any(step.check == "common_engine_commercialization_baseline" for step in repo_guard.steps)
    assert any(step.check == "local_agent_connection_recovery_baseline" for step in repo_guard.steps)
    assert any(step.check == "common_tool_runtime_contract" for step in repo_guard.steps)
    assert any(step.check == "app_baseline_contract" for step in repo_guard.steps)
    assert any(step.check == "standard_workflow_contract" for step in repo_guard.steps)
    assert any(step.check == "module_baseline_contract" for step in repo_guard.steps)
    assert any(step.check == "required_local_gate_wiring" for step in repo_guard.steps)
    assert any(step.check == "module_boundary_contract" for step in repo_guard.steps)
    assert any(step.check == "root_legacy_script_contract" for step in repo_guard.steps)
    assert any(step.check == "google_domain_module_boundaries" for step in repo_guard.steps)


def test_release_preflight_includes_admin_web_and_secret_scan():
    release = next(module for module in gate.MODULES if module.name == "release_preflight")
    checks = {step.check for step in release.steps}

    assert {
        "admin_web_typecheck",
        "admin_web_lint",
        "admin_web_audit",
        "local_agent_browser_runtime_rules",
        "active_source_secret_scan",
    }.issubset(checks)


def test_backend_core_includes_runtime_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "backend_core")

    assert any(step.check == "backend_core_baseline_contract" for step in module.steps)
    assert any(step.check == "approval_flow_baseline_contract" for step in module.steps)
    assert any(step.name == "backend_core_py_compile" for step in module.steps)
    assert any(step.check == "backend_runtime_contract" for step in module.steps)
    assert any(step.name == "backend_core_pytest" for step in module.steps)


def test_local_agent_e2e_module_includes_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "local_agent_e2e")

    assert any(step.check == "local_agent_e2e_baseline_contract" for step in module.steps)
    assert any(step.name == "local_agent_e2e_py_compile" for step in module.steps)
    assert any(any("audit_local_agent_e2e_flow_contract.py" in part for part in step.command) for step in module.steps)
    assert any(step.name == "local_agent_e2e_pytest" for step in module.steps)


def test_release_runtime_gate_is_live_only():
    module = next(module for module in gate.MODULES if module.name == "release_runtime")

    assert module.steps
    assert all(step.live for step in module.steps)
    assert any("verify_release_runtime_gate.py" in step.command for step in module.steps)


def test_playwright_ai_includes_baseline_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "playwright_ai")

    assert any(step.check == "playwright_ai_baseline_contract" for step in module.steps)


def test_python_compile_steps_use_no_cache_wrapper():
    compile_steps = [step for step in gate.all_steps() if step.name.endswith("_py_compile")]

    assert compile_steps
    assert all("tools/quality/py_compile_no_cache.py" in step.command for step in compile_steps)


def test_redact_masks_auth_and_secret_values():
    text = "Authorization: Bearer admin-token\nOPENAI_API_KEY=sk-testsecretvalue12345\ndevice_token=plain-device-token"

    redacted = gate.redact(text)

    assert "admin-token" not in redacted
    assert "sk-testsecretvalue12345" not in redacted
    assert "plain-device-token" not in redacted
    assert "<redacted>" in redacted


def test_active_source_secret_scan_passes_current_sources():
    ok, message = gate.check_active_source_secret_scan()

    assert ok, message


def test_local_agent_browser_runtime_rules_pass_current_sources():
    ok, message = gate.check_local_agent_browser_runtime_rules()

    assert ok, message


def test_local_agent_browser_runtime_rules_registered_in_checks():
    assert "local_agent_browser_runtime_rules" in gate.CHECKS


def test_common_tool_runtime_contract_passes_current_sources():
    ok, message = gate.check_common_tool_runtime_contract()

    assert ok, message


def test_common_tool_runtime_contract_registered_in_checks():
    assert "common_tool_runtime_contract" in gate.CHECKS


def test_app_baseline_contract_passes_current_sources():
    ok, message = gate.check_app_baseline_contract()

    assert ok, message


def test_app_baseline_contract_registered_in_checks():
    assert "app_baseline_contract" in gate.CHECKS


def test_standard_workflow_contract_passes_current_sources():
    ok, message = gate.check_standard_workflow_contract()

    assert ok, message


def test_standard_workflow_contract_registered_in_checks():
    assert "standard_workflow_contract" in gate.CHECKS


def test_module_baseline_contract_passes_current_sources():
    ok, message = gate.check_module_baseline_contract()

    assert ok, message


def test_module_baseline_contract_registered_in_checks():
    assert "module_baseline_contract" in gate.CHECKS


def test_backend_core_baseline_contract_passes_current_sources():
    ok, message = gate.check_backend_core_baseline_contract()

    assert ok, message


def test_backend_core_baseline_contract_registered_in_checks():
    assert "backend_core_baseline_contract" in gate.CHECKS


def test_local_agent_e2e_baseline_contract_passes_current_sources():
    ok, message = gate.check_local_agent_e2e_baseline_contract()

    assert ok, message


def test_local_agent_e2e_baseline_contract_registered_in_checks():
    assert "local_agent_e2e_baseline_contract" in gate.CHECKS


def test_approval_flow_baseline_contract_passes_current_sources():
    ok, message = gate.check_approval_flow_baseline_contract()

    assert ok, message


def test_approval_flow_baseline_contract_registered_in_checks():
    assert "approval_flow_baseline_contract" in gate.CHECKS


def test_playwright_ai_baseline_contract_passes_current_sources():
    ok, message = gate.check_playwright_ai_baseline_contract()

    assert ok, message


def test_playwright_ai_baseline_contract_registered_in_checks():
    assert "playwright_ai_baseline_contract" in gate.CHECKS


def test_common_tool_runtime_baseline_contract_passes_current_sources():
    ok, message = gate.check_common_tool_runtime_baseline_contract()

    assert ok, message


def test_common_tool_runtime_baseline_contract_registered_in_checks():
    assert "common_tool_runtime_baseline_contract" in gate.CHECKS


def test_common_engine_commercialization_module_includes_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "common_engine_commercialization")

    assert any(step.check == "common_engine_commercialization_baseline" for step in module.steps)
    assert any(step.name == "common_engine_commercialization_py_compile" for step in module.steps)
    assert any(step.name == "common_engine_commercialization_pytest" for step in module.steps)


def test_common_engine_commercialization_baseline_passes_current_sources():
    ok, message = gate.check_common_engine_commercialization_baseline()

    assert ok, message


def test_common_engine_commercialization_baseline_registered_in_checks():
    assert "common_engine_commercialization_baseline" in gate.CHECKS


def test_local_agent_connection_recovery_module_includes_contract_gate():
    module = next(module for module in gate.MODULES if module.name == "local_agent_connection_recovery")

    assert any(step.check == "local_agent_connection_recovery_baseline" for step in module.steps)
    assert any(step.name == "local_agent_connection_recovery_py_compile" for step in module.steps)
    assert any(step.name == "local_agent_connection_recovery_pytest" for step in module.steps)


def test_local_agent_connection_recovery_baseline_passes_current_sources():
    ok, message = gate.check_local_agent_connection_recovery_baseline()

    assert ok, message


def test_local_agent_connection_recovery_baseline_registered_in_checks():
    assert "local_agent_connection_recovery_baseline" in gate.CHECKS


def test_desktop_auth_runtime_baseline_contract_passes_current_sources():
    ok, message = gate.check_desktop_auth_runtime_baseline_contract()

    assert ok, message


def test_desktop_auth_runtime_baseline_contract_registered_in_checks():
    assert "desktop_auth_runtime_baseline_contract" in gate.CHECKS


def test_backend_runtime_contract_passes_current_sources():
    ok, message = gate.check_backend_runtime_contract()

    assert ok, message


def test_backend_runtime_contract_registered_in_checks():
    assert "backend_runtime_contract" in gate.CHECKS


def test_google_domain_module_boundaries_pass_current_sources():
    ok, message = gate.check_google_domain_module_boundaries()

    assert ok, message


def test_google_domain_module_boundaries_registered_in_checks():
    assert "google_domain_module_boundaries" in gate.CHECKS


def test_required_local_gate_wiring_passes_current_sources():
    ok, message = gate.check_required_local_gate_wiring()

    assert ok, message


def test_required_local_gate_wiring_registered_in_checks():
    assert "required_local_gate_wiring" in gate.CHECKS


def test_module_boundary_contract_passes_current_sources():
    ok, message = gate.check_module_boundary_contract()

    assert ok, message


def test_module_boundary_contract_registered_in_checks():
    assert "module_boundary_contract" in gate.CHECKS


def test_root_legacy_script_contract_passes_current_sources():
    ok, message = gate.check_root_legacy_script_contract()

    assert ok, message


def test_root_legacy_script_contract_registered_in_checks():
    assert "root_legacy_script_contract" in gate.CHECKS


def test_admin_web_audit_counts_vulnerability_entries_before_metadata():
    report = {
        "vulnerabilities": {},
        "metadata": {"vulnerabilities": {"high": 1, "critical": 0, "total": 1}},
    }

    assert gate.audit_vulnerability_counts(report) == (0, 0, 0)


def test_admin_web_audit_counts_high_and_critical_entries():
    report = {
        "vulnerabilities": {
            "pkg-a": {"severity": "high"},
            "pkg-b": {"severity": "critical"},
            "pkg-c": {"severity": "moderate"},
        }
    }

    assert gate.audit_vulnerability_counts(report) == (1, 1, 3)
    assert gate.audit_high_critical_names(report) == ["pkg-a", "pkg-b"]


def test_admin_web_audit_uses_lockfile_only(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)

        class Result:
            stdout = '{"vulnerabilities": {}, "metadata": {"vulnerabilities": {"total": 0}}}'

        return Result()

    monkeypatch.setattr(gate.shutil, "which", lambda _: "npm.cmd")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    ok, message = gate.check_admin_web_audit()

    assert ok, message
    assert calls
    assert calls[0][-4:] == ["audit", "--omit=dev", "--json", "--package-lock-only"]


def test_admin_web_audit_accepts_clean_fallback_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)

        class Result:
            stdout = (
                '{"vulnerabilities": {"next": {"severity": "high"}}, '
                '"metadata": {"vulnerabilities": {"high": 1, "critical": 0, "total": 1}}}'
            )

        class CleanResult:
            stdout = '{"vulnerabilities": {}, "metadata": {"vulnerabilities": {"total": 0}}}'

        return Result() if len(calls) == 1 else CleanResult()

    monkeypatch.setattr(gate.shutil, "which", lambda name: "npm.cmd" if name == "npm.cmd" else "npm")
    monkeypatch.setattr(gate.os, "name", "nt")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    ok, message = gate.check_admin_web_audit()

    assert ok, message
    assert calls


def test_admin_web_audit_next_floor_passes_current_lockfile():
    assert gate.next_lockfile_meets_security_floor()


def test_find_staged_out_of_scope_uses_normalized_paths():
    staged = gate.find_staged_out_of_scope(
        [
            "scripts\\ops\\check_naver_mail.py",
            "local_agent/desktop_launcher.py",
        ]
    )

    assert staged == ["scripts/ops/check_naver_mail.py"]
