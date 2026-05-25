# Server Deploy Verification - 2026-05-25

## Scope

Reflected the latest `master` on the production server and verified the server
as the final runtime baseline.

## Baseline

- Local HEAD before deploy: `d0012b69bf638d190134423ad86da7d37a6f1675`
- Remote `origin/master`: `d0012b69bf638d190134423ad86da7d37a6f1675`
- Server HEAD after deploy: `d0012b69bf638d190134423ad86da7d37a6f1675`
- Final runtime baseline: server-first

## Server Worktree Handling

Before pulling, the server worktree had local changes in:

```text
.gitignore
ai_orchestrator/local_agent_actions.py
ai_orchestrator/local_agent_risk_policy.py
ai_orchestrator/tests/test_local_agent_risk_policy.py
local_agent/websocket_client.py
tests/test_web_open_url_readonly_ws_result.py
verify_live_browser_readonly_dispatch.py
```

Those changes were preserved as:

```text
stash@{0}: On master: pre-deploy-server-dirty-20260525
```

The server still has one untracked operational override:

```text
docker-compose.override.yml
```

It is a server-only secret env attachment and was intentionally left
uncommitted.

## Deployment Actions

```text
git push
ssh haehan-app "git fetch origin"
ssh haehan-app "git stash push -u -m 'pre-deploy-server-dirty-20260525'"
ssh haehan-app "git merge --ff-only origin/master"
ssh haehan-app "docker compose build ai-orchestrator-api admin-web"
ssh haehan-app "docker compose up -d --no-deps ai-orchestrator-api admin-web"
```

Nginx was not restarted.

## Smoke Verification

```text
GET /orchestrator/api/v1/health -> 200
GET /orchestrator/admin-web/ -> 200
GET /orchestrator/admin-web/local-agents -> 200
GET /orchestrator/api/v1/auth/me -> 401
```

The `401` on `auth/me` is expected for an unauthenticated request.

## Server Stress Verification

All checks were run on the server through nginx with `Host: haehan-ai.kr`.

```text
ab -n 100 -c 30 /orchestrator/api/v1/health
Complete requests: 100
Failed requests: 0
Requests per second: 275.49
Longest request: 200 ms

ab -n 100 -c 30 /orchestrator/admin-web/
Complete requests: 100
Failed requests: 0
Requests per second: 88.69
Longest request: 550 ms

ab -n 100 -c 30 /orchestrator/admin-web/local-agents
Complete requests: 100
Failed requests: 0
Requests per second: 88.30
Longest request: 563 ms
```

## Post-Deploy Logs

- `admin-web`: started and ready, no new Server Action runtime error in the
  post-deploy log window.
- `ai-orchestrator-api`: started successfully, health requests returned 200.

## Final Verdict

PASS_SERVER_DEPLOY_VERIFICATION

The server is now the active baseline for the latest app structure and
operating rules.

## Live Lock

The server smoke, server stress, and post-deploy log checks were rerun before
locking this report. No new runtime error was observed in the live verification
window.
