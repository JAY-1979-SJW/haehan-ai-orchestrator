from scripts.ops import dry_run_local_agent_cdp_attach as gate


def test_dry_run_local_agent_cdp_attach_passes_static_contract():
    result = gate.dry_run()

    assert result.passed, [finding.__dict__ for finding in result.findings]
    assert result.verdict == "PASS_LOCAL_AGENT_CDP_ATTACH_DRY_RUN_READY"


def test_staged_paths_normalizes_out_of_scope_paths():
    staged = gate.staged_paths(
        [
            "M  scripts\\ops\\check_naver_mail.py",
            " M local_agent\\cdp_attach.py",
            "?? tests\\test_local_agent_cdp_attach.py",
        ]
    )

    assert staged == {"scripts/ops/check_naver_mail.py"}
