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
