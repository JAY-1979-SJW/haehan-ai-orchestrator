from scripts import module_quality_gate as gate


def test_module_matrix_has_expected_modules():
    assert {
        "repo_guard",
        "portable_install",
        "desktop_auth_runtime",
        "live_agent",
        "playwright_ai",
        "release_preflight",
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


def test_command_matrix_blocks_build_deploy_and_push_commands():
    offenders = [
        step.name
        for step in gate.all_steps()
        if step.command and gate.command_is_forbidden(step.command)
    ]

    assert offenders == []


def test_repo_guard_includes_desktop_security_boundary():
    repo_guard = next(module for module in gate.MODULES if module.name == "repo_guard")

    assert any(step.check == "desktop_security_boundary" for step in repo_guard.steps)


def test_release_preflight_includes_admin_web_and_secret_scan():
    release = next(module for module in gate.MODULES if module.name == "release_preflight")
    checks = {step.check for step in release.steps}

    assert {
        "admin_web_typecheck",
        "admin_web_lint",
        "admin_web_audit",
        "active_source_secret_scan",
    }.issubset(checks)


def test_desktop_security_boundary_passes_current_runtime_sources():
    ok, message = gate.check_desktop_security_boundary()

    assert ok, message


def test_cad_boundary_imports_are_isolated_to_boundary_modules():
    allowed = {
        "desktop/cad_api_approval.py",
        "desktop/cad_bridge_allowlist.py",
    }
    offenders = []
    for path in (gate.ROOT / "desktop").glob("*.py"):
        rel = gate.normalize_path(str(path.relative_to(gate.ROOT)))
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "from local_agent.cad" in text or "import local_agent.cad" in text:
            offenders.append(rel)

    assert offenders == []


def test_tray_and_launcher_use_runtime_boundary_for_local_agent_imports():
    offenders = []
    for rel in ("desktop/tray_runtime.py", "desktop/main_launcher.py", "desktop/local_server.py"):
        text = (gate.ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if gate.imports_local_agent(text):
            offenders.append(rel)

    assert offenders == []


def test_python_compile_steps_use_no_cache_wrapper():
    compile_steps = [step for step in gate.all_steps() if step.name.endswith("_py_compile")]

    assert compile_steps
    assert all("scripts/py_compile_no_cache.py" in step.command for step in compile_steps)


def test_redact_masks_auth_and_secret_values():
    text = (
        "Authorization: Bearer admin-token\n"
        "OPENAI_API_KEY=sk-testsecretvalue12345\n"
        "device_token=plain-device-token"
    )

    redacted = gate.redact(text)

    assert "admin-token" not in redacted
    assert "sk-testsecretvalue12345" not in redacted
    assert "plain-device-token" not in redacted
    assert "<redacted>" in redacted


def test_active_source_secret_scan_passes_current_sources():
    ok, message = gate.check_active_source_secret_scan()

    assert ok, message


def test_find_staged_out_of_scope_uses_normalized_paths():
    staged = gate.find_staged_out_of_scope(
        [
            "scripts\\ops\\check_naver_mail.py",
            "local_agent/desktop_launcher.py",
        ]
    )

    assert staged == ["scripts/ops/check_naver_mail.py"]
