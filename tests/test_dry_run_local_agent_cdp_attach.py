from tools.verify import dry_run_local_agent_cdp_attach as gate


def test_dry_run_local_agent_cdp_attach_passes_static_contract():
    result = gate.dry_run()

    assert result.passed, [finding.__dict__ for finding in result.findings]
    assert result.verdict == "PASS_LOCAL_AGENT_CDP_ATTACH_DRY_RUN_READY"


def test_staged_paths_normalizes_out_of_scope_paths():
    staged = gate.staged_paths(
        [
            "M  scripts\\ops\\check_naver_mail.py",
            " M core\\agent_runtime\\browser\\cdp_attach.py",
            "?? tests\\test_local_agent_cdp_attach.py",
        ]
    )

    assert staged == {"scripts/ops/check_naver_mail.py"}


def test_chrome_ui_monitor_state_path_is_runtime_not_archive():
    monitor_text = gate.CHROME_UI_MONITOR.read_text(encoding="utf-8", errors="replace")
    client_text = gate.CDP_CLIENT.read_text(encoding="utf-8", errors="replace")

    assert '"data" / "runtime" / "chrome_ui_monitor_state.json"' in monitor_text
    assert '"data" / "runtime" / "chrome_ui_monitor_state.json"' in client_text
    assert '"data" / "chrome_ui_monitor_state.json"' not in monitor_text
    assert '"data" / "chrome_ui_monitor_state.json"' not in client_text
