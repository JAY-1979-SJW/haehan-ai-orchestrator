# Live Parallel Task Dispatch Verification - 2026-05-25

## Scope

Server baseline: `212d103798256e064f1c6a55ecbfed73250c2d31`

Verified path:

```text
server concurrent task creation
-> authenticated temporary local-agent registration
-> local-agent WebSocket dispatch
-> local ws_noop execution
-> server final task state
```

## Findings

- Initial failure was not a parallel-submission failure. The live helper wrote
  temporary admin users to the retired server path, which caused `401`.
- After fixing the auth file path, the next failure was stale local-agent
  registration after server restart. The live smoke now creates a temporary
  registration code and temporary local agent for each verification run.
- True dispatch defect found: the server pushed multiple queued tasks
  back-to-back to one WebSocket connection, while the local client expects
  `task -> running_ack -> result`. This could strand delivered/running tasks.
- Fix applied: one WebSocket session receives at most one active task at a
  time; the server pushes the next queued task after the previous result.

## Verification

Local verification:

```text
python -m py_compile ai_orchestrator\local_agent_router.py verify_live_task_dispatch.py scripts\ops\live_parallel_task_dispatch_smoke.py
python -m pytest ai_orchestrator\tests\test_local_agent_ws.py -q
python scripts\required_quality_gate.py
```

Result:

```text
test_local_agent_ws.py: 56 passed
required_quality_gate: PASS_REQUIRED_QUALITY_GATE
```

Server deployment:

```text
git pull --ff-only
docker compose build ai-orchestrator-api
docker compose up -d --no-deps ai-orchestrator-api
```

Server health:

```text
HEAD=212d103798256e064f1c6a55ecbfed73250c2d31
ai-orchestrator-api: healthy
GET /api/v1/health: {"status":"ok","service":"haehan-ai-orchestrator"}
```

Live task dispatch:

```text
python verify_live_task_dispatch.py --temp-admin --timeout 70
RESULT=PASS_LIVE_TASK_DISPATCH
```

Live parallel dispatch:

```text
python scripts\ops\live_parallel_task_dispatch_smoke.py --temp-admin --count 5 --concurrency 5 --timeout 90
parallel task create: count=5/5 concurrency=5
parallel task final: completed=5/5 failed=0
RESULT=PASS_LIVE_PARALLEL_TASK_DISPATCH
```

## Locked Rule

Concurrent server submissions are supported. A single local-agent process
executes them sequentially without loss. Actual simultaneous local execution is
not claimed for one agent; it requires multiple registered agents or a separate
approved multi-worker local-agent design.
