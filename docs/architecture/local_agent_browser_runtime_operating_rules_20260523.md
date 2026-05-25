# Local Agent Browser Runtime Operating Rules

Date: 2026-05-23
Status: LOCKED

These rules lock the current local-agent browser execution logic. Any change
that weakens these rules must be treated as a security/governance change, not a
routine refactor.

## Locked Rules

1. CDP attach is local-only.
   - Allowed hosts: `127.0.0.1`, `localhost`, `::1`.
   - Remote, LAN, public, or server-side CDP hosts are forbidden.
   - The default CDP port is `9222`; non-default ports must still be loopback.

2. CDP discovery is read-only.
   - Allowed discovery endpoints: `/json/version`, `/json/list`.
   - First-phase discovery must not use cookie, storage, arbitrary runtime
     evaluation, click, type, submit, upload, download, or page mutation calls.

3. CDP output is redacted.
   - Do not output `webSocketDebuggerUrl`.
   - Do not output raw URL query strings, fragments, username, or password.
   - Do not output cookies, storage values, bearer tokens, API keys, or secrets.

4. Automated browser execution uses a dedicated profile.
   - Automated smoke/runtime execution must use the dedicated CDP daemon profile
     rather than a personal Chrome profile.
   - Existing-session attach remains inspection-only unless a later approval
     gate explicitly enables stronger behavior.
   - Headless/background execution is allowed only when the server task carries
     an explicit user-approved background marker such as
     `background_approved=True`. Without that marker, read-only browser work
     must run in visible mode or be rejected before opening a browser.
   - Login, credential issue, submit, publish, billing, IAM, API key, upload,
     send, edit, and delete workflows remain separate approval actions. A
     background approval marker does not downgrade those workflows to read-only.

5. Runtime state must not be written under `scripts/archive`.
   - `chrome_ui_monitor_state.json` is runtime state and must live under
     `data/runtime/`.
   - `scripts/archive/data/chrome_ui_monitor_state.json` is OUT_OF_SCOPE and
     must not be modified, staged, or used as an active write target.

6. Build/deploy boundaries remain separate.
   - CDP dry-run and browser smoke verification must not build installers,
     create portable ZIPs, run Docker deploys, push, or stage OUT_OF_SCOPE
     files.

7. Local audit logging is always-on.
   - Every local-agent connection, dispatch, browser open, block, failure, and
     result path must call the structured local audit logger.
   - The primary audit path is configurable with `HAEHAN_AGENT_AUDIT`.
   - If the primary audit path is not writable, the agent must write a
     `local_audit_write_failed` marker and the original safe event to a
     fallback audit path such as `HAEHAN_AGENT_AUDIT_FALLBACK`, repo `logs/`,
     or the OS temp directory.
   - Audit logs must remain redacted: no raw secrets, tokens, cookies, sessions,
     passwords, OTP values, API keys, auth headers, full page HTML, or raw local
     sensitive content.

## Required Gates

Before changing local-agent browser runtime behavior, run:

```text
python scripts/ops/dry_run_local_agent_cdp_attach.py
python -m pytest tests/test_local_agent_browser_runtime_operating_rules.py tests/test_local_agent_cdp_attach.py tests/test_dry_run_local_agent_cdp_attach.py -q
```

Live checks may start the dedicated CDP daemon only when explicitly approved.
After live checks, stop the daemon and confirm `git status --short` has no
OUT_OF_SCOPE mutation.
