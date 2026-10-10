# Worktree Dry-Run And Cross-App Impact Report - 2026-05-13

## Scope

Scope: `repo-worktree-cleanup`

This report covers the worktree cleanup standard, runtime artifact ignore
rules, worktree classification changes, and their relationship to other app and
site modules.

## Dry-Run Evidence

Command:

```powershell
python scripts\ops\pre_change_dry_run.py --scope repo-worktree-cleanup --reason "worktree cleanup classification and cross-app impact check" -- python -m pytest tests\test_worktree_change_index.py tests\test_codebase_layer_audit.py tests\test_common_operations_index.py tests\test_pre_change_dry_run.py tests\test_quality_gate.py -q --basetemp=C:\tmp\pytest_repo_worktree_cleanup_dryrun_escalated
```

Result:

- `28 passed`
- Latest evidence: `data/logs/pre_change_dry_run_latest.json`
- History evidence:
  `data/logs/pre_change_dry_runs/pre_change_dry_run_20260513_231540.json`
- Latest status: `ok`
- Scope: `repo-worktree-cleanup`
- Exit code: `0`

Additional checks:

```powershell
python scripts\quality_gate.py
python scripts\quality_gate.py --allow-existing-code-change
python scripts\ops\validate_common_operations_index.py
python -m pytest tests\test_app_realtime_check.py tests\test_realtime_audit.py tests\test_common_operations_index.py -q
python scripts\app_realtime_check.py --max-runs 1 --timeout 1 --audit-max-age-seconds 3600 --index-max-age-seconds 3600
```

Results:

- `quality_gate.py`: expected 34 errors because the existing dirty worktree has
  active-code modifications and no intentional approval flag.
- `quality_gate.py --allow-existing-code-change`: `errors: 0`, `warnings: 0`.
- Common operations index validation: passed, 8 sites.
- App realtime/audit/common-index tests: `9 passed`.
- Runtime app check: `degraded` because `api_health` and `cdp_browser` were not
  responding; `latest_dry_run`, `worktree_index`, and `audit_log_freshness`
  were all OK.

## Current Worktree Index

Latest summary:

| group | count |
| --- | ---: |
| changed files | 243 |
| deleted | 49 |
| modified | 47 |
| untracked | 147 |
| active_code | 92 |
| site_automation | 53 |
| test | 41 |
| doc_or_archive | 37 |
| contract_or_policy | 12 |
| audit_or_persistence | 8 |
| unknown layer | 0 |

Owner counts:

| owner | count |
| --- | ---: |
| repo | 119 |
| tests | 41 |
| docs | 25 |
| naver | 24 |
| eum | 16 |
| google | 9 |
| config | 4 |
| smartstore | 3 |
| hiworks | 1 |
| platform | 1 |

## Cross-App Relationship

Direct Python dependencies:

| source | relationship | impact |
| --- | --- | --- |
| `scripts/ops/worktree_change_index.py` | imports `scripts.ops.codebase_layer_audit.classify_path` | Classification changes affect worktree summaries and owner/category counts. |
| `scripts/ops/app_realtime_check.py` | reads `data/logs/pre_change_dry_run_latest.json` and `data/worktree_change_index_latest.json` | App health board depends on latest dry-run and index artifacts, not on implementation internals. |
| `tests/test_worktree_change_index.py` | imports `scripts.ops.worktree_change_index` | Regression coverage for worktree classification. |
| `tests/test_codebase_layer_audit.py` | imports `scripts.ops.codebase_layer_audit` | Regression coverage for layer classification. |
| `tests/test_pre_change_dry_run.py` | imports `scripts.ops.pre_change_dry_run` | Regression coverage for dry-run evidence recording. |

No active site module imports `worktree_change_index.py`,
`codebase_layer_audit.py`, or `pre_change_dry_run.py` directly. The relationship
to EUM, Hiworks, Naver, Google, SmartStore, and G2B is operational: their
workflow docs and common indexes require these tools before new work or commit
review.

Operational dependencies:

| app/site | dependency | impact |
| --- | --- | --- |
| EUM | `docs/eum_logic_reference_20260513.md`, status index | Uses common status/index rules; no runtime code impact. |
| Hiworks | completion report and common status index | Uses worktree index as completion evidence; no runtime code impact. |
| Naver | live safety policy and common operations index | Cleanup does not change robot/live safety behavior. Runtime `data/naver_*` artifacts are ignored by default. |
| SmartStore | logic reference explicitly calls `worktree_change_index.py` | Classification output is clearer; no submit/approval behavior change. |
| Google/YouTube | common operations and surface reports | Runtime catalog artifacts under `data/google_*` remain local unless intentionally promoted. |
| G2B | completion report and common operations index | Read-only policy unaffected; runtime evidence remains local. |
| App realtime checker | reads latest dry-run and worktree index | Confirmed it sees latest dry-run and worktree index as OK. |

## Risk Assessment

- Runtime behavior of site automations is not changed by the worktree cleanup
  itself.
- `.gitignore` now hides generated `data/` artifacts across all site apps. This
  reduces accidental commits but means intentional evidence must be promoted to
  `docs/reports/` or `tests/fixtures/`, or added explicitly with `git add -f`.
- Existing tracked `data/` files are not untracked or removed by `.gitignore`.
- Quality gate still blocks existing active-code modifications unless the
  operator intentionally passes `--allow-existing-code-change`.
- App realtime check degradation is environmental: local API and CDP were not
  responding during the check. Dry-run/index/audit evidence checks were OK.

## Next Handling Order

1. Review `contract_or_policy` changes first.
2. Review one site owner at a time.
3. Keep runtime artifacts local unless promoted.
4. Stage tests with the code or policy they verify.
5. Before commit, run `python scripts\quality_gate.py --staged --enforce`.

