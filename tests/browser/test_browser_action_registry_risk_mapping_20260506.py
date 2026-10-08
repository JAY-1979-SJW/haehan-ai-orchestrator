"""BROWSER_ACTION_REGISTRY_RISK_MAPPING_1 fixture validation tests."""

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_action_registry_risk_mapping_20260506.json"

GATE_REQUIRED = {
    "browser.plan_submit",
    "browser.execute_click",
    "browser.execute_type",
    "browser.open_click_close_controlled",
    "browser.open_type_close_controlled",
}
GATE_NOT_REQUIRED = {
    "browser.inspect",
    "browser.plan_click",
    "browser.plan_type",
    "browser.plan_open_url",
    "browser.open_url_controlled",
}
ALL_ACTIONS = GATE_REQUIRED | GATE_NOT_REQUIRED
BLOCKED = {"browser.submit.production", "browser.submit.real"}


def load_fixture():
    assert FIXTURE_PATH.exists(), f"fixture not found: {FIXTURE_PATH}"
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _action(data, name):
    for a in data["actions"]:
        if a["action_name"] == name:
            return a
    raise KeyError(f"action not found: {name}")


def test_fixture_loads():
    data = load_fixture()
    assert data["mapping_id"] == "BROWSER_ACTION_REGISTRY_RISK_MAPPING_1"
    assert data["version"] == "1.0"


def test_all_actions_present():
    data = load_fixture()
    names = {a["action_name"] for a in data["actions"]}
    assert names == ALL_ACTIONS


def test_no_registry_modified():
    data = load_fixture()
    assert data["registry_modified"] is False


def test_no_task_executor_modified():
    data = load_fixture()
    assert data["task_executor_modified"] is False


def test_production_submit_not_allowed():
    data = load_fixture()
    assert data["production_submit_allowed"] is False


def test_blocked_actions_listed():
    data = load_fixture()
    blocked_names = {b["action_name"] for b in data["blocked_actions"]}
    assert blocked_names == BLOCKED


def test_gate_required_list_matches():
    data = load_fixture()
    assert set(data["gate_required_actions"]) == GATE_REQUIRED


def test_gate_not_required_list_matches():
    data = load_fixture()
    assert set(data["gate_not_required_actions"]) == GATE_NOT_REQUIRED


# LOW_READ
def test_browser_inspect_low_read():
    data = load_fixture()
    a = _action(data, "browser.inspect")
    assert a["risk_tier"] == "LOW_READ"
    assert a["requires_approval"] is False
    assert a["requires_gate"] is False
    assert a["read_only"] is True
    assert a["production_allowed"] is False


# LOW_NAVIGATE
def test_browser_plan_click_low_navigate():
    data = load_fixture()
    a = _action(data, "browser.plan_click")
    assert a["risk_tier"] == "LOW_NAVIGATE"
    assert a["requires_approval"] is False
    assert a["requires_gate"] is False
    assert a["production_allowed"] is False


def test_browser_plan_open_url_low_navigate():
    data = load_fixture()
    a = _action(data, "browser.plan_open_url")
    assert a["risk_tier"] == "LOW_NAVIGATE"
    assert a["requires_gate"] is False


def test_browser_execute_click_high_state_change():
    """browser.execute_click: RECLASSIFICATION_1 이후 HIGH_STATE_CHANGE로 재분류."""
    data = load_fixture()
    a = _action(data, "browser.execute_click")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"
    assert a["requires_gate"] is True
    assert a["requires_approval"] is True
    assert a["recommended_risk"] == "high"
    assert a["side_effect"] is True
    assert a["allowlist_required"] is True
    assert a["dispatcher_connected"] is False
    assert a["production_submit_possible"] is False


# MEDIUM_TYPE
def test_browser_plan_type_medium_type():
    data = load_fixture()
    a = _action(data, "browser.plan_type")
    assert a["risk_tier"] == "MEDIUM_TYPE"
    assert a["requires_gate"] is False
    assert a["sensitive_field_block"] is True


def test_browser_execute_type_high_state_change():
    """browser.execute_type: RECLASSIFICATION_1 이후 HIGH_STATE_CHANGE로 재분류."""
    data = load_fixture()
    a = _action(data, "browser.execute_type")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"
    assert a["requires_gate"] is True
    assert a["sensitive_field_block"] is True
    assert a["requires_approval"] is True
    assert a["recommended_risk"] == "high"
    assert a["side_effect"] is True
    assert a["allowlist_required"] is True
    assert a["dispatcher_connected"] is False
    assert a["production_submit_possible"] is False


# HIGH_STATE_CHANGE
def test_browser_plan_submit_high_state_change():
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a["risk_tier"] == "HIGH_STATE_CHANGE"
    assert a["requires_gate"] is True
    assert a["requires_approval"] is True
    assert a["requires_audit"] is True
    assert a["production_allowed"] is False


def test_browser_plan_submit_risk_level_needs_review():
    data = load_fixture()
    a = _action(data, "browser.plan_submit")
    assert a["risk_level_needs_review"] is True
    assert a["recommended_risk"] == "high"


# CRITICAL_SUBMIT
def test_browser_open_type_close_controlled_critical_submit():
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a["risk_tier"] == "CRITICAL_SUBMIT"
    assert a["requires_gate"] is True
    assert a["requires_preview"] is True
    assert a["requires_preview_hash"] is True
    assert a["requires_audit"] is True
    assert a["requires_user_confirmed"] is True
    assert a["production_allowed"] is False
    assert a["controlled_internal_only"] is True


def test_browser_open_type_close_controlled_gate_module():
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a["gate_module"] == "submit_execution_gate"
    assert a["audit_module"] == "submit_audit_log"


def test_browser_open_type_close_controlled_risk_needs_review():
    data = load_fixture()
    a = _action(data, "browser.open_type_close_controlled")
    assert a["risk_level_needs_review"] is True
    assert a["recommended_risk"] == "high"


# 전체 검증: production_allowed 전원 False
def test_no_action_allows_production():
    data = load_fixture()
    for a in data["actions"]:
        assert a["production_allowed"] is False, f"{a['action_name']}: production_allowed must be False"


# gate_required 와 gate_not_required 겹침 없음
def test_gate_required_and_not_required_no_overlap():
    data = load_fixture()
    gate_req = set(data["gate_required_actions"])
    gate_not = set(data["gate_not_required_actions"])
    assert gate_req.isdisjoint(gate_not), "gate_required와 gate_not_required가 겹침"


# GATE 필수 action은 requires_gate=True
def test_gate_required_actions_have_gate_flag():
    data = load_fixture()
    for name in data["gate_required_actions"]:
        a = _action(data, name)
        assert a["requires_gate"] is True, f"{name}: requires_gate must be True"


# GATE 불필요 action은 requires_gate=False
def test_gate_not_required_actions_no_gate_flag():
    data = load_fixture()
    for name in data["gate_not_required_actions"]:
        a = _action(data, name)
        assert a["requires_gate"] is False, f"{name}: requires_gate must be False"
