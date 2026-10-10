# Naver Developed Tools Index

Updated: 2026-05-27

This document records only the Naver tools that have been developed and
verified in this repo. It is the service-level index for Naver work and should
be checked before adding more Naver automation.

## Operating Rules

- Use existing CDP sessions only; do not launch, restart, or close browsers.
- Use the common tab-isolation gate for browser work:
  `scripts/browser/session/browser_cdp_selection_gate.py:create_isolated_target`.
- Read and prepare workflows may run after session/live-safety checks.
- Final submit, send, publish, delete, move, save, join submit, upload, billing,
  API key issue, and ad publish actions require explicit approval or are blocked.
- Paid Naver API/search-ad/payment actions are blocked. The user does not use
  paid Naver features.

## Tool Catalog

| Area | Command | Risk | Status | Main Files | Output |
| --- | --- | --- | --- | --- | --- |
| Service catalog | `python scripts\entry\cdp_cli.py naver catalog` | read | implemented | `scripts/naver/service_catalog.py` | `data/naver_service_action_catalog_latest.json` |
| Login/session | `python scripts\entry\cdp_cli.py naver login`, `session-check` | prepare/read | implemented | `scripts/naver/router.py`, `scripts/naver/browser_gate.py` | console status |
| Keyword tools | `python scripts\entry\cdp_cli.py naver keyword-tools catalog` | read | implemented | `scripts/naver/keyword_tools.py`, `scripts/naver/router.py` | `data/naver_keyword_tools_latest.json` |
| Keyword research plan | `python scripts\entry\cdp_cli.py naver keyword-tools plan --query=...` | read | implemented | `scripts/naver/keyword_tools.py` | `data/naver_keyword_tools_latest.json` |
| Keyword paid policy | `python scripts\entry\cdp_cli.py naver keyword-tools paid-blocks` | blocked-policy | implemented | `scripts/naver/keyword_tools.py`, `scripts/common/gate.py` | `data/naver_keyword_tools_latest.json` |
| Cafe list | `python scripts\entry\cdp_cli.py naver cafe list` | read | verified | `scripts/naver/cafe/list_collector.py`, `scripts/naver/cafe/list_background_runner.py` | `data/naver_cafes_latest.json` |
| Cafe main/home | `python scripts\entry\cdp_cli.py naver cafe home` | read | implemented | `scripts/naver/cafe/main_page.py` | `data/naver_cafe_main_latest.json` |
| Cafe topic search | `python scripts\entry\cdp_cli.py naver cafe topic-search --query=...` | read | verified | `scripts/naver/cafe/topic_search.py` | `data/naver_cafe_topic_search_latest.json` |
| Cafe join request | `python scripts\entry\cdp_cli.py naver cafe join-request --cafe-url=...` | prepare | verified | `scripts/naver/cafe/join_request.py` | `data/naver_cafe_<cafe>_join_request_latest.json` |
| Cafe join submit gate | `python scripts\entry\cdp_cli.py naver cafe join-submit --approved --confirm=NAVER_APPROVED_CAFE_JOIN` | approval | implemented gate only | `scripts/naver/cafe/join_request.py`, `scripts/naver/router.py` | `data/naver_cafe_<cafe>_join_submit_latest.json` |
| Joined cafe home collect | `python scripts\entry\cdp_cli.py naver cafe collect --cafe-url=...` | read | verified | `scripts/naver/cafe/member_collect.py` | `data/naver_cafe_<cafe>_collect_latest.json` |
| Joined cafe board collect | `python scripts\entry\cdp_cli.py naver cafe boards --cafe-url=...` | read | verified | `scripts/naver/cafe/member_collect.py` | `data/naver_cafe_<cafe>_boards_latest.json` |
| Cafe post list/read/write/publish | `python scripts\entry\cdp_cli.py naver cafe posts/read/write/publish` | read/prepare/approval | existing | `scripts/naver/cafe.py`, `scripts/naver/router.py` | `data/naver_cafe_*_latest.json` |
| Naver mail background | `scripts/naver_mail/background_runner.py` | read | verified | `scripts/naver_mail/background_runner.py`, `scripts/naver/mail_read/*` | report JSON from runner |
| Naver mail settings panel | settings inspection modules | read/approval for save | implemented | `scripts/naver_mail/settings_panel.py` | settings menu records |

## Registered Cafe Targets

| Cafe | URL Key | Club ID | Tool Support |
| --- | --- | --- | --- |
| SmartStore seller cafe | `soho` | `10094408` | home collect, board collect |
| AI Study | `royaltyserver` | `22417348` | join request, home collect, board collect |

`royaltyserver` board hints are registered for AI jobs, tool errors, work
sharing, AI news, SNS/marketing AI, image/video AI, business AI, and education.

## Gates

| Gate | Applies To | Policy |
| --- | --- | --- |
| `cdp_tab_isolation` | Browser work through CDP | Create a dedicated target tab in an existing CDP session. |
| `naver_cafe_join_submit` | Cafe final join submit | Requires `--approved --confirm=NAVER_APPROVED_CAFE_JOIN`; final visible-form adapter still must re-check before clicking. |
| `naver_mail_send` | Mail send | Approval required. |
| `naver_mail_delete` | Mail delete/trash | Approval required. |
| `naver_mail_move` | Mail move/archive/spam/label | Approval required. |
| `naver_mail_settings_save` | Mail setting save | Approval required. |
| `naver_paid_api_key_issue` | Paid Naver API key issue | Blocked. |
| `naver_paid_api_use` | Paid Naver API use | Blocked. |
| `naver_searchad_campaign_create` | Search ad campaign creation | Blocked. |
| `naver_searchad_budget_update` | Search ad budget update | Blocked. |
| `naver_payment_method_register` | Payment method registration | Blocked. |
| `naver_ad_publish` | Ad publish | Blocked. |

## Verification

Latest focused verification:

```powershell
python -m pytest tests\test_browser_cdp_selection_gate.py tests\test_naver_cafe_list_collector.py tests\test_naver_mail_background_runner.py tests\test_naver_service_router.py -q
```

Result: `52 passed`.

Live CDP evidence:

- `cafe join-request --cafe-url=royaltyserver` and
  `cafe boards --cafe-url=royaltyserver` ran in parallel using different CDP
  target IDs.
- Outputs were saved to:
  - `data/naver_cafe_royaltyserver_join_request_latest.json`
  - `data/naver_cafe_royaltyserver_boards_latest.json`

## Remaining Work

- Final visible-form adapter for actual cafe join submit is intentionally not
  auto-clicking yet.
- Broader per-service completion reports can be added later, but this index is
  the current lock list for developed Naver tools.
