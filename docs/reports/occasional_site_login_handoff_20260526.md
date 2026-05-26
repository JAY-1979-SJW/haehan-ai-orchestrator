# Occasional Site Login Handoff

Status: completed
Date: 2026-05-26
Final location: server baseline

## Scope

Added a safe login handoff for one-time or infrequently used sites without
requiring full site-tool development.

## Contract

- Open only the approved entry URL through local-agent `web_open_url_readonly`.
- User enters credentials, OTP, certificate, or security prompts directly.
- Agent does not type, replay, store, export, or report credentials.
- Agent may perform only read-only session checks using non-secret indicators.
- Any Save, Submit, Consent, Publish, Delete, payment, permission grant, or
  other state change remains a separate final user approval point.
- If the site becomes repeated or business-critical, it must be promoted to a
  registered site module before broader automation.

## Verification

- `python -m pytest tests\test_site_sso_subdomain_runtime.py tests\test_site_work_function_baseline.py -q`
- `python scripts\ops\audit_site_sso_subdomain_runtime_baseline.py`
