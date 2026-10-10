# Common Operations Index

Updated: 2026-05-13

This is the first document to check before starting a new site or homepage
operation. It connects the worktree rules, site status, security audit, dry-run
requirements, and next-action order.

Machine-readable index:

- `configs/common_operations_index.json`

## Mandatory Flow

```text
worktree index -> reference check -> pre-change dry-run -> scoped work -> verify -> log -> commit
```

Before new work:

1. Run `python scripts\ops\worktree_change_index.py`.
2. Read `docs/worktree_management_index.md`.
3. Read this document and `configs/common_operations_index.json`.
4. Pick one owner scope, such as `homepage`, `hiworks`, `naver`, `google`, or `eum`.
5. For code changes, record pre-change evidence with `scripts\ops\pre_change_dry_run.py`.
6. Do not stage unrelated dirty files.

## Common Gates

| Gate | Required When | Command Or Rule |
| --- | --- | --- |
| Worktree index | New work, error triage, before commit | `python scripts\ops\worktree_change_index.py` |
| Pre-change dry-run | Code or deploy behavior change | `python scripts\ops\pre_change_dry_run.py --scope <scope> --reason "<why>" -- <command>` |
| Quality gate | Before commit/deploy when active code changed | `python tools\quality\quality_gate.py` |
| Approval gate | Send, submit, publish, upload, delete, billing, IAM, deploy | Site-specific `--approved` and `--confirm` token |

## Risk Tiers

| Tier | Meaning |
| --- | --- |
| `read` | Inspect pages, menus, status, public metadata, and generated artifacts. |
| `prepare` | Fill drafts, build plans, attach local files in dry-run, and save artifacts without final submit. |
| `approval` | Execute only after explicit user approval tied to a prepared artifact. |
| `blocked` | Do not automate. Includes CAPTCHA bypass, payment, credential reveal, and policy evasion. |

## Site Index

| Site | Status | Primary References | Next Action |
| --- | --- | --- | --- |
| Orchestrator | active | `docs/worktree_management_index.md`, `docs/site_automation_reference_index.md` | Keep common indexes current and avoid staging unrelated changes. |
| Homepage | security watch active | Homepage `docs/security-audit.md`, homepage `docs/work-log.md` | Confirm notification channel and run full audit before deployment approval. |
| EUM | complete baseline | `docs/eum_logic_reference_20260513.md` | Live submit only after explicit approval and real values. |
| Hiworks | complete baseline | `docs/hiworks_logic_reference_20260513.md` | Keep mail send and state-changing section actions approval-gated. |
| Naver | implemented partial | `docs/naver_developed_tools_index.md`, `docs/NAVER_SERVICES_EXPANSION_PLAN.md`, `docs/naver_live_safety_policy_20260513.md` | Use the developed tool index first; keep CDP tab isolation, approval gates, and paid-feature blocks active. |
| SmartStore | complete baseline | `docs/smartstore_logic_reference_20260513.md` | Verify SEO, competitor, CSV import, order, inventory, and analytics workflows separately. |
| G2B | verified read-only | `docs/reports/g2b_completion_report_20260513.md`, `docs/reports/g2b_public_notice_readonly_matrix_20260507.md` | Keep public notice and attachment-list work read-only; login/certificate/bid/contract/payment/final submit remain blocked or user-present only. |
| Google/YouTube | implemented gated | `docs/google_developed_tools_index.md`, `docs/google_domain_function_index.md`, `docs/google_surface_catalog_reference_20260513.md`, `docs/google_business_workflow_reference_20260513.md` | Use the developed tool and domain function indexes first; complete per-surface live read reports and prefer official APIs where available. |

## Homepage Security Link

Homepage operations are managed in the sibling homepage repository. Current
security state:

- quick audit every 5 minutes
- full audit daily at 03:40 KST
- log retention cleanup daily at 03:50 KST
- latest production status: `/home/ubuntu/logs/security-audit/latest.status`

Treat a failed homepage security audit as a deployment blocker until classified.

## Error Handling

If an error occurs during any task:

1. Regenerate `data/worktree_change_index_latest.json`.
2. Identify the affected owner/category/layer.
3. Check the owner references in `configs/common_operations_index.json`.
4. Run the smallest verification command for that owner.
5. Update the log or completion report before moving to another owner scope.
