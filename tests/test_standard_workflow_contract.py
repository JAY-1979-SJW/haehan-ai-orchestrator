from scripts.ops import audit_standard_workflow_contract as audit


def test_standard_workflow_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_standard_workflow_is_locked():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-STANDARD-WORKFLOW-01" in text
    assert "docs/templates/STANDARD_REPORT_TEMPLATE.md" in text


def test_standard_report_template_requires_learning_explanation():
    text = audit.REPORT_TEMPLATE.read_text(encoding="utf-8")

    assert "Function:" in text
    assert "Why it exists:" in text
    assert "Input:" in text
    assert "Output:" in text
    assert "Failure behavior:" in text
    assert "How to think when writing it manually:" in text


def test_standard_workflow_limits_actions_to_target_app():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "Target App Scope Rule" in text
    assert "approved target app or repository" in text
    assert "do not stop, modify, delete, stage, or commit anything for that external app" in text
    assert "ask for separate approval" in text


def test_standard_workflow_preserves_server_first_operating_rule():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "Server-First Operating Rule" in text
    assert "The server is the final operational source of truth for HAEHAN." in text
    assert "treat desktop and local-agent code as subordinate execution layers" in text
    assert "do not add persistent local autostart" in text


def test_standard_workflow_defines_safe_auto_run_rule():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "Auto-Run Rule" in text
    assert "Automation is allowed only for safe, bounded work inside the approved scope." in text
    assert "baseline and contract audits" in text
    assert "The worker may commit only when the user explicitly requests commit" in text
    assert "The worker may push only when the user explicitly requests push" in text
    assert "Auto-run must never perform server deploy/restart" in text


def test_standard_workflow_requires_inventory_and_reports():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "Tool Inventory And Report Rule" in text
    assert "docs/inventory/TOOL_INVENTORY.md" in text
    assert "docs/inventory/CONNECTION_INVENTORY.md" in text
    assert "docs/reports/<task>_<yyyymmdd>.md" in text
    assert "data/inspection/<task>/..." in text
    assert "Logs alone are not sufficient as final work evidence." in text


def test_inventory_documents_exist_and_define_lock_queue():
    for path in (audit.TOOL_INVENTORY, audit.CONNECTION_INVENTORY):
        text = path.read_text(encoding="utf-8")

        assert "Status: ACTIVE" in text
        assert "Owner baseline: `docs/baseline/APP_BASELINE.md`" in text
        assert "Workflow rule: `docs/baseline/STANDARD_WORKFLOW.md`" in text
        assert "Lock Needed Queue" in text


def test_standard_workflow_requires_app_structure_updates():
    text = audit.WORKFLOW.read_text(encoding="utf-8")

    assert "App Structure Rule" in text
    assert "docs/architecture/APP_STRUCTURE.md" in text
    assert "The app must remain a server-first control surface." in text


def test_app_structure_baseline_exists_and_locks_control_surface():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "Status: ACTIVE" in text
    assert "The app must be developed as a server-first control surface." in text
    assert "The server is the final operational source of truth for HAEHAN." in text
    assert "## Structural Layers" in text
    assert "## Canonical Flow" in text
    assert "## Forbidden Structure" in text
    assert "## Recovery Boundary" in text
    assert "## Development Order" in text
