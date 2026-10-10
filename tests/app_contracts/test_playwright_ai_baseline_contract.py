from tools.audits.agent import audit_playwright_ai_baseline_contract as audit


def test_playwright_ai_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_playwright_ai_baseline_is_locked():
    text = audit.PLAYWRIGHT_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-PLAYWRIGHT-AI-BASELINE-01" in text


def test_playwright_ai_baseline_locks_execution_boundaries():
    text = audit.PLAYWRIGHT_BASELINE.read_text(encoding="utf-8")

    assert "Server must not run Playwright directly." in text
    assert "Browser execution must be local-agent mediated." in text
    assert "Dry-run checks must remain side-effect free." in text
    assert "Live browser checks require explicit approval." in text


def test_playwright_ai_baseline_blocks_secret_and_approval_bypass():
    text = audit.PLAYWRIGHT_BASELINE.read_text(encoding="utf-8")

    assert "credential/session/cookie extraction request" in text
    assert "Unapproved high-risk browser tasks must not execute." in text
    assert "bypass local-agent dispatch" in text
    assert "use AI output as authorization or approval" in text

