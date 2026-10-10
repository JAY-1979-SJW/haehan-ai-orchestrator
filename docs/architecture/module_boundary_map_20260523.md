# Module Boundary Map

Date: 2026-05-23
Status: LOCKED

This map defines the current operational module boundaries. It does not move
files by itself; it locks ownership and required gates so future changes cannot
silently cross module boundaries.

Source of truth:

```text
configs/module_boundaries.json
tools/audits/app/audit_module_boundaries.py
tests/test_module_boundaries.py
```

## Modules

| Module | Owner | Layer | Gate |
|---|---|---|---|
| repo_guard | platform | L2 | required_local_gate_wiring |
| local_agent_browser_runtime | local-agent | L4 | local_agent_browser_runtime_rules |
| desktop_runtime | desktop | L10 | desktop_security_boundary |
| admin_web | frontend | L9 | release_preflight |
| portable_install | release | L10 | portable_install |
| server_api | backend | L8 | live_agent |
| site_automation | automation | L5 | codebase_layer_audit |
| legacy_root_quarantine | platform | L12 | codebase_layer_audit |

## Rules

- GitHub Actions is limited to the approved `.github/workflows/ci.yml`
  (introduced 2026-09-29, commit a941e09a, user-approved reversal of the prior
  "no GitHub Actions" decision) and `.github/workflows/desktop-release.yml`
  (2026-10-07, user-approved desktop app release build); any other workflow
  file is still forbidden.
  Required checks remain local scripts plus pre-commit/pre-push hooks, reused
  by ci.yml itself (`tools/verify_change.py`).
- Browser runtime state must stay under `data/runtime/`, not under
  `scripts/archive/data/`.
- Legacy root Python scripts are accepted residuals only. New root-level Python
  scripts must be rejected unless a governance document and gate update are
  included in the same change.
- Cross-module changes must run the gate listed for each affected module.
