"""BROWSER_ACTION_RISK_TIER_POLICY_1 fixture validation tests."""

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_action_risk_tier_policy_20260506.json"

EXPECTED_TIERS = {"LOW_READ", "LOW_NAVIGATE", "MEDIUM_TYPE", "MEDIUM_DOWNLOAD", "HIGH_STATE_CHANGE", "CRITICAL_SUBMIT"}

LOW_READ_ACTIONS = {
    "page_open",
    "read_text",
    "extract_table",
    "screenshot",
    "inspect_dom",
    "get_current_url",
    "check_status",
}
LOW_NAVIGATE_ACTIONS = {"click_tab", "click_detail", "pagination", "breadcrumb", "open_link_same_origin"}
MEDIUM_TYPE_ACTIONS = {"type_text", "fill_search_keyword", "fill_filter", "fill_date_range", "select_option"}
MEDIUM_DOWNLOAD_ACTIONS = {"download_file", "save_attachment", "export_csv", "export_pdf"}
HIGH_STATE_CHANGE_ACTIONS = {
    "save_form",
    "form_commit",
    "approve_request",
    "mark_complete",
    "delete_record",
    "update_status",
}
CRITICAL_SUBMIT_ACTIONS = {
    "submit_form",
    "final_submit",
    "confirm_action",
    "execute_transaction",
    "open_type_close_controlled",
}

EXISTING_ACTION_MAPPING = {
    "inspect": "LOW_READ",
    "plan_click": "LOW_NAVIGATE",
    "plan_type": "MEDIUM_TYPE",
    "plan_submit": "HIGH_STATE_CHANGE",
    "execute_click": "LOW_NAVIGATE",
    "execute_type": "MEDIUM_TYPE",
    "open_type_close_controlled": "CRITICAL_SUBMIT",
}


def load_fixture():
    assert FIXTURE_PATH.exists(), f"fixture not found: {FIXTURE_PATH}"
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_fixture_loads():
    data = load_fixture()
    assert data["policy_id"] == "BROWSER_ACTION_RISK_TIER_POLICY_1"
    assert data["version"] == "1.0"


def test_all_tiers_present():
    data = load_fixture()
    assert set(data["tiers"].keys()) == EXPECTED_TIERS


def test_low_read_actions():
    data = load_fixture()
    assert set(data["tiers"]["LOW_READ"]["actions"]) == LOW_READ_ACTIONS


def test_low_read_no_approval_no_gate():
    data = load_fixture()
    tier = data["tiers"]["LOW_READ"]
    assert tier["requires_approval"] is False
    assert tier["gate_required"] is False


def test_low_navigate_actions():
    data = load_fixture()
    assert set(data["tiers"]["LOW_NAVIGATE"]["actions"]) == LOW_NAVIGATE_ACTIONS


def test_low_navigate_no_approval_no_gate():
    data = load_fixture()
    tier = data["tiers"]["LOW_NAVIGATE"]
    assert tier["requires_approval"] is False
    assert tier["gate_required"] is False


def test_medium_type_actions():
    data = load_fixture()
    assert set(data["tiers"]["MEDIUM_TYPE"]["actions"]) == MEDIUM_TYPE_ACTIONS


def test_medium_type_sensitive_field_block():
    data = load_fixture()
    tier = data["tiers"]["MEDIUM_TYPE"]
    assert tier["sensitive_field_block"] is True
    blocked = tier["blocked_field_patterns"]
    for field in ["password", "otp", "cert", "token", "session", "cookie"]:
        assert field in blocked, f"blocked_field_patterns missing: {field}"


def test_medium_type_submit_auto_link_forbidden():
    data = load_fixture()
    assert data["tiers"]["MEDIUM_TYPE"]["submit_auto_link_forbidden"] is True


def test_medium_download_actions():
    data = load_fixture()
    assert set(data["tiers"]["MEDIUM_DOWNLOAD"]["actions"]) == MEDIUM_DOWNLOAD_ACTIONS


def test_medium_download_blocked_extensions():
    data = load_fixture()
    tier = data["tiers"]["MEDIUM_DOWNLOAD"]
    assert tier["audit_required"] is True
    assert tier["path_allowlist_required"] is True
    for ext in [".exe", ".bat", ".sh", ".ps1"]:
        assert ext in tier["blocked_extensions"]


def test_high_state_change_actions():
    data = load_fixture()
    assert set(data["tiers"]["HIGH_STATE_CHANGE"]["actions"]) == HIGH_STATE_CHANGE_ACTIONS


def test_high_state_change_gate_and_approval():
    data = load_fixture()
    tier = data["tiers"]["HIGH_STATE_CHANGE"]
    assert tier["requires_approval"] is True
    assert tier["gate_required"] is True
    assert tier["audit_required"] is True


def test_critical_submit_actions():
    data = load_fixture()
    assert set(data["tiers"]["CRITICAL_SUBMIT"]["actions"]) == CRITICAL_SUBMIT_ACTIONS


def test_critical_submit_full_controls():
    data = load_fixture()
    tier = data["tiers"]["CRITICAL_SUBMIT"]
    assert tier["requires_approval"] is True
    assert tier["gate_required"] is True
    assert tier["audit_required"] is True
    assert tier["preview_required"] is True
    assert tier["preview_hash_required"] is True
    assert tier["user_confirmed_required"] is True
    assert tier["policy_verdict_required"] == "ALLOW"
    assert tier["controlled_internal_only"] is True
    assert tier["production_submit_allowed"] is False


def test_critical_submit_open_type_close_controlled_in_tier():
    data = load_fixture()
    assert "open_type_close_controlled" in data["tiers"]["CRITICAL_SUBMIT"]["actions"]


def test_no_tier_allows_production_submit():
    data = load_fixture()
    for tier_name, tier in data["tiers"].items():
        assert tier.get("production_submit_allowed") is False, f"{tier_name}: production_submit_allowed must be False"


def test_existing_action_mapping():
    data = load_fixture()
    mapping = data["existing_action_mapping"]
    for action, expected_tier in EXISTING_ACTION_MAPPING.items():
        assert mapping.get(action) == expected_tier, (
            f"action '{action}' expected tier '{expected_tier}', got '{mapping.get(action)}'"
        )


def test_conflict_verdict():
    data = load_fixture()
    assert data["conflict_verdict"] == "PASS_BROWSER_ACTION_RISK_TIER_POLICY"


def test_gate_only_on_high_and_critical():
    data = load_fixture()
    gate_not_required_tiers = ["LOW_READ", "LOW_NAVIGATE", "MEDIUM_TYPE", "MEDIUM_DOWNLOAD"]
    gate_required_tiers = ["HIGH_STATE_CHANGE", "CRITICAL_SUBMIT"]
    for tier in gate_not_required_tiers:
        assert data["tiers"][tier]["gate_required"] is False, f"{tier} should not require gate"
    for tier in gate_required_tiers:
        assert data["tiers"][tier]["gate_required"] is True, f"{tier} must require gate"
