from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONNECTION_INVENTORY = ROOT / "docs" / "inventory" / "CONNECTION_INVENTORY.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"


def test_connection_inventory_is_locked_to_server_first_flow():
    text = CONNECTION_INVENTORY.read_text(encoding="utf-8")
    app_baseline = APP_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Connection Logic Lock" in text
    assert "authenticated user instruction" in text
    assert "server task creation" in text
    assert "local-agent WebSocket authentication" in text
    assert "server state update" in text
    assert "audit event" in text
    assert "The server is the final operational source of truth" in text
    assert "The server is the final operational source of truth for HAEHAN." in app_baseline
    assert "docs/inventory/CONNECTION_INVENTORY.md" in app_baseline
    assert "must not bypass the server-first" in app_baseline


def test_connection_inventory_blocks_direct_and_unknown_execution_paths():
    text = CONNECTION_INVENTORY.read_text(encoding="utf-8")

    assert "Only connections with status `active` or `locked` may be used" in text
    assert "Unknown or unclassified connections must fail closed before command execution." in text
    assert "must not call local-agent, desktop, browser, Gmail, or site-work execution" in text
    assert "paths directly" in text
    assert "locked out of executable routing" in text


def test_connection_inventory_locks_local_agent_and_background_browser_boundaries():
    text = CONNECTION_INVENTORY.read_text(encoding="utf-8")

    assert "Local-agent WebSocket" in text
    assert "agent_id + device_token" in text
    assert "background_approved=True" in text
    assert "Desktop and local-agent logs are diagnostic evidence only" in text
    assert "AI Agent Work Record" in text


def test_connection_inventory_lists_required_lock_verification():
    text = CONNECTION_INVENTORY.read_text(encoding="utf-8")

    assert "python tools/audits/app/audit_standard_workflow_contract.py" in text
    assert "python tools/audits/agent/audit_local_agent_e2e_baseline_contract.py" in text
    assert "python tools/audits/agent/audit_local_agent_e2e_flow_contract.py" in text
    assert "python -m pytest tests/test_connection_inventory_lock.py -q" in text
