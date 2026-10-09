from tools.audits.app import audit_app_development_standard as audit


def test_app_development_standard_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_app_development_standard_is_locked():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-APP-DEVELOPMENT-STANDARD-01" in text
    assert "The app is a server-first control surface." in text


def test_app_development_standard_defines_required_navigation():
    text = audit.STANDARD.read_text(encoding="utf-8")

    for label in (
        "Dashboard",
        "Tasks",
        "Approvals",
        "Agents",
        "Tools",
        "Connections",
        "Audit",
        "Consent",
        "Reports",
        "Settings",
    ):
        assert label in text


def test_app_development_standard_prioritizes_user_convenience():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 2.1 User Convenience Standard" in text
    assert "comfortable for a non-developer operator" in text
    assert "What can I safely do next?" in text
    assert "plain business language" in text


def test_app_development_standard_defines_target_users():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 2.2 Target Users" in text
    assert "Owner" in text
    assert "Operator" in text
    assert "Reviewer" in text
    assert "Non-developer user" in text


def test_app_development_standard_forbids_raw_sensitive_display():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "raw prompts" in text
    assert "raw files" in text
    assert "raw emails" in text
    assert "raw screenshots" in text
    assert "approval tokens" in text
    assert "sensitive personal data" in text


def test_app_development_standard_locks_development_order():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "app shell and route skeleton" in text
    assert "read-only server status dashboard" in text
    assert "task list and task detail" in text
    assert "user data contribution consent view" in text


def test_app_development_standard_locks_connections_and_commands():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 9.1 Connection And Command Lock" in text
    assert "Allowed command classes:" in text
    assert "Forbidden command classes:" in text
    assert "server_restart" in text
    assert "process_kill" in text
    assert "unknown_tool_execute" in text
    assert "must not wire them to an executable handler" in text


def test_app_development_standard_only_attaches_developed_tools():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 9.2 Developed Tool Attachment Lock" in text
    assert "Only developed and inventoried tools may be attached to the app." in text
    assert "docs/inventory/TOOL_INVENTORY.md" in text
    assert "docs/inventory/CONNECTION_INVENTORY.md" in text
    assert "status is `active` or `locked`" in text
    assert "Tools in `legacy`, `deprecated`, `unknown`, `TBD`, or `Lock Needed Queue`" in text


def test_app_development_standard_requires_first_time_flow_and_error_messages():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 4.1 First-Time User Flow" in text
    assert "server status check" in text
    assert "data contribution consent choice" in text
    assert "API failures must be translated into user-actionable messages" in text
    assert "The app must never show raw stack traces to normal users." in text


def test_app_development_standard_requires_usability_accessibility_responsive_rules():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 7.1 Usability Standard" in text
    assert "disabled buttons explain why they are disabled" in text
    assert "## 7.2 Accessibility And Readability" in text
    assert "visible focus state" in text
    assert "## 7.3 Responsive Standard" in text
    assert "text must not overlap badges, buttons, or panels" in text


def test_app_development_standard_requires_user_acceptance_checklist():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "## 12. User Acceptance Checklist" in text
    assert "understand the screen purpose within 5 seconds" in text
    assert "recover from an error without reading raw logs" in text
    assert "If any item fails, the screen is incomplete even when the code works." in text


def test_app_development_standard_requires_verification():
    text = audit.STANDARD.read_text(encoding="utf-8")

    assert "python tools/audits/app/audit_app_development_standard.py" in text
    assert "python tools/audits/app/audit_app_structure_contract.py" in text
    assert "python -m pytest tests/test_app_development_standard.py -q" in text


def test_app_development_standard_is_referenced_by_baselines():
    combined = (
        audit.APP_BASELINE.read_text(encoding="utf-8")
        + "\n"
        + audit.APP_STRUCTURE.read_text(encoding="utf-8")
    )

    assert "docs/baseline/APP_DEVELOPMENT_STANDARD.md" in combined
    assert "The app development standard controls app shell, route, screen, API integration" in combined
