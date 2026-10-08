# SmartStore Logic Reference

Updated: 2026-05-13

This document records the reusable SmartStore automation baseline. It should be
checked before changing SmartStore code or before reusing the pattern for
another site.

## Scope

Site id: `smartstore`

Primary entry points:

- `scripts/smartstore/router.py`
- `scripts/smartstore/actions.py`
- `scripts/smartstore/__init__.py`
- `scripts/naver/smartstore/__init__.py`
- `scripts/naver/smartstore/product.py`
- `scripts/naver/smartstore/general_product.py`
- `scripts/naver/smartstore/bulk.py`

## Current Baseline

The baseline is `complete_baseline`, not `complete_live`.

Implemented baseline items:

- Static action catalog: `python scripts/entry/cdp_cli.py smartstore actions catalog`
- Product prepare dry-run: `python scripts/entry/cdp_cli.py smartstore prepare product --data=<json> --dry-run`
- Approval-gated submit dry-run: `python scripts/entry/cdp_cli.py smartstore submit product --data=<json> --dry-run --approved --confirm=SMARTSTORE_APPROVED_SUBMIT`
- Product list router fix: `smartstore product list` now calls `NaverSmartStore.list_products()`.
- Realtime audit record for SmartStore submit/dry-run records.

Live SmartStore exploration is paused after Naver robot detection. Prefer static
catalog and dry-run evidence before any live action. Do not assume an official
Naver API is available for these workflows; use stored artifacts, manual
exports, and conservative browser reads.

## Risk Contract

Read actions:

- Dashboard open
- Product list
- Order list
- Settlement list
- Review/inquiry list
- Store info
- Stats collect

Prepare actions:

- General product field preparation
- Group product field preparation
- Bulk product validation/preparation

Approval actions:

- General product save
- Group product save
- Bulk product save
- Review reply send

Every approval action requires:

```text
--approved --confirm=SMARTSTORE_APPROVED_SUBMIT
```

Dry-run is the default unless `--execute` is explicitly passed. A prepare command
cannot perform a live save; live save must go through `smartstore submit`.

## Data And Indexes

Generated runtime artifacts:

- `data/smartstore_action_catalog_latest.json`
- `data/smartstore_prepare_plan_latest.json`
- `data/smartstore_submit_latest.json`
- `data/smartstore_submits/*.json`

Existing persistence:

- `scripts/naver/smartstore/bulk.py` creates `smartstore_register_log`.
- Indexes: `idx_ssreg_ts`, `idx_ssreg_ok`.

## Operating Rule

Before new SmartStore work:

1. Run `python scripts\ops\worktree_change_index.py`.
2. Check `docs/worktree_management_index.md`.
3. Check this document.
4. Generate or refresh `smartstore actions catalog`.
5. Run a dry-run before any approved live submit.

If an error occurs, regenerate the worktree index, inspect the file owner and
category in `data/worktree_change_index_latest.json`, then resume from the
smallest affected SmartStore workflow.

## Live Safety

Common Naver live safety policy:

- `docs/naver_live_safety_policy_20260513.md`
- `scripts/naver/common/live_safety.py`
- `docs/common_login_session_safety_policy_20260513.md`
- `scripts/site_engine/site_session_safety.py`

Live browser actions require `--live-ok`. Multi-target Naver scans require both
`--live-ok` and `--allow-multi-target`.

Login/session mismatch is a common hard stop. SmartStore dashboard and product
registration open paths call the common session integrity guard after
`ensure_naver_login`.
