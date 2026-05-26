# Standard Workflow Final-Approval-Only Update

Status: completed
Date: 2026-05-26
Final location: server baseline

## Scope

Updated the locked standard workflow so non-trivial work starts with a concise
overview and one approval, then proceeds autonomously inside the approved scope.

## Rule

The user should not be asked repeated intermediate "how should I proceed?"
questions after approving the overview. The worker stops only for blockers,
scope changes, secrets, live runtime, deploy, push, or final state-changing
approval.

## Final User Approval Points

Create, Save, Submit, Consent, Publish, Delete, payment, permission grant,
deploy, restart, and secret entry remain user approval points unless the exact
execution stage is separately approved.

## Verification

- `python -m pytest tests\test_standard_workflow_contract.py -q`
- `python scripts\ops\audit_standard_workflow_contract.py`
