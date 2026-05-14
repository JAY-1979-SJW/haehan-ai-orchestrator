# Login Strategy Classification - 2026-05-13

## Problem

Universal login fallback can misclassify site-specific login pages. In the EUM
case, the site-specific login path failed to find a stable field and
`universal_login()` selected unstable selectors such as `input:nth-of-type(...)`.
That produced `field_not_ready` and stopped the workflow.

This can happen on any site with dynamic tabs, hidden login templates, duplicate
inputs, or role-specific login pages.

## Classification

Every registered site now has a login strategy:

| strategy | meaning | universal fallback |
| --- | --- | --- |
| `registered_only` | Use only the site-specific login function. | Blocked |
| `registered_then_universal` | Try site-specific login, then universal login if allowed. | Allowed |
| `manual_only` | Do not use credentials; open and monitor user login. | Blocked |

Current assignment:

| site | strategy | reason |
| --- | --- | --- |
| `eum` | `registered_only` | Role-specific WEBLOG page and duplicate/hidden inputs make universal fallback unsafe. |
| `naver` | `registered_only` | Robot/security challenge handling must stay in Naver-specific auth. |
| `google` | `registered_only` | 2FA/account security should stay in Google-specific auth. |
| `hiworks` | `manual_only` | Current baseline uses user-visible login monitoring. |

## Code Changes

- `scripts/site_registry.py`
  - Added `SiteSpec.login_strategy`.
  - Classified EUM/Naver/Google/Hiworks.
- `scripts/site_access.py`
  - Added login strategy constants.
  - Universal fallback now runs only for `registered_then_universal`.
  - `manual_only` skips credential checks.
  - Dry-run output now prints the active login strategy.
- `tests/test_site_access_login_flow_helpers.py`
  - Added regression coverage for strategy defaults, universal fallback opt-in,
    and manual-only credential skipping.

## Verification

```powershell
python -m pytest tests\test_site_access_login_flow_helpers.py tests\test_site_session_safety.py tests\test_eum_router_work.py -q --basetemp=C:\tmp\pytest_login_strategy_policy_final2
python -m py_compile scripts\site_registry.py scripts\site_access.py
$env:SITE_DRY_RUN='1'; python -m scripts.site_access eum
$env:SITE_DRY_RUN='1'; python -m scripts.site_access hiworks
```

Results:

- Tests: `20 passed`
- Compile: passed
- EUM dry-run: `registered_only`, universal fallback blocked
- Hiworks dry-run: `manual_only`, credential check skipped

## Next Step

Fix EUM site-specific login selector readiness. The universal fallback is now
contained, so future EUM failures should point to the EUM auth module directly
instead of being masked by generic selector discovery.

