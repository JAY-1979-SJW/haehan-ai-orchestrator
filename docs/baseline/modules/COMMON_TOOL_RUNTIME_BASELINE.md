# HAEHAN Common Tool Runtime Baseline

Status: LOCKED
Baseline ID: HAEHAN-COMMON-TOOL-RUNTIME-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: b1e2821315364aba226276a19d49c9da69b76077
Last updated: 2026-05-24

## 1. Purpose

This document locks the `common_tool_runtime` module contract. This module is
the shared rail for executable tool tasks. It defines task and result contracts,
risk level, approval requirement, forbidden field rejection, safe execution
metadata, and redacted result metadata.

The common runtime classifies and validates execution requests; it must not
execute browser, file, site, or AI work directly.

## 2. Responsibility

`common_tool_runtime` owns:

- task contract
- result contract
- risk level
- approval requirement
- forbidden field rejection
- safe execution metadata
- redacted result metadata
- safe error summary for rejected tasks
- common validation before site/browser/file/AI modules execute work

## 3. Input Contract

Allowed inputs:

- normalized tool task request
- execution context
- tool name
- action
- parameters
- risk classification
- approval state
- caller identity metadata already validated by backend boundaries

Rejected inputs:

- raw Authorization header
- raw secret, token, cookie, session, password, or OTP
- sensitive credential field
- browser execution shortcut
- direct file or external site mutation shortcut
- approval-required task without approval
- site-specific task shape that bypasses the common contract

## 4. Output Contract

Allowed outputs:

- accepted task contract
- rejected task contract
- risk level
- approval required flag
- safe execution metadata
- redacted result metadata
- safe error summary

Forbidden outputs:

- raw auth header
- raw secret, token, cookie, session, password, OTP, or credential material
- executable payload that skipped forbidden field checks
- site-specific private data outside the redacted result contract

## 5. Risk And Approval Boundary

Required rules:

- Readonly low-risk tasks may be marked safe only when they do not mutate
  external site, local file, or local app state.
- Browser write actions require approval.
- File upload, write, delete, or external submission require approval.
- Payment, transfer, bid, signature, and registration require approval.
- Screenshot/capture requires approval unless explicitly classified as safe
  dry-run.
- Approval-required risk must not be bypassed by callers.

## 6. Forbidden Field Boundary

The common runtime must reject payloads containing:

- Authorization
- bearer token
- access token
- refresh token
- device token
- cookie
- session
- password
- OTP
- API key
- secret

Forbidden field rejection must occur before execution is delegated to any
browser, file, site, AI, or local-agent adapter.

## 7. Execution Boundary

`common_tool_runtime` must not:

- execute browser work directly
- execute AI work directly
- mutate files directly
- mutate external sites directly
- call Playwright directly
- call CDP directly
- duplicate site-specific workflow logic
- accept raw auth header forwarding

The module returns validated contracts and safe metadata; execution happens in
approved downstream modules only.

## 8. Allowed Paths

Common tool runtime work may modify the shared runtime contract, common runtime
tests, and common runtime audit scripts only when the task explicitly approves
those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/agent/audit_common_tool_runtime_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_common_tool_runtime_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 9. Required Verification

Baseline verification:

```text
python tools/audits/agent/audit_common_tool_runtime_baseline_contract.py
python -m pytest tests/test_common_tool_runtime_baseline_contract.py -q
```

Runtime/common contract verification:

```text
python tools/audits/agent/audit_common_tool_runtime.py
python -m pytest tests/test_common_tool_runtime.py -q
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

## 10. Known WARN

- Site-specific tool profiles still need individual criteria on top of this
  common contract.
- Long-running execution, retry, cancellation, and recovery policy need future
  module-specific criteria.
- Live browser/site/AI execution checks are separate approved stages.

## 11. Learning Notes

Task contract means the normalized input shape that a tool is allowed to
receive.

Result contract means the safe output shape a tool is allowed to return.

Risk level tells the system whether a task is readonly, approval-required, or
blocked.

Approval required flag prevents dangerous actions from entering execution before
approval.

Forbidden field rejection prevents secrets and credentials from being smuggled
through a generic task payload.

## 12. Baseline Change Rule

Any common runtime change that weakens task/result contracts, risk level,
approval requirement, forbidden field rejection, redaction, or execution
boundaries must be handled as:

```text
common_tool_runtime baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

