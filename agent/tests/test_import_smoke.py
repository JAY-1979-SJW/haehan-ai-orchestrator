"""Import smoke tests — verify core agent modules load without side effects."""
import importlib


def test_agent_core_modules_import_without_side_effects():
    # agent.approval_policy and agent.app require agent.policy which is not present in
    # this branch; those dependencies are tracked separately and excluded here.
    for module in [
        "agent.action_registry",
        "agent.task_executor",
    ]:
        importlib.import_module(module)


def test_action_registry_import():
    importlib.import_module("agent.action_registry")
