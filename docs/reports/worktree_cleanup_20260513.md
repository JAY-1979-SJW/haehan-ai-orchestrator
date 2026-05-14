# Worktree Cleanup Report - 2026-05-13

## Scope

This cleanup standardized the dirty worktree classification without deleting,
reverting, or moving user changes.

## Applied Changes

- Added a runtime artifact ignore baseline for generated `data/` outputs.
- Clarified the worktree file placement and promotion standard.
- Classified repository config files such as `.gitignore` as
  `contract_or_policy`.
- Classified root shared helpers, legacy root tests, and root one-off probes so
  the worktree index no longer reports `UNKNOWN` files.
- Added tests for the new worktree classification rules.

## Result

Before cleanup, the latest worktree index reported:

| metric | count |
| --- | ---: |
| changed files | 379 |
| untracked files | 284 |
| runtime artifacts | 138 |
| unknown layer | 15 |

After cleanup:

| metric | count |
| --- | ---: |
| changed files | 242 |
| untracked files | 146 |
| runtime artifacts in worktree index | 0 |
| unknown layer | 0 |

The count dropped because generated `data/` files are now ignored by default.
Tracked `data/` files remain tracked by Git, and intentional generated evidence
can still be promoted with `git add -f` after review.

## Remaining Review Groups

The remaining worktree should be handled in this order:

1. `contract_or_policy`: `.gitignore`, configs, gates, schemas, security, and
   common indexes.
2. `site_automation`: one site owner at a time.
3. `active_code`: generic browser, router, and helper modules.
4. `test`: stage with the code it proves.
5. `doc_or_archive`: stage with the behavior or status it documents.

Root-level one-off scripts such as `debug_*.py`, `check_*.py`, `close_*.py`,
`list_tabs.py`, and `eum_docs.py` are classified as archive/probe candidates.
They should be moved to `scripts/archive/debug/` only after confirming they are
not active entry points.

## Verification

```powershell
python -m pytest tests\test_worktree_change_index.py tests\test_codebase_layer_audit.py -q
python -m py_compile scripts\ops\worktree_change_index.py scripts\ops\codebase_layer_audit.py
python scripts\ops\worktree_change_index.py
```

Results:

- `16 passed`
- `py_compile` passed
- Worktree index regenerated at `data/worktree_change_index_latest.json`

