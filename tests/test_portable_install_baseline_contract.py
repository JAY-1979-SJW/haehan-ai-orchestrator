from scripts.ops import audit_portable_install_baseline_contract as audit


def test_portable_install_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_portable_install_baseline_is_locked():
    text = audit.PORTABLE_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-PORTABLE-INSTALL-BASELINE-01" in text


def test_portable_install_baseline_locks_no_admin_install():
    text = audit.PORTABLE_BASELINE.read_text(encoding="utf-8")

    assert "`install.bat` must run without administrator rights." in text
    assert "Installation must not copy files into Program Files." in text
    assert "Installation must not edit registry." in text
    assert "Installation must not edit PATH." in text


def test_portable_install_baseline_locks_diagnostics_and_uninstall_boundaries():
    text = audit.PORTABLE_BASELINE.read_text(encoding="utf-8")

    assert "Diagnostics must mask secrets." in text
    assert "`uninstall.bat` removes shortcuts only." in text
    assert "`uninstall.bat` must not delete logs." in text
    assert "Actual portable zip creation is separate and requires explicit approval." in text

