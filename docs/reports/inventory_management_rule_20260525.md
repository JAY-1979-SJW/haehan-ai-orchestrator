# Inventory Management Rule - 2026-05-25

## Scope

Added durable inventory management for tools and connections.

## Changed Files

- `docs/inventory/TOOL_INVENTORY.md`
- `docs/inventory/CONNECTION_INVENTORY.md`
- `docs/baseline/STANDARD_WORKFLOW.md`
- `docs/architecture/development_governance_rules_20260515.md`
- `scripts/ops/audit_standard_workflow_contract.py`
- `tests/test_standard_workflow_contract.py`

## Rule

When a task creates, changes, removes, audits, or classifies a tool, runtime
entrypoint, connector, automation script, site module, or operational helper,
the worker must update the durable inventory and create a human-readable task
report. Machine-readable inspection output should be stored under
`data/inspection/<task>/` when available.

Logs alone are not sufficient as final work evidence.

## Verification

```text
python scripts/ops/audit_standard_workflow_contract.py
python -m pytest tests/test_standard_workflow_contract.py -q
python -m py_compile scripts/ops/audit_standard_workflow_contract.py
git diff --check
```

## Remaining Work

The initial inventories are baseline-level indexes. A deeper inventory audit
should later enumerate each executable script and classify unknown tools one by
one.
