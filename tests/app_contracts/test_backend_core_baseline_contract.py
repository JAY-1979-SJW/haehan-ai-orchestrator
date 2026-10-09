from tools.audits.backend import audit_backend_core_baseline_contract as audit


def test_backend_core_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_backend_core_baseline_is_locked():
    text = audit.BACKEND_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-BACKEND-CORE-BASELINE-01" in text


def test_backend_core_baseline_locks_auth_and_approval_boundaries():
    text = audit.BACKEND_BASELINE.read_text(encoding="utf-8")

    assert "AUTH_ENABLED" in text
    assert "Protected APIs must require authenticated users." in text
    assert "High-risk tasks remain blocked until approval succeeds." in text
    assert "Approval failure or approval API misconfiguration must return a safe failure" in text


def test_backend_core_baseline_blocks_unsafe_runtime_shortcuts():
    text = audit.BACKEND_BASELINE.read_text(encoding="utf-8")

    assert "run Playwright directly" in text
    assert "Bearer admin-token" in text
    assert "hardcoded admin bearer token" in text
    assert "dispatch unapproved high-risk work to a local agent" in text

