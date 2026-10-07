from __future__ import annotations

from scripts.common.gates import secret_action_gate as gate


def test_secret_action_gate_defaults_to_final_approval_only() -> None:
    policy = gate.build_secret_action_policy()

    assert policy["mode"] == "final_approval_only"
    assert policy["final_button_user_only"] is True
    assert policy["agent_final_secret_issue_allowed"] is False
    assert policy["raw_secret_output_allowed"] is False


def test_secret_action_gate_user_click_keeps_agent_blocked() -> None:
    policy = gate.build_secret_action_policy("secret_issue_user_click")

    assert policy["status"] == "ok"
    assert policy["final_button_user_only"] is True
    assert policy["agent_final_secret_issue_allowed"] is False
    assert policy["raw_secret_output_allowed"] is False


def test_secret_action_gate_agent_click_requires_explicit_approval() -> None:
    policy = gate.build_secret_action_policy("secret_issue_agent_click")

    assert policy["status"] == "blocked"
    assert policy["blocked_reason"] == "secret_issue_agent_click_requires_explicit_approval"
    assert policy["agent_final_secret_issue_allowed"] is False
    assert policy["raw_secret_output_allowed"] is False


def test_secret_action_gate_agent_click_can_be_explicitly_approved() -> None:
    policy = gate.build_secret_action_policy("secret_issue_agent_click", secret_issue_approved=True)

    assert policy["status"] == "ok"
    assert policy["agent_final_secret_issue_allowed"] is True
    assert policy["raw_secret_output_allowed"] is False
