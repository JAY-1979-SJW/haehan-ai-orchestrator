from scripts.ops import audit_app_baseline_contract as audit


def test_app_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_app_baseline_is_locked_source_of_truth():
    text = audit.BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "This baseline is the top-level source of truth for app development." in text
    assert "input/output contract" in text
    assert "authorization boundary" in text
    assert "state changes" in text
    assert "regression gate" in text
