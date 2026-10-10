from tools.audits.app import audit_common_engine_commercialization_baseline as audit


def test_common_engine_commercialization_baseline_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_common_engine_commercialization_baseline_is_locked():
    text = audit.BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "HAEHAN-COMMON-ENGINE-COMMERCIALIZATION-BASELINE-01" in text
    assert "The app is the control surface" in text
    assert "Connection failures must end as safe failure states" in text
    assert "no-final-submit mode" in text
    assert "Evidence must not contain raw secrets" in text


def test_common_engine_commercialization_is_engine_first():
    text = audit.BASELINE.read_text(encoding="utf-8")

    assert "common engine contract" in text
    assert "connection and recovery hardening" in text
    assert "app UI first" in text
    assert "engine retrofit" in text
