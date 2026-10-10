from tools.audits.app import audit_approval_flow_baseline_contract as audit


def test_approval_flow_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_approval_flow_baseline_is_locked():
    text = audit.APPROVAL_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-APPROVAL-FLOW-BASELINE-01" in text


def test_approval_flow_baseline_locks_api_default_and_safe_failure():
    text = audit.APPROVAL_BASELINE.read_text(encoding="utf-8")

    assert "API approval is the default." in text
    assert "Approval failure must fail closed." in text
    assert "API misconfiguration, timeout, network failure, or denied response must not" in text
    assert "waiting_approval -> failed" in text


def test_approval_flow_baseline_blocks_unsafe_fallbacks():
    text = audit.APPROVAL_BASELINE.read_text(encoding="utf-8")

    assert "enable local UI fallback by default" in text
    assert "accept unauthenticated approval" in text
    assert "allow high-risk task queue entry without approval" in text
    assert "use mock approval success in production" in text

