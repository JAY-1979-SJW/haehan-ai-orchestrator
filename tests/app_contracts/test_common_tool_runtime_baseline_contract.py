from tools.audits.agent import audit_common_tool_runtime_baseline_contract as audit


def test_common_tool_runtime_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_common_tool_runtime_baseline_is_locked():
    text = audit.COMMON_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-COMMON-TOOL-RUNTIME-BASELINE-01" in text


def test_common_tool_runtime_baseline_locks_contract_and_risk_boundaries():
    text = audit.COMMON_BASELINE.read_text(encoding="utf-8")

    assert "task contract" in text
    assert "result contract" in text
    assert "risk level" in text
    assert "approval required flag" in text
    assert "Approval-required risk must not be bypassed by callers." in text


def test_common_tool_runtime_baseline_blocks_execution_and_secret_shortcuts():
    text = audit.COMMON_BASELINE.read_text(encoding="utf-8")

    assert "raw Authorization header" in text
    assert "Forbidden field rejection must occur before execution is delegated" in text
    assert "execute browser work directly" in text
    assert "call Playwright directly" in text
    assert "duplicate site-specific workflow logic" in text

