# HAEHAN Playwright AI Baseline

Status: LOCKED
Baseline ID: HAEHAN-PLAYWRIGHT-AI-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: 902f3e688014c151c13d01eac4b9f41d59cfcfab
Last updated: 2026-05-24

## 1. Purpose

This document locks the `playwright_ai` module contract. Browser automation and
AI-assisted planning must stay behind backend authentication, approval policy,
common tool runtime validation, and authenticated local-agent execution.

Playwright and CDP execution must be local-agent controlled, not server-side.

## 2. Responsibility

`playwright_ai` owns:

- local-only browser automation
- AI-assisted task planning for approved browser tasks
- approved browser task execution boundaries
- Playwright/CDP dry-run and live-stage separation
- screenshot/capture approval boundary
- redacted browser observation return
- prompt and secret redaction boundaries
- safe task result summary

## 3. Input Contract

Allowed inputs:

- approved browser task contract
- safe URL/action parameters
- AI prompt context without raw secrets
- local-agent execution context
- explicit live browser approval for live checks
- readonly dry-run browser discovery request

Rejected inputs:

- server-side browser execution request
- raw secret, token, cookie, session, password, OTP, or Authorization header
- credential/session/cookie extraction request
- unapproved browser write action
- local-agent bypass request
- dry-run request that would mutate external site or local app state

## 4. Output Contract

Allowed outputs:

- redacted observation
- approved screenshot/capture result
- safe task result summary
- failed safe error summary
- cancelled safe error summary
- dry-run readiness result

Forbidden outputs:

- raw prompt containing secrets
- raw token, cookie, session, password, OTP, or Authorization header
- browser credential material
- unredacted page content outside an approved result contract
- raw CDP websocket URL with sensitive query material

## 5. Execution Boundary

Required rules:

- Server must not run Playwright directly.
- Server must not control a user's local browser directly.
- Browser execution must be local-agent mediated.
- Dry-run checks must remain side-effect free.
- Live browser checks require explicit approval.
- AI planning must not bypass backend auth, approval, task queue, or local-agent
  dispatch rules.

## 6. Approval Boundary

Approval is required before:

- browser write action
- screenshot/capture outside an explicitly safe dry-run
- upload
- submit
- send
- delete
- payment
- transfer
- bid
- signature
- registration
- external site state change
- local file or local app state change

Unapproved high-risk browser tasks must not execute.

## 7. Redaction Boundary

The module must redact:

- prompt secrets
- tokens
- cookies
- sessions
- passwords
- OTP values
- Authorization headers
- raw CDP websocket URLs
- credential-like query parameters

Redaction failure is a security defect.

## 8. Forbidden Playwright/AI Behavior

Runtime Playwright/AI code must not:

- execute server-side Playwright
- extract credentials, cookies, sessions, passwords, OTP values, or auth headers
- execute unapproved write actions
- execute submit/upload/send/delete/payment/bid/signature without approval
- output raw prompt, secret, token, cookie, session, or credential material
- bypass local-agent dispatch
- mutate external site, local file, or local app state during dry-run gates
- use AI output as authorization or approval

## 9. Allowed Paths

Playwright/AI work may modify local browser adapters, CDP/Playwright dry-run
scripts, AI proxy tests, and browser runtime operating rules only when the task
explicitly approves those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md
docs/baseline/MODULE_BASELINE.md
tools/audits/agent/audit_playwright_ai_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_playwright_ai_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 10. Required Verification

Baseline verification:

```text
python tools/audits/agent/audit_playwright_ai_baseline_contract.py
python -m pytest tests/test_playwright_ai_baseline_contract.py -q
```

Runtime/browser verification:

```text
python tools/verify/dry_run_local_agent_cdp_attach.py
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

Live browser verification is separate and requires explicit approval.

## 11. Known WARN

- Real browser launch is a separate approved live/runtime stage.
- Real AI API verification is a separate approved live/runtime stage.
- Site-specific automation baselines are still needed.
- Long-running browser recovery, site blocking, and login expiry behavior need
  future criteria.

## 12. Baseline Change Rule

Any Playwright/AI change that weakens local-only execution, approval gating,
dry-run safety, prompt/secret redaction, or server-side execution prohibitions
must be handled as:

```text
playwright_ai baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

