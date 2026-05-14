# CDP Live State Fix - 2026-05-13

## Problem

`python scripts\cdp_daemon.py start` treated any live CDP port as if the
daemon itself was running. At the same time, `status` read the stale state file
and printed inactive, even though browser automation was usable.

## Fix

- Added a live CDP probe helper.
- `start` now distinguishes:
  - daemon-managed endpoint responding
  - external/live CDP endpoint responding while daemon state is inactive
- `status` now prints live endpoint, managed daemon state, browser usability,
  stale state details, and autostart status in one unambiguous block.

## Current State

- Live CDP: yes
- Endpoint: `http://127.0.0.1:9222`
- Browser usable: yes
- Managed daemon: no
- Google session: logged in

## Verification

```powershell
python -m pytest tests\test_cdp_daemon_status.py tests\test_google_surfaces.py -q --basetemp=tmp\pytest_cdp_google_status_final
python scripts\cdp_daemon.py status
python scripts\cdp_daemon.py start
python scripts\cdp_client.py google session-check
```

Result:

- `5 passed`
- `status` reports live CDP responding and managed daemon `no`
- `start` reports external/live CDP instead of claiming daemon-managed state
- Google session check is logged in
