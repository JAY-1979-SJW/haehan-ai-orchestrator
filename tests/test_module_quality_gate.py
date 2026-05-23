from scripts import module_quality_gate as gate


def test_module_matrix_has_expected_modules():
    assert {
        "repo_guard",
        "portable_install",
        "desktop_auth_runtime",
        "live_agent",
        "playwright_ai",
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


def test_find_staged_out_of_scope_uses_normalized_paths():
    staged = gate.find_staged_out_of_scope(
        [
            "scripts\\ops\\check_naver_mail.py",
            "local_agent/desktop_launcher.py",
        ]
    )

    assert staged == ["scripts/ops/check_naver_mail.py"]
