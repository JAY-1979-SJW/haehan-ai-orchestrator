from tools.audits.app import audit_app_baseline_contract as audit


def test_app_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_app_baseline_is_locked_source_of_truth():
    text = audit.BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "This baseline is the top-level source of truth for app development." in text
    assert "The server is the final operational source of truth for HAEHAN." in text
    assert "The final runtime baseline is server-first:" in text
    assert "Desktop and local-agent code are subordinate execution layers." in text
    assert "must not register persistent autostart" in text
    assert "input/output contract" in text
    assert "authorization boundary" in text
    assert "state changes" in text
    assert "regression gate" in text
    assert "local verification is not the final verdict" in text
    assert "the server repository HEAD matches the intended release HEAD" in text
    assert "server smoke checks pass through the public route or server-side nginx route" in text
    assert "server stress checks pass through the public route or server-side nginx route" in text
    assert "post-deploy logs are checked for new runtime errors" in text
