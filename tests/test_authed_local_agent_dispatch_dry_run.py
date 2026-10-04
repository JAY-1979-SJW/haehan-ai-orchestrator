from scripts.ops import audit_authed_local_agent_dispatch_dry_run as audit


def test_authed_local_agent_dispatch_dry_run_passes_static_contract():
    result = audit.audit()
    assert result.verdict == "PASS_AUTHED_LOCAL_AGENT_DISPATCH_DRY_RUN_READY"
    assert result.passed is True


def test_dry_run_script_has_no_forbidden_execution_tokens():
    script = audit.Path(audit.__file__).read_text(encoding="utf-8", errors="replace").lower()
    forbidden = [token for token in audit.FORBIDDEN_SCRIPT_TOKENS if token in script]
    assert audit.FORBIDDEN_SCRIPT_TOKENS, "audit.FORBIDDEN_SCRIPT_TOKENS 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert forbidden == []
