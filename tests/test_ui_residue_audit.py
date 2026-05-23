from scripts import ui_residue_audit as audit


def test_legacy_ui_paths_are_absent():
    findings = audit.audit()
    failures = [
        finding.path
        for finding in findings
        if finding.status == "FAIL" and finding.path in audit.LEGACY_UI_FORBIDDEN
    ]

    assert failures == []


def test_active_ui_entrypoints_are_present():
    findings = audit.audit()
    missing = [
        finding.path
        for finding in findings
        if finding.status == "FAIL" and finding.path in audit.ACTIVE_UI_REQUIRED
    ]

    assert missing == []


def test_fallback_ui_allowlist_is_empty_after_api_defaults():
    findings = audit.audit()
    unexpected_warnings = [
        finding.path
        for finding in findings
        if finding.status == "WARN"
    ]

    assert audit.FALLBACK_UI_ALLOWED == ()
    assert unexpected_warnings == []


def test_generated_residue_is_ignored_not_warned():
    findings = audit.audit()
    generated = [
        finding
        for finding in findings
        if finding.path in audit.GENERATED_RESIDUE_WARN
    ]

    assert all(finding.status == "PASS" for finding in generated)


def test_summary_passes_with_warnings():
    findings = [
        audit.Finding("PASS", "desktop/ui_dist/index.html", "active"),
        audit.Finding("WARN", "admin-web/.next", "generated"),
    ]

    result, passed, warned, failed = audit.summarize(findings)

    assert result == "PASS_UI_RESIDUE_AUDIT"
    assert passed == 1
    assert warned == 1
    assert failed == 0
