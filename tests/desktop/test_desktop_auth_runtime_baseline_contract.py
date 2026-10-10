from tools.audits.agent import audit_desktop_auth_runtime_baseline_contract as audit


def test_desktop_auth_runtime_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_desktop_auth_runtime_baseline_is_locked():
    text = audit.DESKTOP_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-DESKTOP-AUTH-RUNTIME-BASELINE-01" in text


def test_desktop_auth_runtime_baseline_locks_auth_failure_boundary():
    text = audit.DESKTOP_BASELINE.read_text(encoding="utf-8")

    assert "If token/session is missing, protected requests must not be sent." in text
    assert "Authorization header values must never be printed." in text
    assert "`Bearer admin-token` is forbidden." in text
    assert "hide auth failure behind mock success" in text


def test_desktop_auth_runtime_baseline_locks_runtime_isolation():
    text = audit.DESKTOP_BASELINE.read_text(encoding="utf-8")

    assert "desktop runtime state isolation" in text
    assert "mix unrelated app UI state with this app" in text
    assert "Global `SESSION_ID` shortcut is dangerous" in text

