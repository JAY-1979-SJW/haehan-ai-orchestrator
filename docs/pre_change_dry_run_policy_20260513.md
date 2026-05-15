# Pre-Change Dry-Run Policy

Updated: 2026-05-13

Before changing code, run a dry-run or current-behavior check for the affected
scope. The goal is to know the starting behavior before modifying it.

## Required Flow

```text
worktree index -> pre-change dry-run -> code update -> post-change dry-run/test -> quality gate
```

## Command

Use:

```powershell
python scripts\ops\pre_change_dry_run.py --scope <scope> --reason "<why>" -- <dry-run command>
```

Examples:

```powershell
python scripts\ops\pre_change_dry_run.py --scope smartstore --reason "router safety update" -- python -m pytest tests\test_smartstore_actions.py -q
python scripts\ops\pre_change_dry_run.py --scope naver --reason "live safety policy update" -- python -m pytest tests\test_naver_live_safety.py -q
```

Evidence is written to:

- `data/logs/pre_change_dry_run_latest.json`
- `data/logs/pre_change_dry_runs/*.json`

The realtime audit event is:

- `PRE_CHANGE_DRY_RUN_RECORDED`

## Exceptions

If no executable dry-run exists yet, record a current-behavior check instead,
such as a focused unit test, static catalog generation, schema validation, or a
command that proves the current guard blocks unsafe live execution.

Do not treat this as optional. If the dry-run cannot be run, document why before
editing and add the missing dry-run path as part of the change.
