from scripts.ops import audit_release_preflight_baseline_contract as audit


def test_release_preflight_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_release_preflight_baseline_is_locked():
    text = audit.RELEASE_PREFLIGHT_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-RELEASE-PREFLIGHT-BASELINE-01" in text


def test_release_preflight_baseline_locks_no_build_boundary():
    text = audit.RELEASE_PREFLIGHT_BASELINE.read_text(encoding="utf-8")

    assert "Preflight must not run `npm run build`." in text
    assert "Preflight must not run `electron-builder`." in text
    assert "Preflight must not run `pyinstaller`." in text
    assert "Preflight must not run Docker build, pull, up, restart, or deploy." in text


def test_release_preflight_baseline_locks_classification_boundaries():
    text = audit.RELEASE_PREFLIGHT_BASELINE.read_text(encoding="utf-8")

    assert "Secret scan findings must be classified." in text
    assert "UI residue cleanup must not run during preflight unless explicitly approved." in text
    assert "Environment WARN must be reported separately from security FAIL." in text

