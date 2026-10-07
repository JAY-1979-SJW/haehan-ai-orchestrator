# Local Agent CDP Attach Dry-Run Design

Date: 2026-05-23

## Goal

Verify that the desktop/local-agent can safely inspect or use a local browser
through Chrome DevTools Protocol before enabling full remote browser execution.
This stage is a design and dry-run gate. It does not launch Chrome, attach to a
browser, navigate, click, type, download, build, deploy, or push.

## Modes

- `existing`: attach only to an already-running loopback CDP endpoint. The
  local agent must not start Chrome in this mode.
- `dedicated`: use a dedicated Chrome profile managed by the existing
  `scripts/browser/cdp/cdp_daemon.py` flow. This is preferred for automated execution
  because it avoids mixing automation state with a user's personal profile.

## Boundary

- Only loopback CDP endpoints are allowed: `127.0.0.1`, `localhost`, or `::1`.
- The default port is `9222`; any other port must be explicitly supplied and in
  range `1..65535`.
- Remote hosts, LAN hosts, file URLs, debugger websocket URLs, credentials in
  URLs, cookies, local storage, session storage, and raw query strings are out
  of scope for discovery output.
- Discovery may read `/json/version` and `/json/list` only.
- First-phase attach is read-only: no click, type, submit, upload, download,
  cookie read, storage read, arbitrary `Runtime.evaluate`, or page mutation.

## Secret Handling

Dry-run output may include only:

- Browser family/protocol version from `/json/version`.
- Tab count.
- Tab title truncated to 120 characters.
- URL summary with scheme, origin, and boolean flags for path/query/fragment.

Dry-run output must not include:

- `webSocketDebuggerUrl`
- raw URL query or fragment
- username or password components
- cookies or storage values
- authorization headers or bearer tokens

## Execution Sequence

1. Run the static dry-run gate.
2. If it passes, optionally probe an existing loopback CDP endpoint.
3. If no endpoint exists, start a dedicated CDP daemon in a separate step.
4. Only after a successful probe, allow a separate live smoke to open a public
   URL in the dedicated browser.

## Current Decision

Use the dedicated profile path for automated execution. Existing-session attach
remains available for inspection only and must stay read-only until a separate
approval gate enables stronger actions.
