from tools.audits.app import audit_module_baseline_contract as audit


def test_module_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_module_baseline_is_locked():
    text = audit.MODULE_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-MODULE-BASELINE-01" in text


def test_module_baseline_lists_all_modules():
    text = audit.MODULE_BASELINE.read_text(encoding="utf-8")

    for module in audit.MODULES:
        assert f"### {module}" in text


def test_module_baseline_requires_security_boundaries():
    text = audit.MODULE_BASELINE.read_text(encoding="utf-8")

    assert "no raw secret, token, cookie, session, password, or OTP output" in text
    assert "no hardcoded admin bearer header" in text
    assert "no server-side local browser execution" in text
    assert "no unapproved high-risk browser write execution" in text

