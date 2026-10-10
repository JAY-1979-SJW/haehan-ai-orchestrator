from tools.audits.app import audit_app_structure_contract as audit


def test_app_structure_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_app_structure_locks_server_first_control_surface():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-APP-STRUCTURE-01" in text
    assert "The app must be developed as a server-first control surface." in text
    assert "The server is the final operational source of truth for HAEHAN." in text
    assert "## Structural Layers" in text
    assert "## Parallel Work Design" in text
    assert "## Canonical Flow" in text
    assert "## Forbidden Structure" in text


def test_app_structure_locks_parallel_work_design():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "ownership boundaries are explicit and write sets are disjoint" in text
    assert "app UI shell and screens" in text
    assert "server API contracts" in text
    assert "local-agent dispatch and connection recovery" in text
    assert "tool/site adapter contracts" in text
    assert "standard UI package" in text
    assert "inventories, reports, and audits" in text
    assert "each workstream must declare its owner module before editing" in text
    assert "each workstream must use a disjoint write set" in text
    assert "shared baselines may be edited by one workstream at a time" in text
    assert "cross-module changes must run every affected module gate" in text
    assert "configs/module_boundaries.json" in text
    assert "Parallel work is not allowed for live deploy" in text


def test_app_structure_locks_recovery_boundary():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "## Recovery Boundary" in text
    assert "diagnostic-first and server-baseline controlled" in text
    assert "automatic server deploy/restart" in text
    assert "Docker build, pull, up, restart, or deploy" in text
    assert "local-agent token deletion or credential reset" in text
    assert "persistent local autostart registration" in text
    assert "background recovery registration" in text
    assert "always-on monitoring registration" in text
    assert "process termination outside the approved target app" in text
    assert "audit-first unless their task is separately approved" in text


def test_app_structure_locks_task_history_and_audit_log_boundary():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "## Task History And Audit Log Boundary" in text
    assert "The server task state and server audit events are the final source of truth." in text
    assert "Local-agent and desktop logs are diagnostic evidence only." in text
    assert "must not contain raw" in text


def test_app_structure_locks_user_data_contribution_consent_boundary():
    text = audit.APP_STRUCTURE.read_text(encoding="utf-8")

    assert "## User Data Contribution Consent Boundary" in text
    assert "explicit user data contribution consent" in text
    assert "Only redacted and minimized development material" in text
    assert "must not send or store raw user prompts" in text


def test_app_structure_guard_report_exists():
    text = audit.REPORT.read_text(encoding="utf-8")

    assert "App Structure Guard" in text
    assert "Recovery Boundary" in text
    assert "No live recovery script was added." in text
    assert "Task History And Audit Log Boundary" in text
    assert "User Data Contribution Consent Boundary" in text
