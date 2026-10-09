# HAEHAN Release Preflight Baseline

Status: LOCKED
Baseline ID: HAEHAN-RELEASE-PREFLIGHT-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: c865887e6c53e6f66fa14a58c3f58772a4492fce
Last updated: 2026-05-24

## 1. Purpose

This document locks the `release_preflight` module contract. Release preflight
is the no-build, no-deploy, no-installer readiness check before release work. It
classifies static risks and reports whether a later release/build stage may be
considered.

Release preflight is not a build stage.

## 2. Responsibility

`release_preflight` owns:

- no-build release readiness check
- admin-web static checks
- UI residue audit
- secret scan classification
- module gate verification
- OUT_OF_SCOPE preservation
- dirty tree classification
- PASS/WARN/FAIL release readiness summary
- release readiness decision

## 3. Input Contract

Allowed inputs:

- source tree
- package/build script metadata
- static audit rules
- test fixtures
- git status
- known OUT_OF_SCOPE file list
- secret scan findings for classification

Rejected inputs:

- request to build
- request to deploy
- request to run Docker
- request to create installer exe
- request to create portable zip artifact
- request to push
- request to install dependencies
- request to print secret values
- request to clean or stage OUT_OF_SCOPE files

## 4. Output Contract

Allowed outputs:

- PASS/WARN/FAIL summary
- secret finding classification
- UI residue WARN/FAIL classification
- module gate result summary
- dirty tree classification
- release readiness decision
- safe warning for environment-only issues

Forbidden outputs:

- raw secret, token, cookie, session, password, OTP, or Authorization header
- build artifact
- installer exe
- portable zip artifact
- deploy result
- Docker state mutation
- pushed commit

## 5. Static Verification Boundary

Required rules:

- Preflight may inspect files and scripts.
- Preflight may run static tests and audits.
- Preflight may classify git status.
- Preflight may classify secret scan hits.
- Preflight must not run `npm run build`.
- Preflight must not run `electron-builder`.
- Preflight must not run `pyinstaller`.
- Preflight must not deploy or restart servers.
- Preflight must not run Docker build, pull, up, restart, or deploy.

## 6. Secret Scan Boundary

Required rules:

- Secret scan findings must be classified.
- Test constants, masking strings, and blocked-pattern test fixtures may be
  PASS when clearly non-secret.
- Active-source raw secrets are FAIL.
- Secret values must not be printed in reports.
- Secret scan uncertainty must be WARN or FAIL, not hidden.

## 7. UI Residue Boundary

Required rules:

- UI residue audit must classify findings as PASS, WARN, or FAIL.
- Known WARN findings must remain visible until a cleanup stage is approved.
- UI residue cleanup must not run during preflight unless explicitly approved.
- admin-web/node_modules recovery must not be done during preflight unless
  explicitly approved.

## 8. Environment WARN Boundary

Environment-only findings may be WARN when they do not indicate app code risk.

Examples:

- Docker CLI missing
- optional local tool missing
- live server unavailable during static preflight

Environment WARN must be reported separately from security FAIL.

## 9. Forbidden Release Preflight Behavior

Release preflight code must not:

- run `npm run build`
- run `electron-builder`
- run `pyinstaller`
- run Docker build/up/pull/restart
- deploy or restart server
- create installer exe
- create portable zip artifact
- push
- install dependencies
- print raw secrets
- clean, modify, stage, or commit OUT_OF_SCOPE files

## 10. Allowed Paths

Release preflight work may modify release preflight scripts, UI residue audit
helpers, static secret scan helpers, and focused release preflight tests only
when the task explicitly approves those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/RELEASE_PREFLIGHT_BASELINE.md
docs/baseline/MODULE_BASELINE.md
scripts/ops/audit_release_preflight_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_release_preflight_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 11. Required Verification

Baseline verification:

```text
python scripts/ops/audit_release_preflight_baseline_contract.py
python -m pytest tests/test_release_preflight_baseline_contract.py -q
```

Preflight command identification:

```text
python tools/quality/module_quality_gate.py --module release_preflight --dry-run
```

Required repository verification:

```text
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

Actual release_preflight execution is separate and requires explicit approval
when environment-dependent checks may run.

## 12. Known WARN

- Actual release_preflight full execution is a separate approved stage.
- Actual build is a separate approved stage.
- Actual deploy and push are separate approved stages.
- Docker CLI absence may be an environment WARN, not app failure.

## 13. Learning Notes

Preflight differs from build because it checks readiness without creating
artifacts.

Secret scan classification matters because test fixtures and masked strings are
different from live secrets.

UI residue WARN/FAIL classification keeps old UI remnants visible without
forcing cleanup inside unrelated work.

Dirty tree classification prevents accidental staging or release from mixed
work.

Docker missing is often an environment warning during static preflight, not a
code defect.

## 14. Baseline Change Rule

Any release preflight change that weakens no-build behavior, secret
classification, UI residue visibility, OUT_OF_SCOPE preservation, or
build/deploy separation must be handled as:

```text
release_preflight baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

