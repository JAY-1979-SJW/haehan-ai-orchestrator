# Runtime Function Check Guideline

## Goal

Verify the real runtime path before release:

server -> local agent -> local browser -> public web page -> result returned to server.

The first functional target is opening Google and Naver pages from a server-issued task. Login automation is out of scope for this stage. If an existing browser session is already logged in, the check may report the session state, but it must not type credentials or bypass MFA.

## Operating Principles

- Function first: prove the runtime path before refactoring, committing, or expanding gates.
- Keep the path narrow: server dispatch, local agent receive, browser open, page observe, result return.
- Use visible browser by default so the user can confirm what happened.
- Never print raw tokens, registration codes, passwords, cookies, Authorization headers, or mail/account content.
- Do not automate login. Existing session detection is allowed; credential input is not.
- Treat "login required" as a session-state result, not a functional failure, when the page opens correctly.
- Split failures by boundary before changing code.
- Do not build installers, deploy, push, or mutate OUT_OF_SCOPE files during functional checks.

## Check Sequence

1. Review previous records.
   - Browser worker logs
   - Task dispatch logs
   - CDP/Chrome watchdog records
   - Naver/Google inspection records
   - Approved browser instruction logs

2. Verify current server-local health.
   - Server health
   - Local credential status
   - WebSocket auth
   - Task queue creation
   - Worker receive/result return

3. Verify public browser open.
   - `https://www.google.com/`
   - `https://www.naver.com/`

4. Verify Naver session state only.
   - Open a Naver page that can indicate login state.
   - Report only one of: logged-in session detected, login required, blocked/unknown.
   - Do not print mail titles, sender data, account names, or page body.

5. Report by boundary.
   - Server dispatch
   - Local worker receive
   - Browser runtime
   - Page access
   - Session-state detection
   - Result return

## Verdicts

- `PASS_SERVER_LOCAL_PUBLIC_BROWSER_OPEN`
- `PASS_SERVER_LOCAL_NAVER_SESSION_DETECTED`
- `WARN_NAVER_LOGIN_REQUIRED_MANUAL_SESSION`
- `FAIL_SERVER_LOCAL_DISPATCH_BROKEN`
- `FAIL_LOCAL_BROWSER_RUNTIME_BROKEN`
- `FAIL_RESULT_RETURN_BROKEN`

## Prohibited During This Check

- Commit or push
- Installer or portable build
- Docker/server deploy unless separately approved
- Automatic login or credential entry
- Secret value output
- Account/mail content output
- OUT_OF_SCOPE file modification
