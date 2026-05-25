# App Structure Guard - 2026-05-25

## Scope

Added a read-only app structure contract audit and recovery boundary checks.

## Decision

The app remains a server-first control surface. Recovery behavior is
diagnostic-first and server-baseline controlled.

## Recovery Boundary

No live recovery script was added.

The guard documents and audits that the following require separate explicit
approval:

- automatic server deploy/restart
- Docker build, pull, up, restart, or deploy
- local-agent token deletion or credential reset
- persistent local autostart registration
- background recovery registration
- always-on monitoring registration
- process termination outside the approved target app
- editing another workspace, app, server, browser, or test runner

## Added Verification

```text
python scripts/ops/audit_app_structure_contract.py
python -m pytest tests/test_app_structure_contract.py -q
```

## Verification

```text
python scripts/ops/audit_app_structure_contract.py
python scripts/ops/audit_standard_workflow_contract.py
python -m pytest tests/test_app_structure_contract.py tests/test_standard_workflow_contract.py -q
python -m py_compile scripts/ops/audit_app_structure_contract.py scripts/ops/audit_standard_workflow_contract.py
git diff --check
```
