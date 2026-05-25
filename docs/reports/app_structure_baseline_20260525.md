# App Structure Baseline - 2026-05-25

## Scope

Documented the server-first app structure used for future app development.

## Finding

App structure analysis confirms the current split:

- `ai_orchestrator/`: server/API/auth/approval/task state/audit ownership
- `ai_orchestrator/local_agent/common_tool_runtime.py`: common task/result/risk
  contract
- `scripts/site_engine/` and site folders: common site policy plus thin
  site/tool adapters
- `local_agent/`: authenticated PC-side execution for server-dispatched tasks
- `desktop/`: local runtime/control hub subordinate to the server contract
- `scripts/ops/` and `tests/`: audit, verification, dry-run, and gate evidence
- `docs/inventory/` and `docs/reports/`: durable inventory and work evidence

## Decision

Future app development should use `docs/architecture/APP_STRUCTURE.md` as the
structure baseline. The app is a control surface, not an independent execution
or policy source.

## Verification

```text
python scripts/ops/audit_standard_workflow_contract.py
python -m pytest tests/test_standard_workflow_contract.py -q
python -m py_compile scripts/ops/audit_standard_workflow_contract.py
git diff --check
```

## Remaining Work

The structure baseline is ready. The next practical step is a deeper executable
tool inventory audit that enumerates scripts and classifies unknown tools one by
one.
