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


def test_fallback_ui_is_warned_not_failed():
    findings = audit.audit()
    fallback = {
        finding.path: finding.status
        for finding in findings
        if finding.path in audit.FALLBACK_UI_ALLOWED
    }

    assert fallback
    assert all(status == "WARN" for status in fallback.values())


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
