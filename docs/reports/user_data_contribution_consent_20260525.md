# User Data Contribution Consent - 2026-05-25

## 1. Baseline

- Task ID: user-data-contribution-consent-20260525
- Start HEAD: b04e480
- End HEAD: working tree
- Git status: working tree changes pending
- Approved scope: implement explicit consent and safe development material export gate
- Out-of-scope files preserved: no unrelated app/runtime cleanup

## 2. Work Summary

- Goal: allow agent user task records to be used for development only after
  explicit server-recorded consent.
- Changed files: consent store, API router, route wiring, tests, baseline docs,
  inventories, and app structure report.
- Unchanged protected files: no credentials, live runtime state, deploy files,
  or external app files changed.
- Build/deploy/push/installer status: not run.

## 3. Baseline Contract Answers

- Input/output contract: consent requests record user reference, purposes, data
  categories, and retention; export requests return only redacted/minimized
  development material or a blocked result.
- Authorization boundary: consent endpoints require authenticated server API
  access; export endpoint requires admin or owner role.
- State changes: server consent records are appended to JSONL and replayed into
  memory; records can become ACTIVE or REVOKED; revoked/missing/out-of-scope
  consent blocks export.
- Regression gate: `tests/test_user_data_contribution_consent.py` plus standard
  workflow and app structure contract tests.

## 4. Function-Level Explanation

```text
Function: grant_consent
Why it exists: Records explicit server-owned consent before task history can be reused.
Input: user reference, organization reference, purposes, data categories, retention days.
Output: active consent metadata without raw user content, persisted as a JSONL lifecycle event.
Failure behavior: Raises ValueError for missing, unknown, or invalid consent scope.
Security or state boundary: Consent is purpose/category scoped and separate from normal service use.
How to think when writing it manually: Treat consent as a policy record, not as user content storage.
```

```text
Function: reload_store_from_disk
Why it exists: Rebuilds consent state after process restart from append-only JSONL events.
Input: durable consent JSONL events.
Output: number of restored consent records.
Failure behavior: Missing or unreadable log returns 0; malformed lines are skipped.
Security or state boundary: Replays consent metadata only, never development material or raw user content.
How to think when writing it manually: Event replay is last-wins state recovery for consent records.
```

```text
Function: export_development_material
Why it exists: Blocks development dataset creation unless consent and redaction rules pass.
Input: user reference, purpose, and candidate safe records.
Output: minimized records plus consent_id, or a blocked result.
Failure behavior: Blocks unknown purposes, forbidden raw fields, missing consent, revoked consent, or uncovered categories.
Security or state boundary: Raw prompts, files, emails, screenshots, browser traces, secrets, and third-party content are never exported.
How to think when writing it manually: Check consent first, but still reject unsafe raw material even when consent exists.
```

## 5. Verification

- Syntax checks: `python -m py_compile ai_orchestrator/server/user_data_contribution_store.py ai_orchestrator/user_data_contribution_router.py ai_orchestrator/router.py`
- Unit tests: `python -m pytest tests/test_user_data_contribution_consent.py -q` -> `10 passed`
- Contract audits: `python scripts/ops/audit_app_structure_contract.py`; `python scripts/ops/audit_standard_workflow_contract.py`
- Module gates: repo_guard passed through required quality gate.
- Required gate: `python scripts/required_quality_gate.py` -> `RESULT=PASS_REQUIRED_QUALITY_GATE`
- Live checks: not run.
- Skipped checks and reason: live server checks require separate approval.

## 6. Findings

- PASS: consent missing blocks export; consented safe categories export; raw prompt blocks even with consent; revoked consent blocks export; JSONL replay restores grant and revoke state.
- WARN: consent store is JSONL-based; relational DB migration is still next-stage work.
- FAIL: none.
- Remaining risk: persistent DB schema and UI consent control are next-stage work.

## 7. Prohibited Actions Check

- Secret value output: none.
- OUT_OF_SCOPE modification/staging: none.
- Docker/server deploy: not run.
- Build/installer/portable package: not run.
- Push: not run.

## 8. Final Verdict

PASS_USER_DATA_CONTRIBUTION_CONSENT_IMPLEMENTATION

## 9. Next Work

- Recommended next task: add persistent consent storage and app UI consent controls.
- Required approval before next task: DB migration, live server deployment, or UI/browser smoke.
