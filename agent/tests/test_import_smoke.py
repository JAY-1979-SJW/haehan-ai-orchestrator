"""Import smoke tests — verify core agent modules load without side effects."""

import importlib


def test_agent_core_modules_import_without_side_effects():
    for module in [
        "agent.action_registry",
        "agent.policy",
        "agent.approval_policy",
        "agent.app",
    ]:
        importlib.import_module(module)
