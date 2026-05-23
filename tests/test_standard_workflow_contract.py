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

