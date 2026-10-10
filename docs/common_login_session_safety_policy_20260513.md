# Common Login Session Safety Policy

Updated: 2026-05-13

This policy applies to every site automation workflow, not only Naver.

## Rule

Login/session integrity must be verified before any live browser workflow
continues.

If a site auth helper reports any of the following, the workflow must stop:

- `different_user_logged_in`
- `session_user_mismatch`
- `account_mismatch`
- `wrong_user`
- `stale_session`
- `expired_session`
- `invalid_session`
- `login_required_after_restore`

Expected user and actual user mismatch is also a hard stop.

## Required Behavior

When a session integrity failure is detected:

1. Stop navigation, scan, prepare, and submit work.
2. Do not automatically retry with the same session.
3. Record `SITE_SESSION_INTEGRITY_BLOCKED` in realtime audit logs.
4. Require manual login/session confirmation before resuming.

## Work Pacing And Page Completion

Fast exploration after a valid login is allowed when the site is stable and no
security or monitoring signal appears. Speed is never the main success metric.

Operational priority:

```text
accuracy -> page completion -> audit evidence -> next page
```

Rules:

1. Finish one page/work surface before moving to the next page.
2. A page is not complete until its visible inputs, buttons, links, state-changing controls, required data, dry-run behavior, and audit artifacts are classified or explicitly deferred.
3. If the browser starts to feel monitored, guarded, challenged, or inconsistent, slow down or stop the live workflow and record why.
4. Do not continue broad exploration while any page has unresolved login/session, selector, data, or submit-gate uncertainty.
5. Accuracy and reproducible evidence are more important than traversal speed.

## Implementation

Common module:

- `scripts/site_engine/site_session_safety.py`

Current integration:

- `scripts/naver/common/content.py` calls the common guard after `ensure_naver_login`.

Every future site auth helper should reuse this module before live actions are
allowed.

## Full Business Workflow Development

Login/session safety does not mean workflows stop at read-only discovery.
For business use, every workflow should be developed through prepare,
approval, execute, verify, and log stages.

State-changing execution remains blocked until explicit user approval, but the
execute path should still be implemented and gated.

Reference:

- `docs/business_workflow_full_development_policy_20260513.md`

## Common Security Module

All live site modules must use the common security/redaction layer before
writing logs, audit metadata, DB-safe records, or CLI status output.

Common modules:

- `security_utils.py`: sensitive-key detection, email/identifier masking,
  nested dict/list/tuple redaction, inline token/RRN/card masking.
- `scripts/common/security.py`: compatibility wrapper for the existing
  `scripts.common.security` import path.
- `logging_utils.py`: compatibility facade that delegates to `security_utils.py`.
- `scripts/auth/credentials.py`: encrypted credential storage; CLI `get` and `list`
  must show only masked IDs and masked password previews.
- `scripts/auth/local_user_secret_store.py`: per-user local OS keyring storage for
  approved secret material such as OAuth client JSON. Commands return only
  status and `local-secret://...` references, never raw secret values.

Rules:

1. Do not log raw password, token, cookie, session, storage state, API key,
   client secret, OTP, authorization header, or private key values.
2. Do not receive raw login IDs, passwords, OTPs, recovery codes, or other
   login secrets in chat or agent instructions, even if the user offers them or
   asks to change the rule. The user may decide to log in, but the user enters
   credentials directly in the browser or an approved local secret store. The
   agent role is limited to opening the login surface, detecting completion,
   and saving a domain-scoped session artifact.
3. Do not print raw login IDs in CLI status output unless the command's only
   purpose is interactive credential entry by the user.
4. Redaction must be recursive across mappings, lists, and tuples.
5. New site modules must import the common helpers instead of defining their
   own sensitive-key list.
6. If a site needs a stricter rule, add it to `security_utils.py` first and
   then reuse it from the site-specific module.
7. User-specific OAuth/API secrets must be passed by approved local secret
   reference when possible. The reference may be logged; the resolved value must
   not be logged, printed, or committed.

## Login Strategy Classification

Universal login must be opt-in, not fallback-by-default. Each registered site
uses one explicit strategy:

| strategy | behavior |
| --- | --- |
| `registered_only` | Use only the site-specific login function. |
| `registered_then_universal` | Use universal login only after site-specific login fails and the site explicitly allows it. |
| `manual_only` | Skip credential login and wait for user-visible login detection. |

Current baseline:

- EUM, Naver, Google: `registered_only`
- Hiworks: `manual_only`

Universal login is unsafe for sites with hidden templates, role-specific login
tabs, duplicated fields, CAPTCHA/robot detection, or security-sensitive account
flows unless that site has explicit selector evidence and test coverage.
