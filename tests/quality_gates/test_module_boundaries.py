from tools.audits.app import audit_module_boundaries as audit


def test_module_boundary_audit_passes():
    findings = audit.audit()
    failed = [finding for finding in findings if finding.status == "FAIL"]

    assert failed == []


def test_module_boundary_config_is_locked():
    config = audit._load_config()

    assert config["status"] == "locked"
    assert {module["name"] for module in config["modules"]} >= {
        "repo_guard",
        "local_agent_browser_runtime",
        "desktop_runtime",
        "admin_web",
        "server_api",
        "site_automation",
        "legacy_root_quarantine",
    }


def test_module_boundary_forbids_actions_workflows():
    findings = audit.audit()

    assert any(
        finding.item == "github_actions_disabled" and finding.status == "PASS"
        for finding in findings
    )
